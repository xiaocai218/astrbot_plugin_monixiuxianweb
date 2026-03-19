"""传承挑战管理器。"""

import random
from typing import Dict, List, Tuple, Union

from ..data import DataBase
from ..models import Player
from ..models_extended import UserStatus
from .battle_hp_service import BattleHpService
from .combat_manager import CombatManager

__all__ = ["ImpartPkManager"]


class ImpartPkManager:
    """处理玩家之间的传承挑战。"""

    def __init__(self, db: DataBase, combat_mgr: CombatManager):
        self.db = db
        self.combat_mgr = combat_mgr
        self.battle_hp_service = BattleHpService(db, combat_mgr)

    async def _get_or_create_user_cd(self, user_id: str):
        return await self.battle_hp_service.get_or_create_user_cd(user_id)

    async def _build_combat_stats(self, player: Player):
        stats, user_cd, _latest_player = await self.battle_hp_service.prepare_combat_stats(
            player.user_id,
            include_equipment_bonus=False,
            display_name_prefix="道友",
        )
        return stats, user_cd

    async def challenge_impart(self, attacker: Player, defender: Player) -> Tuple[bool, str, dict]:
        """发起传承挑战。"""
        attacker_cd = await self._get_or_create_user_cd(attacker.user_id)
        defender_cd = await self._get_or_create_user_cd(defender.user_id)
        if attacker_cd.type != UserStatus.IDLE:
            return False, "你当前正忙，无法发起传承挑战。", {}
        if defender_cd.type != UserStatus.IDLE:
            return False, "对方当前正忙，无法进行传承挑战。", {}

        attacker_impart = await self.db.ext.get_impart_info(attacker.user_id)
        defender_impart = await self.db.ext.get_impart_info(defender.user_id)

        atk_stats, attacker_cd = await self._build_combat_stats(attacker)
        def_stats, defender_cd = await self._build_combat_stats(defender)
        if not atk_stats or not def_stats:
            return False, "挑战双方都需要已踏入修仙之路。", {}

        battle_result = self.combat_mgr.player_vs_player(atk_stats, def_stats, combat_type=2)
        attacker_final_hp = battle_result["player1_final_hp"]
        attacker_final_mp = battle_result["player1_final_mp"]
        defender_final_hp = battle_result["player2_final_hp"]
        defender_final_mp = battle_result["player2_final_mp"]

        await self.db.ext.update_player_hp_mp(attacker.user_id, attacker_final_hp, attacker_final_mp)
        await self.db.ext.update_player_hp_mp(defender.user_id, defender_final_hp, defender_final_mp)
        await self.battle_hp_service.sync_battle_hp_recovery(attacker_cd, attacker_final_hp, atk_stats.max_hp)
        await self.battle_hp_service.sync_battle_hp_recovery(defender_cd, defender_final_hp, def_stats.max_hp)

        attacker_wins = battle_result["winner"] == attacker.user_id
        rewards: Dict[str, Union[float, int]] = {
            "attacker_final_hp": attacker_final_hp,
            "attacker_max_hp": atk_stats.max_hp,
            "defender_final_hp": defender_final_hp,
            "defender_max_hp": def_stats.max_hp,
            "rounds": battle_result["rounds"],
        }

        if attacker_wins:
            impart_gain = random.uniform(0.01, 0.05)
            if not attacker_impart:
                await self.db.ext.create_impart_info(attacker.user_id)
                attacker_impart = await self.db.ext.get_impart_info(attacker.user_id)
            if attacker_impart:
                attacker_impart.impart_atk_per = min(1.0, attacker_impart.impart_atk_per + impart_gain)
                await self.db.ext.update_impart_info(attacker_impart)
            rewards["impart_atk_gain"] = impart_gain

            if defender_impart and defender_impart.impart_atk_per > 0:
                loss = min(impart_gain / 2, defender_impart.impart_atk_per)
                defender_impart.impart_atk_per -= loss
                await self.db.ext.update_impart_info(defender_impart)
                rewards["defender_loss"] = loss
        else:
            latest_attacker = await self.db.get_player_by_id(attacker.user_id)
            exp_loss = int(latest_attacker.experience * 0.01) if latest_attacker else 0
            if latest_attacker:
                latest_attacker.experience = max(0, latest_attacker.experience - exp_loss)
                await self.db.update_player(latest_attacker)
            rewards["exp_loss"] = exp_loss

        battle_log = "\n".join(battle_result["combat_log"][-8:])
        return attacker_wins, battle_log, rewards

    async def get_impart_ranking(self, limit: int = 10) -> List[dict]:
        """获取传承排行。"""
        async with self.db.conn.execute(
            """
            SELECT user_id, impart_hp_per, impart_mp_per, impart_atk_per,
                   impart_know_per, impart_burst_per
            FROM impart_info
            ORDER BY impart_atk_per DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            user_id = row[0]
            player = await self.db.get_player_by_id(user_id)
            if not player:
                continue
            total_per = row[1] + row[2] + row[3] + row[4] + row[5]
            results.append(
                {
                    "user_id": user_id,
                    "user_name": player.user_name or user_id[:8],
                    "atk_per": row[3],
                    "total_per": total_per,
                }
            )
        return results
