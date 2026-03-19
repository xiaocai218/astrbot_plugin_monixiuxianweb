import re
import time

from astrbot.api import logger
from astrbot.api.all import At
from astrbot.api.event import AstrMessageEvent

from ..data.data_manager import DataBase
from ..managers.battle_hp_service import BattleHpService
from ..managers.combat_manager import CombatManager
from ..managers.pet_battle_service import PetBattleService
from ..models_extended import UserStatus

DUEL_COOLDOWN = 300
DUEL_LOSER_COOLDOWN = 1800
DUEL_LOSER_COOLDOWN_KEY = "duel_loser_cd_until"
SPAR_COOLDOWN = 60


class CombatHandlers:
    def __init__(self, db: DataBase, combat_mgr: CombatManager, config_manager=None):
        self.db = db
        self.combat_mgr = combat_mgr
        self.config_manager = config_manager
        self.battle_hp_service = BattleHpService(db, combat_mgr, config_manager)
        self.pet_battle_service = PetBattleService(db)

    async def _get_combat_cooldown(self, user_id: str) -> dict:
        try:
            async with self.db.conn.execute(
                "SELECT last_duel_time, last_spar_time FROM combat_cooldowns WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {"last_duel_time": row[0], "last_spar_time": row[1]}
        except Exception as exc:
            logger.warning(f"获取战斗冷却失败: {exc}")
        return {"last_duel_time": 0, "last_spar_time": 0}

    async def _update_combat_cooldown(self, user_id: str, combat_type: str):
        now = int(time.time())
        try:
            if combat_type == "duel":
                await self.db.conn.execute(
                    """
                    INSERT INTO combat_cooldowns (user_id, last_duel_time, last_spar_time)
                    VALUES (?, ?, 0)
                    ON CONFLICT(user_id) DO UPDATE SET last_duel_time = ?
                    """,
                    (user_id, now, now),
                )
            else:
                await self.db.conn.execute(
                    """
                    INSERT INTO combat_cooldowns (user_id, last_duel_time, last_spar_time)
                    VALUES (?, 0, ?)
                    ON CONFLICT(user_id) DO UPDATE SET last_spar_time = ?
                    """,
                    (user_id, now, now),
                )
            await self.db.conn.commit()
        except Exception as exc:
            logger.warning(f"更新战斗冷却失败: {exc}")

    async def _get_or_create_user_cd(self, user_id: str):
        return await self.battle_hp_service.get_or_create_user_cd(user_id)

    async def _get_duel_loser_cooldown_remaining(self, user_id: str) -> int:
        user_cd = await self._get_or_create_user_cd(user_id)
        extra_data = user_cd.get_extra_data()
        cooldown_until = int(extra_data.get(DUEL_LOSER_COOLDOWN_KEY, 0) or 0)
        now = int(time.time())
        remaining = cooldown_until - now

        if remaining <= 0 and cooldown_until:
            extra_data.pop(DUEL_LOSER_COOLDOWN_KEY, None)
            user_cd.set_extra_data(extra_data)
            await self.db.ext.update_user_cd(user_cd)
            return 0

        return max(0, remaining)

    async def _set_duel_loser_cooldown(self, user_id: str, cooldown_until: int):
        user_cd = await self._get_or_create_user_cd(user_id)
        extra_data = user_cd.get_extra_data()
        extra_data[DUEL_LOSER_COOLDOWN_KEY] = cooldown_until
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    async def _get_target_id(self, event: AstrMessageEvent, arg: str) -> str:
        message_chain = []
        if hasattr(event, "message_obj") and event.message_obj:
            message_chain = getattr(event.message_obj, "message", []) or []

        for component in message_chain:
            if isinstance(component, At):
                candidate = None
                for attr in ("qq", "target", "uin", "user_id"):
                    candidate = getattr(component, attr, None)
                    if candidate:
                        break
                if candidate:
                    return str(candidate).lstrip("@")

        if arg:
            cleaned = arg.strip().lstrip("@")
            if cleaned.isdigit():
                return cleaned

        message_text = event.get_message_str() if hasattr(event, "get_message_str") else ""
        match = re.search(r"(\d{5,})", message_text or "")
        if match:
            return match.group(1)
        return None

    async def _prepare_combat_stats(self, user_id: str):
        stats, user_cd, _player = await self.battle_hp_service.prepare_combat_stats(
            user_id,
            include_equipment_bonus=True,
            display_name_prefix="道友",
        )
        if not stats:
            return None
        return stats, user_cd

    async def execute_duel(self, user_id: str, target_id: str):
        if not target_id:
            return False, "请指定决斗目标。", None

        if user_id == target_id:
            return False, "不能和自己决斗。", None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            return False, f"你当前正在{current_status}，无法进行战斗。", None

        target_cd = await self.db.ext.get_user_cd(target_id)
        if target_cd and target_cd.type != UserStatus.IDLE:
            target_status = UserStatus.get_name(target_cd.type)
            return False, f"对方当前正在{target_status}，无法进行战斗。", None

        loser_cd_remaining = await self._get_duel_loser_cooldown_remaining(user_id)
        if loser_cd_remaining > 0:
            return (
                False,
                f"你处于决斗失败冷却中，还需 {loser_cd_remaining // 60} 分 {loser_cd_remaining % 60} 秒。",
                None,
            )

        now = int(time.time())
        cooldown = await self._get_combat_cooldown(user_id)
        last_duel = cooldown.get("last_duel_time", 0)
        if last_duel and (now - last_duel) < DUEL_COOLDOWN:
            remaining = DUEL_COOLDOWN - (now - last_duel)
            return False, f"决斗冷却中，还需 {remaining // 60} 分 {remaining % 60} 秒。", None

        p1_bundle = await self._prepare_combat_stats(user_id)
        p2_bundle = await self._prepare_combat_stats(target_id)
        if not p1_bundle:
            return False, "你还未踏入修仙之路。", None
        if not p2_bundle:
            return False, "对方还未踏入修仙之路。", None

        p1_stats, p1_user_cd = p1_bundle
        p2_stats, p2_user_cd = p2_bundle
        pet_context1 = await self.pet_battle_service.build_battle_context(user_id)
        pet_context2 = await self.pet_battle_service.build_battle_context(target_id)
        result = self.combat_mgr.player_vs_player(
            p1_stats,
            p2_stats,
            combat_type=2,
            pet_context1=pet_context1,
            pet_context2=pet_context2,
        )

        await self.db.ext.update_player_hp_mp(user_id, result["player1_final_hp"], result["player1_final_mp"])
        await self.db.ext.update_player_hp_mp(target_id, result["player2_final_hp"], result["player2_final_mp"])
        await self.battle_hp_service.sync_battle_hp_recovery(
            p1_user_cd,
            result["player1_final_hp"],
            p1_stats.max_hp,
        )
        await self.battle_hp_service.sync_battle_hp_recovery(
            p2_user_cd,
            result["player2_final_hp"],
            p2_stats.max_hp,
        )
        await self._update_combat_cooldown(user_id, "duel")

        if result["winner"] == user_id:
            loser_id = target_id
        elif result["winner"] == target_id:
            loser_id = user_id
        else:
            loser_id = None

        if loser_id:
            await self._set_duel_loser_cooldown(loser_id, now + DUEL_LOSER_COOLDOWN)

        log = "\n".join(result["combat_log"])
        return True, log, result

    async def handle_duel(self, event: AstrMessageEvent, target: str):
        user_id = event.get_sender_id()
        target_id = await self._get_target_id(event, target)
        _success, msg, _result = await self.execute_duel(user_id, target_id)
        yield event.plain_result(msg)

    async def handle_spar(self, event: AstrMessageEvent, target: str):
        user_id = event.get_sender_id()
        target_id = await self._get_target_id(event, target)

        if not target_id:
            yield event.plain_result("请指定切磋目标。")
            return

        if user_id == target_id:
            yield event.plain_result("不能和自己切磋。")
            return

        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"你当前正在{current_status}，无法进行战斗。")
            return

        target_cd = await self.db.ext.get_user_cd(target_id)
        if target_cd and target_cd.type != UserStatus.IDLE:
            target_status = UserStatus.get_name(target_cd.type)
            yield event.plain_result(f"对方当前正在{target_status}，无法进行战斗。")
            return

        now = int(time.time())
        cooldown = await self._get_combat_cooldown(user_id)
        last_spar = cooldown.get("last_spar_time", 0)
        if last_spar and (now - last_spar) < SPAR_COOLDOWN:
            remaining = SPAR_COOLDOWN - (now - last_spar)
            yield event.plain_result(f"切磋冷却中，还需 {remaining} 秒。")
            return

        p1_bundle = await self._prepare_combat_stats(user_id)
        p2_bundle = await self._prepare_combat_stats(target_id)
        if not p1_bundle or not p2_bundle:
            yield event.plain_result("双方都需要已踏入修仙之路。")
            return

        p1_stats, _ = p1_bundle
        p2_stats, _ = p2_bundle
        pet_context1 = await self.pet_battle_service.build_battle_context(user_id)
        pet_context2 = await self.pet_battle_service.build_battle_context(target_id)
        result = self.combat_mgr.player_vs_player(
            p1_stats,
            p2_stats,
            combat_type=1,
            pet_context1=pet_context1,
            pet_context2=pet_context2,
        )
        await self._update_combat_cooldown(user_id, "spar")

        log = "\n".join(result["combat_log"])
        yield event.plain_result(log)
