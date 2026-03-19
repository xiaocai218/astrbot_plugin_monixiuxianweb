"""灵宠战斗效果服务。"""

from typing import Dict, Optional

from ..data import DataBase
from .pet_manager import PetManager

__all__ = ["PetBattleService"]


class PetBattleService:
    SKILL_VALUES = {
        "normal": {"heal": 0.02, "guard": 0.04, "inspire": 0.05, "gaze": 0.05, "rebirth": 0.15, "illusion": 0.08},
        "rare": {"heal": 0.03, "guard": 0.06, "inspire": 0.08, "gaze": 0.08, "rebirth": 0.20, "illusion": 0.12},
        "epic": {"heal": 0.04, "guard": 0.08, "inspire": 0.11, "gaze": 0.12, "rebirth": 0.25, "illusion": 0.16},
        "legendary": {"heal": 0.05, "guard": 0.10, "inspire": 0.15, "gaze": 0.15, "rebirth": 0.35, "illusion": 0.20},
    }

    def __init__(self, db: DataBase, pet_manager: Optional[PetManager] = None):
        self.db = db
        self.pet_manager = pet_manager or PetManager(db)

    async def build_battle_context(self, user_id: str) -> Optional[Dict]:
        pet = await self.pet_manager.get_equipped_pet(user_id)
        if not pet:
            return None

        rank = pet["rank"]
        values = self.SKILL_VALUES.get(rank, self.SKILL_VALUES["normal"])
        skills = [skill for skill in [pet.get("skill_1", ""), pet.get("skill_2", "")] if skill]
        return {
            "pet_name": pet["name"],
            "rank": rank,
            "rank_label": self.pet_manager.RANK_LABELS.get(rank, rank),
            "skills": skills,
            "skill_labels": [self.pet_manager.SKILL_LABELS.get(skill, skill) for skill in skills],
            "values": {skill: values.get(skill, 0.0) for skill in skills},
            "rounds_left": 5,
            "revive_used": False,
        }
