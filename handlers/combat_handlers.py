import json
import re
import time

from astrbot.api import logger
from astrbot.api.all import At
from astrbot.api.event import AstrMessageEvent

from ..data.data_manager import DataBase
from ..managers.battle_hp_service import BattleHpService
from ..managers.combat_manager import CombatManager
from ..managers.combat_resource_service import CombatResourceService
from ..managers.pet_battle_service import PetBattleService
from ..models_extended import UserStatus

DUEL_COOLDOWN = 300
DUEL_LOSER_COOLDOWN = 1800
DUEL_LOSER_COOLDOWN_KEY = "duel_loser_cd_until"
DUEL_REQUEST_TIMEOUT = 60
DUEL_REQUEST_RETRY_COOLDOWN = 60
SPAR_COOLDOWN = 60


class CombatHandlers:
    def __init__(self, db: DataBase, combat_mgr: CombatManager, config_manager=None):
        self.db = db
        self.combat_mgr = combat_mgr
        self.config_manager = config_manager
        self.battle_hp_service = BattleHpService(db, combat_mgr, config_manager)
        self.combat_resource_service = CombatResourceService(db)
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

    def _duel_request_key(self, target_id: str) -> str:
        return f"duel_request_{target_id}"

    def _duel_request_retry_key(self, challenger_id: str) -> str:
        return f"duel_request_retry_{challenger_id}"

    async def _get_duel_request_retry_remaining(self, challenger_id: str) -> int:
        value = await self.db.ext.get_system_config(self._duel_request_retry_key(challenger_id))
        if not value:
            return 0
        retry_until = int(value or 0)
        remaining = retry_until - int(time.time())
        if remaining <= 0:
            await self.db.ext.set_system_config(self._duel_request_retry_key(challenger_id), "0")
            return 0
        return remaining

    async def _set_duel_request_retry(self, challenger_id: str, seconds: int = DUEL_REQUEST_RETRY_COOLDOWN):
        retry_until = int(time.time()) + seconds
        await self.db.ext.set_system_config(self._duel_request_retry_key(challenger_id), str(retry_until))

    async def _get_pending_duel_request(self, target_id: str) -> dict | None:
        raw_value = await self.db.ext.get_system_config(self._duel_request_key(target_id))
        if not raw_value or raw_value == "0":
            return None

        try:
            payload = json.loads(raw_value)
        except Exception:
            await self.db.ext.set_system_config(self._duel_request_key(target_id), "0")
            return None

        expire_at = int(payload.get("expire_at", 0) or 0)
        if expire_at <= int(time.time()):
            await self.db.ext.set_system_config(self._duel_request_key(target_id), "0")
            challenger_id = str(payload.get("challenger_id", "") or "")
            if challenger_id:
                await self._set_duel_request_retry(challenger_id)
            return None

        return payload

    async def _set_pending_duel_request(self, challenger_id: str, challenger_name: str, target_id: str):
        payload = {
            "challenger_id": challenger_id,
            "challenger_name": challenger_name,
            "target_id": target_id,
            "created_at": int(time.time()),
            "expire_at": int(time.time()) + DUEL_REQUEST_TIMEOUT,
        }
        await self.db.ext.set_system_config(
            self._duel_request_key(target_id),
            json.dumps(payload, ensure_ascii=False),
        )

    async def _clear_pending_duel_request(self, target_id: str):
        await self.db.ext.set_system_config(self._duel_request_key(target_id), "0")

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

        challenger = await self.db.get_player_by_id(user_id)
        if not challenger:
            return False, "你还未踏入修仙之路。", None
        ok, resource_msg, _cost = await self.combat_resource_service.consume_entry_cost(challenger, "duel")
        if not ok:
            return False, resource_msg, None

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
        if not target_id:
            yield event.plain_result("请指定决斗目标。")
            return

        if user_id == target_id:
            yield event.plain_result("不能和自己决斗。")
            return

        retry_remaining = await self._get_duel_request_retry_remaining(user_id)
        if retry_remaining > 0:
            yield event.plain_result(f"决斗请求冷却中，还需 {retry_remaining} 秒后才能再次发起。")
            return

        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"你当前正在{current_status}，无法发起决斗请求。")
            return

        target_cd = await self.db.ext.get_user_cd(target_id)
        if target_cd and target_cd.type != UserStatus.IDLE:
            target_status = UserStatus.get_name(target_cd.type)
            yield event.plain_result(f"对方当前正在{target_status}，暂时无法处理决斗请求。")
            return

        loser_cd_remaining = await self._get_duel_loser_cooldown_remaining(user_id)
        if loser_cd_remaining > 0:
            yield event.plain_result(
                f"你处于决斗失败冷却中，还需 {loser_cd_remaining // 60} 分 {loser_cd_remaining % 60} 秒。"
            )
            return

        cooldown = await self._get_combat_cooldown(user_id)
        now = int(time.time())
        last_duel = cooldown.get("last_duel_time", 0)
        if last_duel and (now - last_duel) < DUEL_COOLDOWN:
            remaining = DUEL_COOLDOWN - (now - last_duel)
            yield event.plain_result(f"决斗冷却中，还需 {remaining // 60} 分 {remaining % 60} 秒。")
            return

        pending_request = await self._get_pending_duel_request(target_id)
        if pending_request:
            yield event.plain_result("对方当前已有待处理的决斗请求，请稍后再试。")
            return

        challenger = await self.db.get_player_by_id(user_id)
        if not challenger:
            yield event.plain_result("你还未踏入修仙之路。")
            return

        await self._set_pending_duel_request(user_id, challenger.name, target_id)
        yield event.plain_result(
            f"你向【{target_id}】发起了决斗请求。\n"
            f"对方可在 {DUEL_REQUEST_TIMEOUT} 秒内输入 /接受决斗 或 /拒绝决斗。"
        )

    async def handle_accept_duel(self, event: AstrMessageEvent):
        target_id = event.get_sender_id()
        request = await self._get_pending_duel_request(target_id)
        if not request:
            yield event.plain_result("当前没有待处理的决斗请求。")
            return

        challenger_id = str(request.get("challenger_id", "") or "")
        if not challenger_id:
            await self._clear_pending_duel_request(target_id)
            yield event.plain_result("这条决斗请求已失效。")
            return

        await self._clear_pending_duel_request(target_id)
        success, msg, _result = await self.execute_duel(challenger_id, target_id)
        yield event.plain_result(msg)

    async def handle_reject_duel(self, event: AstrMessageEvent):
        target_id = event.get_sender_id()
        request = await self._get_pending_duel_request(target_id)
        if not request:
            yield event.plain_result("当前没有待处理的决斗请求。")
            return

        challenger_id = str(request.get("challenger_id", "") or "")
        challenger_name = str(request.get("challenger_name", "对方") or "对方")
        await self._clear_pending_duel_request(target_id)
        if challenger_id:
            await self._set_duel_request_retry(challenger_id)

        yield event.plain_result(
            f"你拒绝了【{challenger_name}】的决斗请求。\n"
            f"对方需等待 {DUEL_REQUEST_RETRY_COOLDOWN} 秒后才能再次发起。"
        )

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

        challenger = await self.db.get_player_by_id(user_id)
        if not challenger:
            yield event.plain_result("你还未踏入修仙之路。")
            return
        ok, resource_msg, _cost = await self.combat_resource_service.consume_entry_cost(challenger, "spar")
        if not ok:
            yield event.plain_result(resource_msg)
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
