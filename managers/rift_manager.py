"""
秘境系统管理器 - 处理秘境探索、开放状态与奖励逻辑。
"""

import json
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import Rift, UserStatus

if TYPE_CHECKING:
    from ..core import StorageRingManager


class RiftManager:
    """秘境系统管理器"""

    DEFAULT_DURATION = 1800

    RIFT_DROP_TABLE = {
        1: [
            {"name": "灵草", "weight": 40, "min": 2, "max": 5},
            {"name": "精铁", "weight": 30, "min": 1, "max": 3},
            {"name": "灵石碎片", "weight": 30, "min": 3, "max": 8},
        ],
        2: [
            {"name": "灵草", "weight": 30, "min": 3, "max": 7},
            {"name": "玄铁", "weight": 25, "min": 2, "max": 4},
            {"name": "灵兽毛皮", "weight": 20, "min": 1, "max": 3},
            {"name": "功法残页", "weight": 15, "min": 1, "max": 1},
            {"name": "秘境精华", "weight": 10, "min": 1, "max": 2},
        ],
        3: [
            {"name": "玄铁", "weight": 25, "min": 3, "max": 6},
            {"name": "星陨石", "weight": 20, "min": 2, "max": 4},
            {"name": "灵兽内丹", "weight": 20, "min": 1, "max": 2},
            {"name": "功法残页", "weight": 20, "min": 1, "max": 2},
            {"name": "天材地宝", "weight": 15, "min": 1, "max": 1},
        ],
        4: [
            {"name": "星陨石", "weight": 30, "min": 2, "max": 5},
            {"name": "灵兽内丹", "weight": 25, "min": 2, "max": 3},
            {"name": "秘境精华", "weight": 20, "min": 2, "max": 4},
            {"name": "天材地宝", "weight": 15, "min": 1, "max": 2},
            {"name": "混沌精华", "weight": 10, "min": 1, "max": 1},
        ],
        5: [
            {"name": "天材地宝", "weight": 30, "min": 1, "max": 2},
            {"name": "混沌精华", "weight": 25, "min": 1, "max": 2},
            {"name": "神兽之骨", "weight": 20, "min": 1, "max": 1},
            {"name": "功法残页", "weight": 15, "min": 2, "max": 3},
            {"name": "秘境精华", "weight": 10, "min": 3, "max": 5},
        ],
    }

    RIFT_PILL_DROP_TABLE = {
        1: [{"name": "三品凝神增益丹", "weight": 100, "min": 1, "max": 1}],
        2: [
            {"name": "三品凝神增益丹", "weight": 50, "min": 1, "max": 1},
            {"name": "四品破境增益丹", "weight": 40, "min": 1, "max": 1},
            {"name": "五品渡劫增益丹", "weight": 10, "min": 1, "max": 1},
        ],
        3: [
            {"name": "四品破境增益丹", "weight": 40, "min": 1, "max": 1},
            {"name": "五品渡劫增益丹", "weight": 30, "min": 1, "max": 1},
            {"name": "六品破虚增益丹", "weight": 20, "min": 1, "max": 1},
            {"name": "七品化神增益丹", "weight": 10, "min": 1, "max": 1},
        ],
        4: [
            {"name": "五品渡劫增益丹", "weight": 40, "min": 1, "max": 1},
            {"name": "六品破虚增益丹", "weight": 35, "min": 1, "max": 1},
            {"name": "七品化神增益丹", "weight": 25, "min": 1, "max": 1},
        ],
        5: [
            {"name": "六品破虚增益丹", "weight": 45, "min": 1, "max": 1},
            {"name": "七品化神增益丹", "weight": 35, "min": 1, "max": 1},
            {"name": "八品圣元增益丹", "weight": 20, "min": 1, "max": 1},
        ],
    }

    RIFT_PILL_DROP_CHANCE = {1: 3, 2: 5, 3: 10, 4: 12, 5: 15}

    def __init__(self, db: DataBase, config_manager=None, storage_ring_manager: "StorageRingManager" = None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_manager = storage_ring_manager
        self.config = config_manager.rift_config if config_manager else {}
        self.explore_duration = self.config.get("default_duration", self.DEFAULT_DURATION)

    def _get_level_name(self, level_index: int) -> str:
        if self.config_manager and hasattr(self.config_manager, "level_data"):
            if 0 <= level_index < len(self.config_manager.level_data):
                return self.config_manager.level_data[level_index].get("level_name", f"境界{level_index}")

        level_names = [
            "练气期一层", "练气期二层", "练气期三层", "练气期四层", "练气期五层",
            "练气期六层", "练气期七层", "练气期八层", "练气期九层", "练气期十层",
            "筑基期初期", "筑基期中期", "筑基期后期", "金丹期初期", "金丹期中期", "金丹期后期",
        ]
        if 0 <= level_index < len(level_names):
            return level_names[level_index]
        return f"境界{level_index}"

    def _get_open_refresh_interval(self) -> int:
        interval = int(self.config.get("open_refresh_interval", 3600) or 3600)
        return max(300, interval)

    def _get_open_chance_by_level(self, rift_level: int) -> int:
        chances = self.config.get("open_chances_by_level", {})
        chance = chances.get(str(rift_level), chances.get(rift_level, 30))
        try:
            chance_value = int(chance)
        except (TypeError, ValueError):
            chance_value = 30
        return max(0, min(100, chance_value))

    def _ensure_always_open_rifts(self, all_rifts: List[Rift], open_rifts: List[Rift]) -> List[Rift]:
        open_map = {rift.rift_id: rift for rift in open_rifts}
        for rift in all_rifts:
            if rift.rift_id == 1 or rift.rift_name == "青云秘境":
                open_map[rift.rift_id] = rift
        return sorted(open_map.values(), key=lambda item: (item.rift_level, item.rift_id))

    async def _get_current_open_rifts(self, all_rifts: List[Rift]) -> Tuple[List[Rift], int]:
        if not all_rifts:
            return [], 0

        now = int(time.time())
        open_ids_raw = await self.db.ext.get_system_config("rift_open_ids")
        next_refresh_raw = await self.db.ext.get_system_config("rift_open_next_refresh")

        if open_ids_raw and next_refresh_raw:
            try:
                next_refresh = int(next_refresh_raw)
                open_ids = set(json.loads(open_ids_raw))
                if now < next_refresh:
                    open_rifts = [rift for rift in all_rifts if rift.rift_id in open_ids]
                    if open_rifts:
                        return self._ensure_always_open_rifts(all_rifts, open_rifts), next_refresh
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        open_rifts = []
        for rift in all_rifts:
            if random.randint(1, 100) <= self._get_open_chance_by_level(rift.rift_level):
                open_rifts.append(rift)

        if not open_rifts:
            open_rifts = [min(all_rifts, key=lambda item: (item.rift_level, item.rift_id))]

        open_rifts = self._ensure_always_open_rifts(all_rifts, open_rifts)

        next_refresh = now + self._get_open_refresh_interval()
        await self.db.ext.set_system_config(
            "rift_open_ids",
            json.dumps([rift.rift_id for rift in open_rifts], ensure_ascii=False),
        )
        await self.db.ext.set_system_config("rift_open_next_refresh", str(next_refresh))
        return open_rifts, next_refresh

    async def list_rifts(self) -> Tuple[bool, str]:
        all_rifts = await self.db.ext.get_all_rifts()
        rifts, next_refresh = await self._get_current_open_rifts(all_rifts)

        if not all_rifts:
            return False, "❌ 当前没有秘境数据！"

        msg = "🌀 秘境列表\n"
        msg += "━━━━━━━━━━\n"
        msg += "【本轮开放】\n"

        for rift in rifts:
            rewards_dict = rift.get_rewards()
            exp_range = rewards_dict.get("exp", [0, 0])
            gold_range = rewards_dict.get("gold", [0, 0])
            level_name = self._get_level_name(rift.required_level)

            msg += f"【{rift.rift_name}】(ID:{rift.rift_id})\n"
            if rift.required_level == 0:
                msg += "  等级要求：无限制\n"
            else:
                msg += f"  等级要求：{level_name} 及以上\n"
            msg += f"  修为奖励：{exp_range[0]:,}-{exp_range[1]:,}\n"
            msg += f"  灵石奖励：{gold_range[0]:,}-{gold_range[1]:,}\n"
            msg += f"  开放概率：{self._get_open_chance_by_level(rift.rift_level)}%\n\n"

        closed_rifts = [rift for rift in all_rifts if all(open_rift.rift_id != rift.rift_id for open_rift in rifts)]
        if closed_rifts:
            msg += "【暂未开放】\n"
            for rift in closed_rifts:
                level_name = self._get_level_name(rift.required_level)
                msg += f"  [{rift.rift_id}] {rift.rift_name}"
                if rift.required_level == 0:
                    msg += " - 暂未开放\n"
                else:
                    msg += f" - 需 {level_name}，暂未开放\n"
            msg += "\n"

        remaining = max(0, next_refresh - int(time.time()))
        msg += f"🔁 下一轮刷新：约 {remaining // 60} 分钟后\n"
        msg += "💡 使用 /探索秘境 <ID> 进入（如：/探索秘境 1）"
        return True, msg

    async def enter_rift(self, user_id: str, rift_id: int) -> Tuple[bool, str]:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！"

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)

        if user_cd.type != UserStatus.IDLE:
            return False, f"❌ 你当前正{UserStatus.get_name(user_cd.type)}，无法探索秘境！"

        rift = await self.db.ext.get_rift_by_id(rift_id)
        if not rift:
            return False, "❌ 秘境不存在！使用 /秘境列表 查看可用秘境"

        open_rifts, next_refresh = await self._get_current_open_rifts(await self.db.ext.get_all_rifts())
        if not any(open_rift.rift_id == rift_id for open_rift in open_rifts):
            remaining = max(0, next_refresh - int(time.time()))
            return False, f"❌ 该秘境当前未开放，请等待约 {remaining // 60} 分钟后查看下一轮开放情况"

        if player.level_index < rift.required_level:
            level_name = self._get_level_name(rift.required_level)
            return False, f"❌ 探索【{rift.rift_name}】需要达到【{level_name}】！"

        scheduled_time = int(time.time()) + self.explore_duration
        extra_data = {"rift_id": rift_id, "rift_level": rift.rift_level}
        await self.db.ext.set_user_busy(user_id, UserStatus.EXPLORING, scheduled_time, extra_data)

        return True, (
            f"✅ 你进入了【{rift.rift_name}】！探索需要 {self.explore_duration // 60} 分钟。\n"
            "使用 /完成探索 领取奖励"
        )

    async def finish_exploration(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！", None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.EXPLORING:
            return False, "❌ 你当前不在探索秘境！", None

        current_time = int(time.time())
        if current_time < user_cd.scheduled_time:
            remaining = user_cd.scheduled_time - current_time
            return False, f"❌ 探索尚未完成！还需要 {remaining // 60} 分钟。", None

        extra_data = user_cd.get_extra_data() if hasattr(user_cd, "get_extra_data") else {}
        rift_id = extra_data.get("rift_id", 0)
        rift_level = extra_data.get("rift_level", 1)

        rift = await self.db.ext.get_rift_by_id(rift_id) if rift_id else None
        rift_name = rift.rift_name if rift else "未知秘境"

        if rift:
            rewards_config = rift.get_rewards()
            exp_range = rewards_config.get("exp", [1000, 5000])
            gold_range = rewards_config.get("gold", [500, 2000])
            exp_reward = random.randint(exp_range[0], exp_range[1])
            gold_reward = random.randint(gold_range[0], gold_range[1])
            rift_level = rift.rift_level
        else:
            exp_reward = random.randint(1000, 5000)
            gold_reward = random.randint(500, 2000)

        events = [
            {"desc": "你发现了一处灵泉，修为大增！", "item_chance": 70},
            {"desc": "你在秘境中击败了一只妖兽！", "item_chance": 80},
            {"desc": "你找到了一个隐藏的宝箱！", "item_chance": 100},
            {"desc": "你领悟了一些修炼心得。", "item_chance": 40},
            {"desc": "你在秘境中遇到了前辈留下的传承！", "item_chance": 90},
        ]
        event = random.choice(events)

        dropped_items = await self._roll_rift_drops(player, rift_level, event["item_chance"])
        item_msg = ""
        if dropped_items:
            item_lines = []
            for item_name, count in dropped_items:
                if self._is_pill_item(item_name):
                    inventory = player.get_pills_inventory()
                    inventory[item_name] = inventory.get(item_name, 0) + count
                    player.set_pills_inventory(inventory)
                    item_lines.append(f"  - {item_name} x{count}（丹药背包）")
                elif self.storage_ring_manager:
                    success, _ = await self.storage_ring_manager.store_item(player, item_name, count, silent=True)
                    if success:
                        item_lines.append(f"  - {item_name} x{count}")
                    else:
                        item_lines.append(f"  - {item_name} x{count}（储物戒已满，丢失）")
                else:
                    item_lines.append(f"  - {item_name} x{count}（无法存储）")

            if item_lines:
                item_msg = "\n\n🎁 获得物品：\n" + "\n".join(item_lines)

        player.experience += exp_reward
        player.gold += gold_reward
        await self.db.update_player(player)
        await self.db.ext.set_user_free(user_id)

        msg = (
            f"🌀 探索完成 - {rift_name}\n"
            f"━━━━━━━━━━\n"
            f"{event['desc']}\n\n"
            f"获得修为：+{exp_reward:,}\n"
            f"获得灵石：+{gold_reward:,}{item_msg}"
        )

        reward_data = {
            "exp": exp_reward,
            "gold": gold_reward,
            "event": event["desc"],
            "items": dropped_items,
            "rift_name": rift_name,
        }
        return True, msg, reward_data

    async def exit_rift(self, user_id: str) -> Tuple[bool, str]:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！"

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.EXPLORING:
            return False, "❌ 你当前不在探索秘境！"

        await self.db.ext.set_user_free(user_id)
        return True, "✅ 你已退出秘境，本次探索未获得任何奖励。"

    def _is_pill_item(self, item_name: str) -> bool:
        if self.config_manager and hasattr(self.config_manager, "is_pill"):
            return self.config_manager.is_pill(item_name)
        return False

    def _get_rift_level_by_player(self, player: Player) -> int:
        level_index = player.level_index
        if level_index <= 5:
            return 1
        if level_index <= 12:
            return 2
        if level_index <= 18:
            return 3
        if level_index <= 24:
            return 4
        return 5

    async def _roll_rift_drops(self, player: Player, rift_level: int, item_chance: int) -> List[Tuple[str, int]]:
        dropped_items = []
        if random.randint(1, 100) > item_chance:
            return dropped_items

        drop_table = self.RIFT_DROP_TABLE.get(rift_level, self.RIFT_DROP_TABLE[min(self.RIFT_DROP_TABLE.keys())])
        total_weight = sum(item["weight"] for item in drop_table)
        roll = random.randint(1, total_weight)

        current_weight = 0
        for item in drop_table:
            current_weight += item["weight"]
            if roll <= current_weight:
                dropped_items.append((item["name"], random.randint(item["min"], item["max"])))
                break

        if rift_level >= 3 and random.randint(1, 100) <= 50:
            roll = random.randint(1, total_weight)
            current_weight = 0
            for item in drop_table:
                current_weight += item["weight"]
                if roll <= current_weight:
                    dropped_items.append((item["name"], random.randint(item["min"], item["max"])))
                    break

        dropped_items.extend(self._roll_pill_drops(rift_level))
        return dropped_items

    def _roll_pill_drops(self, rift_level: int) -> List[Tuple[str, int]]:
        pill_chance = self.RIFT_PILL_DROP_CHANCE.get(rift_level, 3)
        if random.randint(1, 100) > pill_chance:
            return []

        drop_table = self.RIFT_PILL_DROP_TABLE.get(rift_level)
        if not drop_table:
            return []

        total_weight = sum(item["weight"] for item in drop_table)
        roll = random.randint(1, total_weight)
        current_weight = 0
        for item in drop_table:
            current_weight += item["weight"]
            if roll <= current_weight:
                return [(item["name"], random.randint(item["min"], item["max"]))]
        return []
