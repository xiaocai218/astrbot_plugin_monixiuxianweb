"""世界 Boss 管理器。"""

import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ..battle_hp_utils import (
    BOSS_CHALLENGE_COOLDOWN_KEY,
    BOSS_CHALLENGE_COOLDOWN_SECONDS,
    BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY,
    BOSS_CHALLENGE_RECOVERY_KEY,
    BOSS_CHALLENGE_RECOVERY_SECONDS,
    BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY,
)
from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import Boss, UserStatus
from .battle_hp_service import BattleHpService
from .boss_challenge_service import BossChallengeService
from .combat_manager import CombatManager, CombatStats
from .combat_resource_service import CombatResourceService
from .pet_battle_service import PetBattleService

if TYPE_CHECKING:
    from ..core import StorageRingManager


class BossManager:
    """处理世界 Boss 的生成、挑战、奖励与掉落。"""

    BOSS_DAILY_CHALLENGE_COUNT_KEY = "boss_daily_challenge_count"
    BOSS_DAILY_CHALLENGE_DATE_KEY = "boss_daily_challenge_date"
    BOSS_DAILY_CHALLENGE_LIMIT = 3

    BOSS_LEVELS = [
        {"name": "炼气", "level_index": 0, "hp_mult": 1.0, "atk_mult": 1.0, "reward_mult": 1.0},
        {"name": "筑基", "level_index": 3, "hp_mult": 1.5, "atk_mult": 1.2, "reward_mult": 1.5},
        {"name": "金丹", "level_index": 6, "hp_mult": 2.0, "atk_mult": 1.5, "reward_mult": 2.0},
        {"name": "元婴", "level_index": 9, "hp_mult": 2.5, "atk_mult": 1.8, "reward_mult": 2.5},
        {"name": "化神", "level_index": 12, "hp_mult": 3.0, "atk_mult": 2.0, "reward_mult": 3.0},
        {"name": "炼虚", "level_index": 15, "hp_mult": 4.0, "atk_mult": 2.5, "reward_mult": 4.0},
        {"name": "合体", "level_index": 18, "hp_mult": 5.0, "atk_mult": 3.0, "reward_mult": 5.0},
        {"name": "大乘", "level_index": 21, "hp_mult": 6.0, "atk_mult": 3.5, "reward_mult": 6.0},
    ]

    BOSS_NAMES = [
        "血魔",
        "邪修",
        "魔头",
        "妖王",
        "魔君",
        "异兽",
        "凶兽",
        "妖尊",
        "魔尊",
        "邪帝",
        "天魔",
        "地魔",
        "魔神",
        "妖神",
        "邪神",
    ]

    BOSS_DROP_TABLE = {
        "low": [
            {"name": "灵兽内丹", "weight": 40, "min": 1, "max": 2},
            {"name": "妖兽精血", "weight": 30, "min": 1, "max": 3},
            {"name": "玄铁", "weight": 30, "min": 3, "max": 6},
        ],
        "mid": [
            {"name": "灵兽内丹", "weight": 30, "min": 2, "max": 4},
            {"name": "星陨石", "weight": 25, "min": 2, "max": 4},
            {"name": "天材地宝", "weight": 20, "min": 1, "max": 2},
            {"name": "功法残页", "weight": 25, "min": 1, "max": 2},
        ],
        "high": [
            {"name": "天材地宝", "weight": 30, "min": 2, "max": 4},
            {"name": "混沌精华", "weight": 25, "min": 1, "max": 2},
            {"name": "神兽之骨", "weight": 20, "min": 1, "max": 1},
            {"name": "远古秘卷", "weight": 15, "min": 1, "max": 1},
            {"name": "仙器碎片", "weight": 10, "min": 1, "max": 1},
        ],
    }

    BOSS_CHALLENGE_COOLDOWN_KEY = BOSS_CHALLENGE_COOLDOWN_KEY
    BOSS_CHALLENGE_RECOVERY_KEY = BOSS_CHALLENGE_RECOVERY_KEY
    BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY = BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY
    BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY = BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY
    BOSS_CHALLENGE_COOLDOWN_SECONDS = BOSS_CHALLENGE_COOLDOWN_SECONDS
    BOSS_CHALLENGE_RECOVERY_SECONDS = BOSS_CHALLENGE_RECOVERY_SECONDS

    def __init__(
        self,
        db: DataBase,
        combat_mgr: CombatManager,
        config_manager=None,
        storage_ring_manager: "StorageRingManager" = None,
    ):
        self.db = db
        self.combat_mgr = combat_mgr
        self.storage_ring_manager = storage_ring_manager
        self.config_manager = config_manager
        self.config = config_manager.boss_config if config_manager else {}
        self.levels = self.config.get("levels", self.BOSS_LEVELS)
        self.battle_hp_service = BattleHpService(db, combat_mgr, config_manager)
        self.boss_challenge_service = BossChallengeService(db)
        self.combat_resource_service = CombatResourceService(db)
        self.pet_battle_service = PetBattleService(db)

    async def _get_boss_cooldown_remaining(self, user_cd) -> int:
        extra_data = user_cd.get_extra_data()
        cooldown_until = int(extra_data.get(self.BOSS_CHALLENGE_COOLDOWN_KEY, 0) or 0)
        now = int(time.time())
        remaining = cooldown_until - now

        if remaining <= 0 and cooldown_until:
            extra_data.pop(self.BOSS_CHALLENGE_COOLDOWN_KEY, None)
            user_cd.set_extra_data(extra_data)
            await self.db.ext.update_user_cd(user_cd)
            return 0

        return max(0, remaining)

    async def _set_boss_challenge_cooldown(self, user_cd, cooldown_until: int):
        extra_data = user_cd.get_extra_data()
        extra_data[self.BOSS_CHALLENGE_COOLDOWN_KEY] = cooldown_until
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    def _today_str(self) -> str:
        return self.boss_challenge_service._today_str()

    async def _get_daily_boss_challenge_usage(self, user_cd) -> tuple[int, int]:
        return await self.boss_challenge_service.get_daily_status_from_user_cd(user_cd)

    async def _consume_daily_boss_challenge(self, user_cd) -> tuple[int, int]:
        return await self.boss_challenge_service.consume_daily_challenge_from_user_cd(user_cd)

    async def spawn_boss(
        self,
        base_exp: int = 100000,
        level_config: Optional[Dict] = None,
    ) -> Tuple[bool, str, Optional[Boss]]:
        existing_boss = await self.db.ext.get_active_boss()
        if existing_boss:
            return False, f"当前已有 Boss【{existing_boss.boss_name}】存在。", None

        if not level_config:
            level_config = random.choice(self.levels)

        boss_name = f"{random.choice(self.BOSS_NAMES)}·{level_config['name']}境"
        hp_mult = level_config["hp_mult"]
        atk_mult = level_config["atk_mult"]
        reward_mult = level_config["reward_mult"]

        max_hp = int(base_exp * hp_mult // 2)
        atk = int(base_exp * atk_mult // 10)
        stone_reward = int(base_exp * reward_mult // 10)

        defense = 0
        if level_config["level_index"] >= 15:
            defense = random.randint(40, 90)

        boss = Boss(
            boss_id=0,
            boss_name=boss_name,
            boss_level=level_config["name"],
            hp=max_hp,
            max_hp=max_hp,
            atk=atk,
            defense=defense,
            stone_reward=stone_reward,
            create_time=int(time.time()),
            status=1,
        )

        boss_id = await self.db.ext.create_boss(boss)
        boss.boss_id = boss_id

        msg = (
            "Boss 降临\n"
            "━━━━━━━━━━━━━━\n"
            f"{boss_name} 降临世间\n"
            f"境界：{level_config['name']}\n"
            f"HP：{max_hp}\n"
            f"ATK：{atk}\n"
            f"减伤：{defense}%\n"
            f"奖励：{stone_reward} 灵石\n\n"
            "快来挑战吧！"
        )
        return True, msg, boss

    async def challenge_boss(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "你还未踏入修仙之路。", None

        if int(player.cultivation_start_time or 0) > 0:
            return False, "当前正在闭关，无法挑战世界 Boss，请先出关。", None

        boss = await self.db.ext.get_active_boss()
        if not boss:
            return False, "当前没有世界 Boss。", None

        user_cd = await self.battle_hp_service.get_or_create_user_cd(user_id)
        if user_cd.type != UserStatus.IDLE:
            return False, "你当前正忙，无法挑战 Boss。", None

        used_count, remaining_count = await self._get_daily_boss_challenge_usage(user_cd)
        if remaining_count <= 0:
            return (
                False,
                f"你今日挑战世界 Boss 的次数已用尽（{used_count}/{self.BOSS_DAILY_CHALLENGE_LIMIT}），请明日再来。",
                None,
            )

        player_stats, user_cd, player = await self.battle_hp_service.prepare_combat_stats(
            user_id,
            include_equipment_bonus=False,
            display_name_prefix="道友",
        )
        if not player_stats:
            return False, "你还未踏入修仙之路。", None

        cooldown_remaining = await self._get_boss_cooldown_remaining(user_cd)
        if cooldown_remaining > 0:
            hp_percent = (player_stats.hp / player_stats.max_hp) * 100 if player_stats.max_hp > 0 else 0
            minutes = cooldown_remaining // 60
            seconds = cooldown_remaining % 60
            return (
                False,
                (
                    "你刚刚被世界 Boss 击败，5 分钟内无法再次挑战。\n"
                    f"当前战斗HP：{player_stats.hp}/{player_stats.max_hp}（{hp_percent:.0f}%）\n"
                    f"还需等待 {minutes} 分 {seconds} 秒后才能再次挑战。\n"
                    "战斗HP会按时间自动恢复，约 10 分钟恢复满血。"
                ),
                None,
            )

        ok, resource_msg, _cost = await self.combat_resource_service.consume_entry_cost(player, "boss")
        if not ok:
            return False, resource_msg, None

        used_count, remaining_count = await self._consume_daily_boss_challenge(user_cd)

        boss_stats = CombatStats(
            user_id=str(boss.boss_id),
            name=boss.boss_name,
            hp=boss.hp,
            max_hp=boss.max_hp,
            mp=boss.max_hp,
            max_mp=boss.max_hp,
            atk=boss.atk,
            defense=boss.defense,
            crit_rate=30,
            exp=boss.stone_reward,
        )

        player_pet_context = await self.pet_battle_service.build_battle_context(user_id)
        battle_result = self.combat_mgr.player_vs_boss(
            player_stats,
            boss_stats,
            player_pet_context=player_pet_context,
        )
        winner = battle_result["winner"]
        reward = battle_result["reward"]
        final_hp = battle_result["player_final_hp"]
        final_mp = battle_result["player_final_mp"]
        gold_gain = max(0, reward)

        if winner == user_id:
            boss.status = 0
            await self.db.ext.defeat_boss(boss.boss_id)

            item_msg = ""
            if self.storage_ring_manager:
                dropped_items = await self._roll_boss_drops(player, boss)
                if dropped_items:
                    item_lines = []
                    for item_name, count in dropped_items:
                        success, _msg = await self.storage_ring_manager.store_item(
                            player, item_name, count, silent=True
                        )
                        if success:
                            item_lines.append(f"  - {item_name} x{count}")
                        else:
                            item_lines.append(f"  - {item_name} x{count}（储物戒已满，掉落丢失）")
                    if item_lines:
                        item_msg = "\n\n获得物品：\n" + "\n".join(item_lines)

            recovery_msg = ""
            if final_hp < player_stats.max_hp:
                recovery_msg = "\n战斗 HP 将继续按时间自动恢复，直到满血。"

            result_msg = (
                "挑战成功\n"
                "━━━━━━━━━━━━━━\n"
                f"你成功击败了【{boss.boss_name}】\n"
                f"战斗回合数：{battle_result['rounds']}\n"
                f"获得灵石：{reward}\n"
                f"今日 Boss 次数：{used_count}/{self.BOSS_DAILY_CHALLENGE_LIMIT}（剩余 {remaining_count} 次）"
                f"{item_msg}\n\n"
                f"{player_stats.name}\n"
                f"HP：{final_hp}/{player_stats.max_hp}"
                f"{recovery_msg}"
            )
        else:
            boss.hp = battle_result["boss_final_hp"]
            await self.db.ext.update_boss(boss)

            final_hp = 1
            await self._set_boss_challenge_cooldown(
                user_cd,
                int(time.time()) + self.BOSS_CHALLENGE_COOLDOWN_SECONDS,
            )

            result_msg = (
                "挑战失败\n"
                "━━━━━━━━━━━━━━\n"
                f"你被【{boss.boss_name}】击败了，战斗回合数：{battle_result['rounds']}\n"
                f"安慰奖励：{reward} 灵石\n"
                f"今日 Boss 次数：{used_count}/{self.BOSS_DAILY_CHALLENGE_LIMIT}（剩余 {remaining_count} 次）\n\n"
                f"{boss.boss_name} 剩余 HP：{boss.hp}/{boss.max_hp}\n"
                "你的战斗 HP 已降至 1，并开始按时间恢复。\n"
                "5 分钟后才能再次挑战 Boss。"
            )

        latest_player = await self.db.get_player_by_id(user_id)
        latest_player.gold += gold_gain
        latest_player.hp = final_hp
        latest_player.mp = final_mp
        await self.db.update_player(latest_player)

        await self.battle_hp_service.sync_battle_hp_recovery(user_cd, final_hp, player_stats.max_hp)

        combat_log = "\n".join(battle_result["combat_log"])
        full_msg = combat_log + "\n\n" + result_msg
        return True, full_msg, battle_result

    async def get_boss_info(self) -> Tuple[bool, str, Optional[Boss]]:
        boss = await self.db.ext.get_active_boss()
        if not boss:
            return False, "当前没有世界 Boss。", None

        hp_percent = (boss.hp / boss.max_hp) * 100 if boss.max_hp else 0
        msg = (
            "当前 Boss\n"
            "━━━━━━━━━━━━━━\n"
            f"名称：{boss.boss_name}\n"
            f"境界：{boss.boss_level}\n\n"
            f"HP：{boss.hp}/{boss.max_hp} ({hp_percent:.1f}%)\n"
            f"ATK：{boss.atk}\n"
            f"减伤：{boss.defense}%\n\n"
            f"奖励：{boss.stone_reward} 灵石\n\n"
            "使用 /挑战Boss 来进行挑战。"
        )
        return True, msg, boss

    async def auto_spawn_boss(self, player_count: int = 0) -> Tuple[bool, str, Optional[Boss]]:
        existing_boss = await self.db.ext.get_active_boss()
        if existing_boss:
            return False, "当前已有 Boss 存在。", None

        all_players = await self.db.get_all_players()
        if not all_players:
            level_config = self.levels[0]
            base_exp = 50000
        else:
            total_exp = sum(p.experience for p in all_players)
            avg_exp = total_exp // len(all_players) if all_players else 50000

            for config in reversed(self.levels):
                if avg_exp >= config.get("level_index", 0) * 10000:
                    level_config = config
                    break
            else:
                level_config = self.levels[0]

            base_exp = int(avg_exp * 1.2)

        return await self.spawn_boss(base_exp, level_config)

    async def _roll_boss_drops(self, player: Player, boss: Boss) -> List[Tuple[str, int]]:
        dropped_items = []

        boss_level_index = 0
        for level in self.levels:
            if level["name"] == boss.boss_level:
                boss_level_index = level["level_index"]
                break

        if boss_level_index <= 6:
            drop_table = self.BOSS_DROP_TABLE["low"]
        elif boss_level_index <= 12:
            drop_table = self.BOSS_DROP_TABLE["mid"]
        else:
            drop_table = self.BOSS_DROP_TABLE["high"]

        total_weight = sum(item["weight"] for item in drop_table)
        roll = random.randint(1, total_weight)

        current_weight = 0
        for item in drop_table:
            current_weight += item["weight"]
            if roll <= current_weight:
                count = random.randint(item["min"], item["max"])
                dropped_items.append((item["name"], count))
                break

        if boss_level_index >= 9:
            extra_chance = 50 if boss_level_index < 15 else 70
            if random.randint(1, 100) <= extra_chance:
                roll = random.randint(1, total_weight)
                current_weight = 0
                for item in drop_table:
                    current_weight += item["weight"]
                    if roll <= current_weight:
                        count = random.randint(item["min"], item["max"])
                        dropped_items.append((item["name"], count))
                        break

        return dropped_items
