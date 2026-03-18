import random
import time

from ..data import DataBase
from ..models import Player

__all__ = ["EnlightenmentManager"]

ENLIGHTENMENT_CONFIG = {
    "trigger_chance": 0.15,
    "cooldown": 3600,
    "mental_power_bonus": {
        "threshold": 1000,
        "bonus": 0.01,
        "max_bonus": 0.15,
    },
    "types": {
        "minor": {"name": "小悟", "description": "灵光一闪，略有所悟。", "exp_bonus_ratio": 0.05, "weight": 60},
        "normal": {"name": "顿悟", "description": "道心通明，念头豁然贯通。", "exp_bonus_ratio": 0.15, "weight": 30},
        "major": {"name": "大彻大悟", "description": "天地共鸣，道法自然。", "exp_bonus_ratio": 0.30, "weight": 8},
        "supreme": {
            "name": "天人合一",
            "description": "身与道合，神游天地。",
            "exp_bonus_ratio": 0.50,
            "attribute_bonus": True,
            "weight": 2,
        },
    },
}

ENLIGHTENMENT_QUOTES = [
    "道可道，非常道。",
    "上善若水，水善利万物而不争。",
    "天地不仁，以万物为刍狗。",
    "大音希声，大象无形。",
    "大道至简，返璞归真。",
    "心若止水，万象归一。",
    "一花一世界，一叶一菩提。",
    "致虚极，守静笃。",
]


class EnlightenmentManager:
    """悟道管理器。"""

    def __init__(self, db: DataBase):
        self.db = db

    def _last_key(self, user_id: str) -> str:
        return f"enlightenment_last_{user_id}"

    def _get_trigger_chance(self, player: Player) -> float:
        base_chance = ENLIGHTENMENT_CONFIG["trigger_chance"]
        mental_cfg = ENLIGHTENMENT_CONFIG["mental_power_bonus"]
        mental_bonus = min(
            (player.mental_power // mental_cfg["threshold"]) * mental_cfg["bonus"],
            mental_cfg["max_bonus"],
        )
        return min(0.50, base_chance + mental_bonus)

    async def _get_last_time(self, player: Player) -> int:
        value = await self.db.ext.get_system_config(self._last_key(player.user_id))
        return int(value or 0)

    async def _check_cooldown(self, player: Player) -> bool:
        last_time = await self._get_last_time(player)
        return time.time() - last_time >= ENLIGHTENMENT_CONFIG["cooldown"]

    async def _mark_triggered(self, player: Player):
        await self.db.ext.set_system_config(self._last_key(player.user_id), str(int(time.time())))

    def _select_enlightenment_type(self, player: Player) -> dict:
        types = ENLIGHTENMENT_CONFIG["types"]
        weights = {key: value["weight"] for key, value in types.items()}
        if player.level_index >= 20:
            weights["major"] += 5
            weights["supreme"] += 2
        elif player.level_index >= 13:
            weights["normal"] += 10
            weights["major"] += 3

        total_weight = sum(weights.values())
        roll = random.randint(1, total_weight)
        current = 0
        for key, weight in weights.items():
            current += weight
            if roll <= current:
                return {"type": key, **types[key]}
        return {"type": "minor", **types["minor"]}

    async def try_enlightenment(self, player: Player, cultivation_exp: int) -> tuple[bool, str, int]:
        if not await self._check_cooldown(player):
            return False, "", 0
        if random.random() > self._get_trigger_chance(player):
            return False, "", 0

        enlightenment = self._select_enlightenment_type(player)
        bonus_exp = int(cultivation_exp * enlightenment["exp_bonus_ratio"])
        await self._mark_triggered(player)

        lines = [
            f"📖 {enlightenment['name']}",
            "━━━━━━━━━━━━━━",
            f"“{random.choice(ENLIGHTENMENT_QUOTES)}”",
            "",
            enlightenment["description"],
            f"额外获得修为：{bonus_exp:,}",
        ]

        if enlightenment.get("attribute_bonus"):
            attr_bonus = max(1, player.mental_power // 100)
            player.mental_power += attr_bonus
            player.physical_defense += attr_bonus // 2
            player.magic_defense += attr_bonus // 2
            lines.extend(
                [
                    "",
                    "天人合一额外奖励：",
                    f"精神力 +{attr_bonus}",
                    f"物防/法防 +{attr_bonus // 2}",
                ]
            )

        return True, "\n".join(lines), bonus_exp

    async def get_enlightenment_info(self, player: Player) -> str:
        trigger_chance = self._get_trigger_chance(player)
        last_time = await self._get_last_time(player)
        cooldown_remaining = max(0, ENLIGHTENMENT_CONFIG["cooldown"] - int(time.time() - last_time)) if last_time else 0

        info = (
            "📖 悟道信息\n"
            "━━━━━━━━━━━━━━\n"
            f"当前悟道概率：{trigger_chance:.1%}\n"
            f"精神力：{player.mental_power:,}\n"
        )
        if cooldown_remaining > 0:
            minutes = cooldown_remaining // 60
            seconds = cooldown_remaining % 60
            info += f"冷却剩余：{minutes}分{seconds}秒\n"
        else:
            info += "状态：可触发悟道\n"

        info += (
            "\n【悟道类型】\n"
            "  小悟：额外 5% 修为\n"
            "  顿悟：额外 15% 修为\n"
            "  大彻大悟：额外 30% 修为\n"
            "  天人合一：额外 50% 修为，并提升属性\n"
            "\n提示：闭关出关时有概率触发悟道，精神力越高越容易触发。"
        )
        return info
