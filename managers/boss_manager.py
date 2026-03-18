"""
Boss 系统管理器。

负责处理世界 Boss 的生成、挑战、奖励和掉落逻辑。
"""

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
    calculate_recovering_boss_hp,
    resolve_boss_battle_hp_state,
)
from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import Boss, UserStatus
from .combat_manager import CombatManager, CombatStats

if TYPE_CHECKING:
    from ..core import StorageRingManager


class BossManager:
    """Boss 系统管理器。"""

    BOSS_LEVELS = [
        {"name": "练气", "level_index": 0, "hp_mult": 1.0, "atk_mult": 1.0, "reward_mult": 1.0},
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
            {"name": "星辰石", "weight": 25, "min": 2, "max": 4},
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
        self.config = config_manager.boss_config if config_manager else {}
        self.levels = self.config.get("levels", self.BOSS_LEVELS)

    async def _get_boss_cooldown_remaining(self, user_cd) -> int:
        """返回玩家世界 Boss 挑战冷却剩余秒数。"""
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
        """写入玩家世界 Boss 挑战冷却。"""
        extra_data = user_cd.get_extra_data()
        extra_data[self.BOSS_CHALLENGE_COOLDOWN_KEY] = cooldown_until
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    async def _set_boss_hp_recovery(self, user_cd, base_hp: int, started_at: Optional[int] = None):
        """Store the post-battle HP recovery anchor for Boss fights."""
        extra_data = user_cd.get_extra_data()
        extra_data[self.BOSS_CHALLENGE_RECOVERY_KEY] = 1
        extra_data[self.BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY] = max(1, int(base_hp))
        extra_data[self.BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY] = int(started_at or time.time())
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    async def _clear_boss_hp_recovery(self, user_cd):
        """Clear the Boss fight HP recovery anchor."""
        extra_data = user_cd.get_extra_data()
        extra_data.pop(self.BOSS_CHALLENGE_RECOVERY_KEY, None)
        extra_data.pop(self.BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY, None)
        extra_data.pop(self.BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY, None)
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    def _calculate_recovering_boss_hp(self, base_hp: int, max_hp: int, started_at: int) -> Tuple[int, bool]:
        """Recover 10% of max HP per minute, fully recovered after 10 minutes."""
        return calculate_recovering_boss_hp(base_hp, max_hp, started_at)

    async def _resolve_boss_battle_hp(self, player: Player, user_cd, max_hp: int) -> int:
        """Resolve current battle HP from saved recovery state."""
        hp, _, _, resolved_extra_data, changed = resolve_boss_battle_hp_state(
            player.hp,
            max_hp,
            user_cd.get_extra_data(),
        )
        if changed:
            user_cd.set_extra_data(resolved_extra_data)
            await self.db.ext.update_user_cd(user_cd)
        return hp

    async def spawn_boss(
        self,
        base_exp: int = 100000,
        level_config: Optional[Dict] = None,
    ) -> Tuple[bool, str, Optional[Boss]]:
        """生成一个新的世界 Boss。"""
        existing_boss = await self.db.ext.get_active_boss()
        if existing_boss:
            return False, f"❌ 当前已有 Boss【{existing_boss.boss_name}】存在！", None

        if not level_config:
            level_config = random.choice(self.levels)

        boss_name = random.choice(self.BOSS_NAMES) + f"·{level_config['name']}境"
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

        msg = f"""
👹 Boss降临
━━━━━━━━━━━━
{boss_name}降临世间！
境界：{level_config["name"]}
HP：{max_hp}
ATK：{atk}
减伤：{defense}%
奖励：{stone_reward}灵石

快来挑战吧！
        """.strip()

        return True, msg, boss

    async def challenge_boss(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """挑战当前世界 Boss。"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！", None

        boss = await self.db.ext.get_active_boss()
        if not boss:
            return False, "❌ 当前没有Boss！", None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)

        if user_cd.type != UserStatus.IDLE:
            return False, "❌ 你当前正忙，无法挑战Boss！", None

        impart_info = await self.db.ext.get_impart_info(user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        mp_buff = impart_info.impart_mp_per if impart_info else 0.0
        atk_buff = impart_info.impart_atk_per if impart_info else 0.0
        crit_rate_buff = impart_info.impart_know_per if impart_info else 0.0

        max_hp, max_mp = self.combat_mgr.calculate_hp_mp(player.experience, hp_buff, mp_buff)
        atk = self.combat_mgr.calculate_atk(player.experience, player.atkpractice, atk_buff)

        hp = await self._resolve_boss_battle_hp(player, user_cd, max_hp)
        mp = max(1, min(player.mp, max_mp)) if player.mp > 0 else max_mp

        if player.hp != hp or player.mp != mp or player.atk != atk:
            player.hp = hp
            player.mp = mp
            player.atk = atk
            await self.db.update_player(player)

        cooldown_remaining = await self._get_boss_cooldown_remaining(user_cd)
        if cooldown_remaining > 0:
            hp_percent = (hp / max_hp) * 100 if max_hp > 0 else 0
            minutes = cooldown_remaining // 60
            seconds = cooldown_remaining % 60
            return False, (
                f"\u274c \u4f60\u521a\u521a\u88ab\u4e16\u754cBoss\u51fb\u8d25\uff0c5\u5206\u949f\u5185\u65e0\u6cd5\u518d\u6b21\u6311\u6218\u3002\n"
                f"\u5f53\u524d\u6218\u6597HP\uff1a{hp}/{max_hp}\uff08{hp_percent:.0f}%\uff09\n"
                f"\u8fd8\u9700\u7b49\u5f85 {minutes}\u5206{seconds}\u79d2 \u540e\u624d\u80fd\u518d\u6b21\u6311\u6218\u3002\n"
                f"\u6218\u6597HP\u6bcf\u5206\u949f\u6062\u590d10%\uff0c\u7ea610\u5206\u949f\u6062\u590d\u6ee1\u8840\u3002"
            ), None

        player_stats = CombatStats(
            user_id=user_id,
            name=player.user_name if player.user_name else f"道友{user_id[:6]}",
            hp=hp,
            max_hp=int(player.experience * (1 + hp_buff) // 2),
            mp=mp,
            max_mp=int(player.experience * (1 + mp_buff)),
            atk=atk,
            defense=0,
            crit_rate=int(crit_rate_buff * 100),
            exp=player.experience,
        )

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

        battle_result = self.combat_mgr.player_vs_boss(player_stats, boss_stats)
        winner = battle_result["winner"]
        reward = battle_result["reward"]
        gold_gain = 0

        if winner == user_id:
            boss.status = 0
            await self.db.ext.defeat_boss(boss.boss_id)
            gold_gain += reward

            item_msg = ""
            dropped_items = []
            if self.storage_ring_manager:
                dropped_items = await self._roll_boss_drops(player, boss)
                if dropped_items:
                    item_lines = []
                    for item_name, count in dropped_items:
                        success, _ = await self.storage_ring_manager.store_item(player, item_name, count, silent=True)
                        if success:
                            item_lines.append(f"  · {item_name} x{count}")
                        else:
                            item_lines.append(f"  · {item_name} x{count}（储物戒已满，丢失）")
                    if item_lines:
                        item_msg = "\n\n🎁 获得物品：\n" + "\n".join(item_lines)

            final_hp = battle_result["player_final_hp"]
            recovery_msg = ""
            if final_hp < player_stats.max_hp:
                recovery_msg = "\n\u6218\u6597HP\u5c06\u7ee7\u7eed\u6309\u6bcf\u5206\u949f\u6062\u590d10%\u7684\u901f\u5ea6\u81ea\u52a8\u6062\u590d\uff0c\u76f4\u5230\u6ee1\u8840\u3002"

            result_msg = f"""
🎉 挑战成功
━━━━━━━━━━━━
你成功击败了【{boss.boss_name}】！

战斗回合数：{battle_result['rounds']}
获得灵石：{reward}{item_msg}

{player_stats.name}
HP：{final_hp}/{player_stats.max_hp}{recovery_msg}
            """.strip()
        else:
            boss.hp = battle_result["boss_final_hp"]
            await self.db.ext.update_boss(boss)

            final_hp = 1
            cooldown_until = int(time.time()) + self.BOSS_CHALLENGE_COOLDOWN_SECONDS
            await self._set_boss_challenge_cooldown(user_cd, cooldown_until)

            result_msg = f"""
💀 挑战失败
━━━━━━━━━━━━
你被【{boss.boss_name}】击败了！
战斗回合数：{battle_result['rounds']}
安慰奖：{reward}灵石

{boss.boss_name} 剩余HP：{boss.hp}/{boss.max_hp}
你已经被击败，气血正在恢复，5分钟后才能再次挑战Boss！
            """.strip()

            if reward > 0:
                gold_gain += reward

        player = await self.db.get_player_by_id(user_id)
        player.gold += gold_gain
        player.hp = final_hp
        player.mp = battle_result["player_final_mp"]
        await self.db.update_player(player)

        if final_hp < player_stats.max_hp:
            await self._set_boss_hp_recovery(user_cd, final_hp)
        else:
            await self._clear_boss_hp_recovery(user_cd)

        combat_log = "\n".join(battle_result["combat_log"])
        full_msg = combat_log + "\n\n" + result_msg
        return True, full_msg, battle_result

    async def get_boss_info(self) -> Tuple[bool, str, Optional[Boss]]:
        """获取当前世界 Boss 信息。"""
        boss = await self.db.ext.get_active_boss()
        if not boss:
            return False, "❌ 当前没有Boss！", None

        hp_percent = (boss.hp / boss.max_hp) * 100
        msg = f"""
👹 当前Boss
━━━━━━━━━━━━
名称：{boss.boss_name}
境界：{boss.boss_level}

HP：{boss.hp}/{boss.max_hp} ({hp_percent:.1f}%)
ATK：{boss.atk}
减伤：{boss.defense}%

奖励：{boss.stone_reward}灵石

使用 /挑战Boss 来挑战！
        """.strip()
        return True, msg, boss

    async def auto_spawn_boss(self, player_count: int = 0) -> Tuple[bool, str, Optional[Boss]]:
        """根据玩家整体水平自动生成 Boss。"""
        existing_boss = await self.db.ext.get_active_boss()
        if existing_boss:
            return False, "当前已有Boss存在", None

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
        """根据 Boss 等级随机掉落物品。"""
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
