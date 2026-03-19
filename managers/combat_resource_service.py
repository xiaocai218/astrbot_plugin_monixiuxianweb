"""战斗资源服务：统一处理体修气血 / 灵修灵气的战斗发起消耗。"""

from dataclasses import dataclass
from typing import Dict, Tuple

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["CombatResourceCost", "CombatResourceService"]


@dataclass(frozen=True)
class CombatResourceCost:
    mode: str
    ratio: float
    minimum: int


class CombatResourceService:
    """统一计算和扣除战斗入口资源。"""

    COST_CONFIG: Dict[str, CombatResourceCost] = {
        "spar": CombatResourceCost(mode="spar", ratio=0.03, minimum=30),
        "duel": CombatResourceCost(mode="duel", ratio=0.05, minimum=50),
        "boss": CombatResourceCost(mode="boss", ratio=0.08, minimum=80),
        "impart": CombatResourceCost(mode="impart", ratio=0.10, minimum=100),
    }

    MODE_LABELS = {
        "spar": "切磋",
        "duel": "决斗",
        "boss": "挑战世界Boss",
        "impart": "传承挑战",
    }

    def __init__(self, db: DataBase):
        self.db = db

    def get_resource_name(self, player: Player) -> str:
        return "气血" if player.cultivation_type == "体修" else "灵气"

    def get_resource_values(self, player: Player) -> Tuple[int, int]:
        if player.cultivation_type == "体修":
            current = int(player.blood_qi or 0)
            maximum = int(player.max_blood_qi or 0)
        else:
            current = int(player.spiritual_qi or 0)
            maximum = int(player.max_spiritual_qi or 0)
        maximum = max(maximum, current, 1)
        current = max(0, current)
        return current, maximum

    def get_entry_cost(self, player: Player, mode: str) -> int:
        config = self.COST_CONFIG[mode]
        _current, maximum = self.get_resource_values(player)
        return max(config.minimum, int(maximum * config.ratio))

    def check_entry_cost(self, player: Player, mode: str) -> Tuple[bool, str, int]:
        current, maximum = self.get_resource_values(player)
        cost = self.get_entry_cost(player, mode)
        resource_name = self.get_resource_name(player)
        if current < cost:
            mode_label = self.MODE_LABELS.get(mode, "战斗")
            return (
                False,
                (
                    f"{resource_name}不足，无法发起{mode_label}。\n"
                    f"当前{resource_name}：{current}/{maximum}\n"
                    f"本次需要{resource_name}：{cost}"
                ),
                cost,
            )
        return True, "", cost

    async def consume_entry_cost(self, player: Player, mode: str) -> Tuple[bool, str, int]:
        ok, msg, cost = self.check_entry_cost(player, mode)
        if not ok:
            return False, msg, cost

        if player.cultivation_type == "体修":
            player.blood_qi = max(0, player.blood_qi - cost)
        else:
            player.spiritual_qi = max(0, player.spiritual_qi - cost)
        await self.db.update_player(player)

        resource_name = self.get_resource_name(player)
        mode_label = self.MODE_LABELS.get(mode, "战斗")
        current, maximum = self.get_resource_values(player)
        return (
            True,
            f"{mode_label}消耗{resource_name}：{cost}（当前{resource_name}：{current}/{maximum}）",
            cost,
        )
