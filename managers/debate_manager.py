"""论道管理器。"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from ..data import DataBase
from ..models import Player
from ..models_extended import UserStatus

__all__ = ["DebateManager"]


DEBATE_CONFIG = {
    "cooldown_seconds": 3600,
    "base_exp_reward": 500,
    "level_bonus_per_stage": 120,
    "mental_power_bonus_divisor": 25,
    "max_reward": 3000,
}


class DebateManager:
    """处理玩家之间的轻社交论道收益。"""

    COOLDOWN_KEY_PREFIX = "debate_cd_until"

    def __init__(self, db: DataBase):
        self.db = db

    def _cooldown_key(self, user_id: str) -> str:
        return f"{self.COOLDOWN_KEY_PREFIX}:{user_id}"

    async def _get_cooldown_until(self, user_id: str) -> int:
        raw_value = await self.db.ext.get_system_config(self._cooldown_key(user_id))
        if not raw_value:
            return 0

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return 0

        return max(0, value)

    async def _set_cooldown_until(self, user_id: str, cooldown_until: int):
        await self.db.ext.set_system_config(self._cooldown_key(user_id), str(max(0, int(cooldown_until))))

    async def _get_player_by_target(self, target_text: str) -> Player | None:
        target = await self.db.get_player_by_id(target_text)
        if target:
            return target
        return await self.db.get_player_by_name(target_text)

    async def _get_busy_status_name(self, user_id: str) -> str | None:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            return UserStatus.get_name(user_cd.type)

        if player.state and player.state != "空闲":
            return player.state

        return None

    def _calculate_reward(self, initiator: Player, target: Player) -> int:
        lower_level = min(initiator.level_index, target.level_index)
        average_mental_power = (max(0, initiator.mental_power) + max(0, target.mental_power)) // 2
        reward = (
            DEBATE_CONFIG["base_exp_reward"]
            + lower_level * DEBATE_CONFIG["level_bonus_per_stage"]
            + average_mental_power // DEBATE_CONFIG["mental_power_bonus_divisor"]
        )
        return min(DEBATE_CONFIG["max_reward"], max(DEBATE_CONFIG["base_exp_reward"], reward))

    async def debate(self, initiator: Player, target_text: str) -> Tuple[bool, str]:
        target = await self._get_player_by_target(target_text)
        if not target:
            return False, f"未找到目标玩家【{target_text}】。"

        if target.user_id == initiator.user_id:
            return False, "不能和自己论道。"

        initiator_busy = await self._get_busy_status_name(initiator.user_id)
        if initiator_busy:
            return False, f"你当前正在【{initiator_busy}】，暂时无法论道。"

        target_busy = await self._get_busy_status_name(target.user_id)
        if target_busy:
            return False, f"对方当前正在【{target_busy}】，暂时无法论道。"

        now = int(datetime.now().timestamp())
        initiator_cd = await self._get_cooldown_until(initiator.user_id)
        if initiator_cd > now:
            remaining = initiator_cd - now
            return False, f"你刚与人论道不久，还需等待 {remaining // 60} 分 {remaining % 60} 秒。"

        target_cd = await self._get_cooldown_until(target.user_id)
        if target_cd > now:
            remaining = target_cd - now
            return False, f"对方刚与人论道不久，还需等待 {remaining // 60} 分 {remaining % 60} 秒。"

        reward = self._calculate_reward(initiator, target)
        initiator.experience += reward
        target.experience += reward

        await self.db.update_player(initiator)
        await self.db.update_player(target)

        cooldown_until = now + DEBATE_CONFIG["cooldown_seconds"]
        await self._set_cooldown_until(initiator.user_id, cooldown_until)
        await self._set_cooldown_until(target.user_id, cooldown_until)

        initiator_name = initiator.user_name or f"道友{initiator.user_id[:6]}"
        target_name = target.user_name or f"道友{target.user_id[:6]}"
        cooldown_minutes = DEBATE_CONFIG["cooldown_seconds"] // 60

        return True, (
            "论道有所悟\n"
            "━━━━━━━━━━━━━━━\n"
            f"{initiator_name} 与 {target_name} 坐而论道，互相印证修行心得。\n"
            f"双方各获得修为：{reward:,}\n"
            f"双方进入论道冷却：{cooldown_minutes} 分钟\n"
            "━━━━━━━━━━━━━━━\n"
            "提示：论道为轻社交玩法，不会触发战斗或额外惩罚。"
        )
