import random
import time

from ..data import DataBase
from ..models import Player

__all__ = ["FortuneManager"]

FORTUNE_CONFIG = {
    "daily_limit": 3,
    "trigger_chance": 0.08,
    "events": {
        "spirit_stone_rain": {
            "name": "灵石雨",
            "description": "天降灵石，福缘深厚。",
            "reward_type": "gold",
            "reward_range": [100, 500],
            "weight": 40,
        },
        "ancient_inheritance": {
            "name": "古人遗泽",
            "description": "偶得前人遗留的修炼心得。",
            "reward_type": "exp",
            "reward_range": [500, 2000],
            "weight": 30,
        },
        "spirit_spring": {
            "name": "灵泉涌现",
            "description": "发现一处灵泉，灵气充沛。",
            "reward_type": "qi",
            "reward_ratio": 0.5,
            "weight": 20,
        },
        "lifespan_blessing": {
            "name": "天赐寿元",
            "description": "福缘深厚，寿元增长。",
            "reward_type": "lifespan",
            "reward_range": [10, 50],
            "weight": 8,
        },
        "divine_artifact": {
            "name": "神器认主",
            "description": "一件神秘法器认可了你的气运。",
            "reward_type": "attribute",
            "attribute_bonus": {
                "physical_damage": [5, 20],
                "magic_damage": [5, 20],
                "physical_defense": [3, 15],
                "magic_defense": [3, 15],
            },
            "weight": 2,
        },
    },
}

FORTUNE_QUOTES = [
    "天道酬勤，福缘自来。",
    "积善之家，必有余庆。",
    "机缘巧合，造化弄人。",
    "冥冥之中，自有天意。",
    "祸兮福所倚，福兮祸所伏。",
]


class FortuneManager:
    """福缘管理器。"""

    def __init__(self, db: DataBase):
        self.db = db

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _config_key(self, user_id: str, day: str) -> str:
        return f"fortune_daily_{user_id}_{day}"

    async def _get_daily_count(self, user_id: str) -> int:
        day = self._today_key()
        value = await self.db.ext.get_system_config(self._config_key(user_id, day))
        return int(value or 0)

    async def _increment_daily_count(self, user_id: str) -> int:
        day = self._today_key()
        current = await self._get_daily_count(user_id)
        current += 1
        await self.db.ext.set_system_config(self._config_key(user_id, day), str(current))
        return current

    def _select_fortune_event(self) -> dict:
        events = FORTUNE_CONFIG["events"]
        total_weight = sum(item["weight"] for item in events.values())
        roll = random.randint(1, total_weight)
        current = 0
        for key, event in events.items():
            current += event["weight"]
            if roll <= current:
                return {"type": key, **event}
        return {"type": "spirit_stone_rain", **events["spirit_stone_rain"]}

    async def _apply_fortune_reward(self, player: Player, event: dict) -> str:
        reward_type = event["reward_type"]
        reward_msg = ""

        if reward_type == "gold":
            amount = random.randint(*event["reward_range"])
            player.gold += amount
            reward_msg = f"获得灵石：{amount:,}"
        elif reward_type == "exp":
            amount = random.randint(*event["reward_range"])
            amount = int(amount * (1 + player.level_index * 0.1))
            player.experience += amount
            reward_msg = f"获得修为：{amount:,}"
        elif reward_type == "qi":
            ratio = event["reward_ratio"]
            if player.cultivation_type == "体修":
                amount = int(player.max_blood_qi * ratio)
                player.blood_qi = min(player.max_blood_qi, player.blood_qi + amount)
                reward_msg = f"恢复气血：{amount:,}"
            else:
                amount = int(player.max_spiritual_qi * ratio)
                player.spiritual_qi = min(player.max_spiritual_qi, player.spiritual_qi + amount)
                reward_msg = f"恢复灵气：{amount:,}"
        elif reward_type == "lifespan":
            amount = random.randint(*event["reward_range"])
            player.lifespan += amount
            reward_msg = f"增加寿元：{amount}"
        elif reward_type == "attribute":
            reward_lines = ["属性提升："]
            attr_names = {
                "physical_damage": "物伤",
                "magic_damage": "法伤",
                "physical_defense": "物防",
                "magic_defense": "法防",
            }
            for attr, range_val in event["attribute_bonus"].items():
                amount = random.randint(*range_val)
                setattr(player, attr, getattr(player, attr, 0) + amount)
                reward_lines.append(f"  {attr_names.get(attr, attr)} +{amount}")
            reward_msg = "\n".join(reward_lines)

        await self.db.update_player(player)
        return reward_msg

    async def claim_daily_fortune(self, player: Player) -> tuple[bool, str]:
        daily_count = await self._get_daily_count(player.user_id)
        if daily_count >= FORTUNE_CONFIG["daily_limit"]:
            return False, f"今日福缘已用尽（{daily_count}/{FORTUNE_CONFIG['daily_limit']}），明日再来！"

        event = self._select_fortune_event()
        reward_msg = await self._apply_fortune_reward(player, event)
        used_count = await self._increment_daily_count(player.user_id)
        remaining = max(0, FORTUNE_CONFIG["daily_limit"] - used_count)

        msg = (
            "🍀 福缘降临！🍀\n"
            "━━━━━━━━━━━━━━\n"
            f"{event['name']}\n"
            f"{event['description']}\n"
            f"“{random.choice(FORTUNE_QUOTES)}”\n"
            "━━━━━━━━━━━━━━\n"
            f"{reward_msg}\n"
            f"\n今日剩余福缘次数：{remaining}"
        )
        return True, msg

    async def get_fortune_info(self, player: Player) -> str:
        daily_count = await self._get_daily_count(player.user_id)
        remaining = max(0, FORTUNE_CONFIG["daily_limit"] - daily_count)

        info = (
            "🍀 福缘信息\n"
            "━━━━━━━━━━━━━━\n"
            f"今日已触发：{daily_count}次\n"
            f"今日剩余：{remaining}次\n"
            f"主动求福缘每日上限：{FORTUNE_CONFIG['daily_limit']}次\n"
            f"参考随机触发概率：{FORTUNE_CONFIG['trigger_chance']:.0%}\n"
            "\n【福缘类型】\n"
        )
        for event in FORTUNE_CONFIG["events"].values():
            info += f"  {event['name']}：{event['description']}\n"

        info += "\n提示：使用 /求福缘 可主动触发福缘。"
        return info
