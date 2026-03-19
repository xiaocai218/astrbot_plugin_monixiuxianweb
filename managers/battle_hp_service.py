"""Unified battle HP service used by Boss, PvP, display panels and Web preview."""

import time
from typing import Optional, Tuple

from ..battle_hp_utils import (
    BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY,
    BOSS_CHALLENGE_RECOVERY_KEY,
    BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY,
    merge_battle_hp_state,
    resolve_player_battle_hp_state,
)
from ..data import DataBase
from ..models import Player
from .combat_manager import CombatManager, CombatStats

__all__ = ["BattleHpService"]


class BattleHpService:
    """Provide one shared battle HP workflow for all battle-related entry points."""

    def __init__(self, db: DataBase, combat_mgr: CombatManager, config_manager=None):
        self.db = db
        self.combat_mgr = combat_mgr
        self.config_manager = config_manager

    async def get_or_create_user_cd(self, user_id: str):
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)
        return user_cd

    def calculate_equipment_bonus(self, player: Player) -> dict:
        bonus = {"atk": 0, "defense": 0}
        if not self.config_manager:
            return bonus

        if player.weapon and player.weapon in self.config_manager.weapons_data:
            data = self.config_manager.weapons_data[player.weapon]
            bonus["atk"] += data.get("atk", 0)
            bonus["atk"] += data.get("physical_damage", 0)
            bonus["atk"] += data.get("magic_damage", 0)

        if player.armor and player.armor in self.config_manager.items_data:
            data = self.config_manager.items_data[player.armor]
            bonus["defense"] += data.get("physical_defense", 0)
            bonus["defense"] += data.get("magic_defense", 0)

        return bonus

    async def resolve_player_battle_hp(self, player: Player, user_cd, max_hp: int) -> int:
        hp, _, _, _, resolved_extra_data, changed = resolve_player_battle_hp_state(
            player.hp,
            max_hp,
            user_cd.get_extra_data(),
        )
        if changed:
            user_cd.set_extra_data(merge_battle_hp_state(user_cd.get_extra_data(), resolved_extra_data))
            await self.db.ext.update_user_cd(user_cd)
        return hp

    async def resolve_player_battle_status(self, player: Player):
        impart_info = await self.db.ext.get_impart_info(player.user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        max_hp, _max_mp = self.combat_mgr.calculate_hp_mp(player.experience, hp_buff, 0.0)

        if max_hp <= 0:
            return player.hp, 0, False, 0

        user_cd = await self.get_or_create_user_cd(player.user_id)
        hp, battle_hp_max, recovery_enabled, cooldown_remaining, resolved_extra_data, changed = (
            resolve_player_battle_hp_state(
                player.hp if player.hp > 0 else max_hp,
                max_hp,
                user_cd.get_extra_data(),
            )
        )
        if changed:
            user_cd.set_extra_data(merge_battle_hp_state(user_cd.get_extra_data(), resolved_extra_data))
            await self.db.ext.update_user_cd(user_cd)

        if player.hp != hp:
            player.hp = hp
            await self.db.update_player(player)

        return hp, battle_hp_max, recovery_enabled, cooldown_remaining

    async def set_battle_hp_recovery(self, user_cd, base_hp: int, started_at: Optional[int] = None):
        extra_data = merge_battle_hp_state(user_cd.get_extra_data(), user_cd.get_extra_data())
        extra_data[BOSS_CHALLENGE_RECOVERY_KEY] = 1
        extra_data[BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY] = max(1, int(base_hp))
        extra_data[BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY] = int(started_at or time.time())
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    async def clear_battle_hp_recovery(self, user_cd):
        extra_data = merge_battle_hp_state(user_cd.get_extra_data(), user_cd.get_extra_data())
        extra_data.pop(BOSS_CHALLENGE_RECOVERY_KEY, None)
        extra_data.pop(BOSS_CHALLENGE_RECOVERY_BASE_HP_KEY, None)
        extra_data.pop(BOSS_CHALLENGE_RECOVERY_STARTED_AT_KEY, None)
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

    async def sync_battle_hp_recovery(self, user_cd, final_hp: int, max_hp: int):
        if final_hp < max_hp:
            await self.set_battle_hp_recovery(user_cd, final_hp)
        else:
            await self.clear_battle_hp_recovery(user_cd)

    async def prepare_combat_stats(
        self,
        user_id: str,
        *,
        include_equipment_bonus: bool = True,
        display_name_prefix: str = "道友",
    ) -> Tuple[CombatStats, object, Player]:
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return None, None, None

        user_cd = await self.get_or_create_user_cd(user_id)
        impart_info = await self.db.ext.get_impart_info(user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        mp_buff = impart_info.impart_mp_per if impart_info else 0.0
        atk_buff = impart_info.impart_atk_per if impart_info else 0.0
        crit_rate_buff = impart_info.impart_know_per if impart_info else 0.0

        max_hp, max_mp = self.combat_mgr.calculate_hp_mp(player.experience, hp_buff, mp_buff)
        hp = await self.resolve_player_battle_hp(player, user_cd, max_hp)
        mp = max(1, min(player.mp, max_mp)) if player.mp > 0 else max_mp
        atk = self.combat_mgr.calculate_atk(player.experience, player.atkpractice, atk_buff)
        defense = 0

        if include_equipment_bonus:
            equip_bonus = self.calculate_equipment_bonus(player)
            atk += equip_bonus["atk"]
            defense = equip_bonus["defense"]

        if player.hp != hp or player.mp != mp or player.atk != atk:
            player.hp = hp
            player.mp = mp
            player.atk = atk
            await self.db.update_player(player)

        stats = CombatStats(
            user_id=user_id,
            name=player.user_name if player.user_name else f"{display_name_prefix}{user_id[:6]}",
            hp=hp,
            max_hp=max_hp,
            mp=mp,
            max_mp=max_mp,
            atk=atk,
            defense=defense,
            crit_rate=int(crit_rate_buff * 100),
            exp=player.experience,
        )
        return stats, user_cd, player

