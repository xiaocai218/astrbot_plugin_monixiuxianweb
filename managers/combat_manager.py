"""
战斗管理器。

负责玩家之间以及玩家挑战世界 Boss 时的战斗结算。
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class CombatStats:
    """战斗结算所需的基础属性。"""

    user_id: str
    name: str
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    atk: int
    defense: int = 0
    crit_rate: int = 0
    exp: int = 0


class CombatManager:
    """统一处理 PVP 与 Boss 战斗。"""

    BOSS_ENRAGE_THRESHOLD = 0.3
    BOSS_ENRAGE_DURATION = 5
    BOSS_ENRAGE_SKILLS = ("heal", "rage", "stone", "dodge", "roar")

    @staticmethod
    def calculate_hp_mp(experience: int, hp_buff: float = 0.0, mp_buff: float = 0.0) -> Tuple[int, int]:
        """根据修为和加成计算战斗 HP/MP。"""
        base_hp = experience // 2
        base_mp = experience
        hp = int(base_hp * (1 + hp_buff))
        mp = int(base_mp * (1 + mp_buff))
        return hp, mp

    @staticmethod
    def calculate_atk(experience: int, atkpractice: int = 0, atk_buff: float = 0.0) -> int:
        """根据修为、攻修和加成计算攻击力。"""
        base_atk = experience // 10
        practice_bonus = atkpractice * 0.04
        total_atk = int(base_atk * (1 + practice_bonus + atk_buff))
        return max(total_atk, 1)

    @staticmethod
    def calculate_turn_attack(base_atk: int, crit_rate: int = 0, atk_buff: float = 0.0) -> Tuple[bool, int]:
        """计算单回合伤害，并判断是否暴击。"""
        damage = int(round(random.uniform(0.95, 1.05), 2) * base_atk * (1 + atk_buff))
        is_crit = random.randint(0, 100) <= crit_rate
        if is_crit:
            damage = int(damage * 1.5)
        return is_crit, damage

    @staticmethod
    def apply_damage_reduction(damage: int, defense: int = 0) -> int:
        """根据防御值计算最终伤害。"""
        if defense <= 0:
            return damage
        reduction_rate = defense / (defense + 100)
        final_damage = int(damage * (1 - reduction_rate))
        return max(1, final_damage)

    @classmethod
    def _roll_boss_enrage_skill(cls) -> str:
        """随机选择 Boss 狂暴技能。"""
        return random.choice(cls.BOSS_ENRAGE_SKILLS)

    @staticmethod
    def _get_boss_enrage_skill_name(skill: str) -> str:
        """返回 Boss 狂暴技能名称。"""
        names = {
            "heal": "回血",
            "rage": "暴怒",
            "stone": "石化",
            "dodge": "闪避",
            "roar": "咆哮",
        }
        return names.get(skill, "未知")

    @classmethod
    def _trigger_boss_enrage(cls, combat_log: List[str], boss: CombatStats) -> str:
        """触发 Boss 狂暴并写入战报。"""
        skill = cls._roll_boss_enrage_skill()
        skill_name = cls._get_boss_enrage_skill_name(skill)
        combat_log.append(f"🔥 {boss.name} 血量跌至 30%，进入狂暴状态！")
        combat_log.append(f"狂暴持续 {cls.BOSS_ENRAGE_DURATION} 回合，本次技能：{skill_name}")
        if skill == "heal":
            combat_log.append("效果：Boss 每回合在你出手前恢复 15%-20% 最大生命。")
        elif skill == "rage":
            combat_log.append("效果：Boss 在 5 回合内攻击力额外提升 200%。")
        elif skill == "stone":
            combat_log.append("效果：Boss 获得递减石化减伤，并反弹你造成的实际伤害。")
        elif skill == "dodge":
            combat_log.append("效果：Boss 在 5 回合内拥有 50% 闪避。")
        else:
            combat_log.append("效果：你将在 3 回合内因恐惧无法造成伤害，但同时拥有 30% 闪避。")
        return skill

    @classmethod
    def player_vs_player(
        cls,
        player1: CombatStats,
        player2: CombatStats,
        combat_type: int = 1,
    ) -> Dict:
        """玩家之间的战斗。"""
        combat_log = []
        combat_log.append("☆━━━━ 对战开始 ━━━━☆")
        combat_log.append(f"{player1.name} VS {player2.name}")
        combat_log.append(f"{player1.name}：HP {player1.hp}/{player1.max_hp}，ATK {player1.atk}")
        combat_log.append(f"{player2.name}：HP {player2.hp}/{player2.max_hp}，ATK {player2.atk}")
        combat_log.append("")

        round_num = 0
        max_rounds = 100

        while player1.hp > 0 and player2.hp > 0 and round_num < max_rounds:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")

            is_crit1, damage1 = cls.calculate_turn_attack(player1.atk, player1.crit_rate)
            damage1 = cls.apply_damage_reduction(damage1, player2.defense)
            player2.hp -= damage1

            if is_crit1:
                combat_log.append(f"{player1.name} 发起会心一击，造成 {damage1} 点伤害！")
            else:
                combat_log.append(f"{player1.name} 发起攻击，造成 {damage1} 点伤害")
            combat_log.append(f"{player2.name} 剩余 HP: {max(0, player2.hp)}")

            if player2.hp <= 0:
                break

            is_crit2, damage2 = cls.calculate_turn_attack(player2.atk, player2.crit_rate)
            damage2 = cls.apply_damage_reduction(damage2, player1.defense)
            player1.hp -= damage2

            if is_crit2:
                combat_log.append(f"{player2.name} 发起会心一击，造成 {damage2} 点伤害！")
            else:
                combat_log.append(f"{player2.name} 发起攻击，造成 {damage2} 点伤害")
            combat_log.append(f"{player1.name} 剩余 HP: {max(0, player1.hp)}")
            combat_log.append("")

        if player1.hp > 0:
            winner = player1.user_id
            combat_log.append(f"☆━━━━ {player1.name} 获得胜利！━━━━☆")
        elif player2.hp > 0:
            winner = player2.user_id
            combat_log.append(f"☆━━━━ {player2.name} 获得胜利！━━━━☆")
        else:
            winner = "draw"
            combat_log.append("☆━━━━ 双方同归于尽！━━━━☆")

        if combat_type == 1:
            player1_final_hp = player1.max_hp
            player1_final_mp = player1.max_mp
            player2_final_hp = player2.max_hp
            player2_final_mp = player2.max_mp
        else:
            player1_final_hp = max(1, player1.hp) if player1.hp > 0 else 1
            player1_final_mp = player1.mp
            player2_final_hp = max(1, player2.hp) if player2.hp > 0 else 1
            player2_final_mp = player2.mp

        return {
            "winner": winner,
            "combat_log": combat_log,
            "player1_final_hp": player1_final_hp,
            "player1_final_mp": player1_final_mp,
            "player2_final_hp": player2_final_hp,
            "player2_final_mp": player2_final_mp,
            "rounds": round_num,
        }

    @classmethod
    def player_vs_boss(cls, player: CombatStats, boss: CombatStats) -> Dict:
        """玩家挑战世界 Boss。"""
        combat_log = []
        combat_log.append("☆━━━━ Boss战开始 ━━━━☆")
        combat_log.append(f"{player.name} 挑战 {boss.name}")
        combat_log.append(f"{player.name}：HP {player.hp}/{player.max_hp}，ATK {player.atk}")
        combat_log.append(f"{boss.name}：HP {boss.hp}/{boss.max_hp}，ATK {boss.atk}")
        combat_log.append("")

        round_num = 0
        max_rounds = 100
        total_damage_dealt = 0
        enrage_skill = None
        enrage_rounds_left = 0
        fear_rounds_left = 0

        if boss.max_hp > 0 and boss.hp <= int(boss.max_hp * cls.BOSS_ENRAGE_THRESHOLD):
            enrage_skill = cls._trigger_boss_enrage(combat_log, boss)
            enrage_rounds_left = cls.BOSS_ENRAGE_DURATION
            if enrage_skill == "roar":
                fear_rounds_left = 3
            combat_log.append("")

        while player.hp > 0 and boss.hp > 0 and round_num < max_rounds:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")
            round_enrage_active = enrage_rounds_left > 0
            enrage_round_index = cls.BOSS_ENRAGE_DURATION - enrage_rounds_left + 1 if round_enrage_active else 0
            current_stone_reduction = 0

            if round_enrage_active and enrage_skill == "heal" and boss.hp > 0:
                heal_percent = random.randint(15, 20)
                heal_amount = max(1, int(boss.max_hp * heal_percent / 100))
                old_hp = boss.hp
                boss.hp = min(boss.max_hp, boss.hp + heal_amount)
                actual_heal = boss.hp - old_hp
                combat_log.append(
                    f"{boss.name} 在你出手前恢复了 {actual_heal} 点生命（{heal_percent}%）"
                )

            player_can_attack = True
            if fear_rounds_left > 0:
                player_can_attack = False
                combat_log.append(f"{player.name} 被咆哮震慑，本回合无法造成伤害！")

            is_crit, damage = cls.calculate_turn_attack(player.atk, player.crit_rate)
            damage = cls.apply_damage_reduction(damage, boss.defense)
            actual_damage_to_boss = damage
            reflected_damage = 0
            boss_dodged = False

            if not player_can_attack:
                actual_damage_to_boss = 0
            elif round_enrage_active and enrage_skill == "dodge" and random.randint(1, 100) <= 50:
                boss_dodged = True
                actual_damage_to_boss = 0
            elif round_enrage_active and enrage_skill == "stone":
                current_stone_reduction = max(50, 100 - enrage_round_index * 10)
                actual_damage_to_boss = max(1, int(damage * (1 - current_stone_reduction / 100)))
                reflected_damage = actual_damage_to_boss
                boss.hp -= actual_damage_to_boss
                total_damage_dealt += actual_damage_to_boss
                player.hp -= reflected_damage
            else:
                boss.hp -= actual_damage_to_boss
                total_damage_dealt += actual_damage_to_boss

            if is_crit:
                combat_log.append(f"{player.name} 发起会心一击，造成 {damage} 点伤害！")
            else:
                combat_log.append(f"{player.name} 发起攻击，造成 {damage} 点伤害")

            if not player_can_attack:
                combat_log.append("本次攻击因恐惧失效，没有对 Boss 造成伤害。")
            elif boss_dodged:
                combat_log.append(f"{boss.name} 成功闪避了这次攻击！")
            elif round_enrage_active and enrage_skill == "stone":
                combat_log.append(
                    f"{boss.name} 处于石化状态，本回合减伤 {current_stone_reduction}% ，实际仅受到 {actual_damage_to_boss} 点伤害。"
                )
                combat_log.append(f"{player.name} 受到反伤，损失 {reflected_damage} 点 HP")
                combat_log.append(f"{player.name} 剩余 HP: {max(0, player.hp)}")

            combat_log.append(f"{boss.name} 剩余 HP: {max(0, boss.hp)}")

            if enrage_skill is None and boss.hp > 0 and boss.max_hp > 0 and boss.hp <= int(boss.max_hp * cls.BOSS_ENRAGE_THRESHOLD):
                enrage_skill = cls._trigger_boss_enrage(combat_log, boss)
                enrage_rounds_left = cls.BOSS_ENRAGE_DURATION
                if enrage_skill == "roar":
                    fear_rounds_left = 3
                combat_log.append("")

            if player.hp <= 0 or boss.hp <= 0:
                break

            boss_atk = boss.atk
            if round_enrage_active and enrage_skill == "rage":
                boss_atk = int(boss.atk * 3)
                combat_log.append(f"{boss.name} 进入暴怒状态，本回合攻击力提升至 {boss_atk}！")

            is_boss_crit, boss_damage = cls.calculate_turn_attack(boss_atk, 30)
            boss_damage = cls.apply_damage_reduction(boss_damage, player.defense)
            player_dodged = round_enrage_active and enrage_skill == "roar" and random.randint(1, 100) <= 30

            if player_dodged:
                boss_damage = 0
            else:
                player.hp -= boss_damage

            if player_dodged:
                combat_log.append(f"{player.name} 在恐惧中本能闪避，成功躲开了这次攻击！")
            elif is_boss_crit:
                combat_log.append(f"{boss.name} 发起会心一击，造成 {boss_damage} 点伤害！")
            else:
                combat_log.append(f"{boss.name} 发起攻击，造成 {boss_damage} 点伤害")
            combat_log.append(f"{player.name} 剩余 HP: {max(0, player.hp)}")
            combat_log.append("")

            if fear_rounds_left > 0:
                fear_rounds_left -= 1

            if round_enrage_active:
                enrage_rounds_left -= 1
                if enrage_rounds_left <= 0:
                    combat_log.append(f"{boss.name} 的狂暴状态结束了。")
                    combat_log.append("")

        if boss.hp <= 0:
            winner = player.user_id
            combat_log.append(f"☆━━━━ {player.name} 击败了 {boss.name}！━━━━☆")
            reward = boss.exp
        elif player.hp <= 0:
            winner = boss.user_id
            combat_log.append(f"☆━━━━ {player.name} 被 {boss.name} 击败！━━━━☆")
            damage_ratio = total_damage_dealt / boss.max_hp if boss.max_hp > 0 else 0
            reward = int(boss.exp * damage_ratio)
            combat_log.append(f"虽败犹荣，获得 {reward} 灵石作为奖励")
        else:
            winner = "draw"
            reward = 0
            combat_log.append("☆━━━━ 战斗超时，双方未分胜负！━━━━☆")

        return {
            "winner": winner,
            "combat_log": combat_log,
            "player_final_hp": max(1, player.hp),
            "player_final_mp": player.mp,
            "boss_final_hp": max(0, boss.hp),
            "reward": reward,
            "rounds": round_num,
        }
