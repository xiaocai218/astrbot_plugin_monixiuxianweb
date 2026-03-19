"""统一战斗结算管理器。"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


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
        base_hp = experience // 2
        base_mp = experience
        hp = int(base_hp * (1 + hp_buff))
        mp = int(base_mp * (1 + mp_buff))
        return hp, mp

    @staticmethod
    def calculate_atk(experience: int, atkpractice: int = 0, atk_buff: float = 0.0) -> int:
        base_atk = experience // 10
        practice_bonus = atkpractice * 0.04
        total_atk = int(base_atk * (1 + practice_bonus + atk_buff))
        return max(total_atk, 1)

    @staticmethod
    def calculate_turn_attack(base_atk: int, crit_rate: int = 0, atk_buff: float = 0.0) -> Tuple[bool, int]:
        damage = int(round(random.uniform(0.95, 1.05), 2) * base_atk * (1 + atk_buff))
        is_crit = random.randint(0, 100) <= crit_rate
        if is_crit:
            damage = int(damage * 1.5)
        return is_crit, damage

    @staticmethod
    def apply_damage_reduction(damage: int, defense: int = 0) -> int:
        if defense <= 0:
            return damage
        reduction_rate = defense / (defense + 100)
        final_damage = int(damage * (1 - reduction_rate))
        return max(1, final_damage)

    @classmethod
    def _roll_boss_enrage_skill(cls) -> str:
        return random.choice(cls.BOSS_ENRAGE_SKILLS)

    @staticmethod
    def _get_boss_enrage_skill_name(skill: str) -> str:
        return {
            "heal": "回血",
            "rage": "暴怒",
            "stone": "石化",
            "dodge": "闪避",
            "roar": "咆哮",
        }.get(skill, "未知")

    @classmethod
    def _trigger_boss_enrage(cls, combat_log: List[str], boss: CombatStats) -> str:
        skill = cls._roll_boss_enrage_skill()
        skill_name = cls._get_boss_enrage_skill_name(skill)
        combat_log.append(f"🔟 {boss.name} 血量跌至 30%，进入狂暴状态！")
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
            combat_log.append("效果：你在 3 回合内因恐惧无法造成伤害，但拥有 30% 闪避。")
        return skill

    @staticmethod
    def _pet_skill_active(pet_ctx: Optional[Dict], skill: str) -> bool:
        return bool(pet_ctx and pet_ctx.get("rounds_left", 0) > 0 and skill in pet_ctx.get("skills", []))

    @classmethod
    def _log_pet_intro(cls, combat_log: List[str], owner_name: str, pet_ctx: Optional[Dict]):
        if not pet_ctx:
            return
        combat_log.append(f"{owner_name} 携带灵宠【{pet_ctx['pet_name']}】出战（{pet_ctx['rank_label']}）")
        combat_log.append(f"灵宠技能：{'、'.join(pet_ctx.get('skill_labels', []))}")

    @classmethod
    def _apply_pet_round_start(cls, pet_ctx: Optional[Dict], fighter: CombatStats, combat_log: List[str]) -> float:
        atk_bonus = 0.0
        if not pet_ctx or pet_ctx.get("rounds_left", 0) <= 0:
            return atk_bonus

        if cls._pet_skill_active(pet_ctx, "heal"):
            heal_ratio = pet_ctx["values"].get("heal", 0.0)
            heal_amount = max(1, int(fighter.max_hp * heal_ratio))
            old_hp = fighter.hp
            fighter.hp = min(fighter.max_hp, fighter.hp + heal_amount)
            actual_heal = fighter.hp - old_hp
            if actual_heal > 0:
                combat_log.append(f"{pet_ctx['pet_name']} 发动【回春】，为 {fighter.name} 恢复了 {actual_heal} 点 HP")

        if cls._pet_skill_active(pet_ctx, "inspire"):
            atk_bonus = pet_ctx["values"].get("inspire", 0.0)
            combat_log.append(f"{pet_ctx['pet_name']} 发动【鼓舞】，{fighter.name} 本回合攻击提升 {int(atk_bonus * 100)}%")

        return atk_bonus

    @classmethod
    def _get_enemy_defense_after_pet_effect(cls, pet_ctx: Optional[Dict], defender: CombatStats, combat_log: List[str]) -> int:
        if not cls._pet_skill_active(pet_ctx, "gaze"):
            return defender.defense
        reduction = pet_ctx["values"].get("gaze", 0.0)
        reduced_defense = max(0, int(defender.defense * (1 - reduction)))
        combat_log.append(f"{pet_ctx['pet_name']} 发动【凝视】，{defender.name} 本回合防御降低 {int(reduction * 100)}%")
        return reduced_defense

    @classmethod
    def _roll_pet_enemy_miss(cls, defender_pet_ctx: Optional[Dict], combat_log: List[str], attacker_name: str) -> bool:
        if not cls._pet_skill_active(defender_pet_ctx, "illusion"):
            return False
        miss_rate = defender_pet_ctx["values"].get("illusion", 0.0)
        if random.random() < miss_rate:
            combat_log.append(f"{defender_pet_ctx['pet_name']} 发动【幻象】，{attacker_name} 本回合攻击落空！")
            return True
        return False

    @classmethod
    def _apply_pet_damage_reduction(cls, defender_pet_ctx: Optional[Dict], damage: int, combat_log: List[str], defender_name: str) -> int:
        if not cls._pet_skill_active(defender_pet_ctx, "guard"):
            return damage
        reduction = defender_pet_ctx["values"].get("guard", 0.0)
        reduced_damage = max(0, int(damage * (1 - reduction)))
        combat_log.append(f"{defender_pet_ctx['pet_name']} 发动【坚毅】，{defender_name} 本回合减伤 {int(reduction * 100)}%")
        return reduced_damage

    @classmethod
    def _try_pet_revive(cls, pet_ctx: Optional[Dict], fighter: CombatStats, combat_log: List[str]) -> bool:
        if not pet_ctx or pet_ctx.get("revive_used") or not cls._pet_skill_active(pet_ctx, "rebirth"):
            return False
        if fighter.hp > 0:
            return False
        revive_ratio = pet_ctx["values"].get("rebirth", 0.0)
        fighter.hp = max(1, int(fighter.max_hp * revive_ratio))
        pet_ctx["revive_used"] = True
        combat_log.append(f"{pet_ctx['pet_name']} 发动【涅槃】，{fighter.name} 重新站起，恢复 {fighter.hp} 点 HP！")
        return True

    @classmethod
    def _advance_pet_round(cls, pet_ctx: Optional[Dict]):
        if pet_ctx and pet_ctx.get("rounds_left", 0) > 0:
            pet_ctx["rounds_left"] -= 1

    @classmethod
    def player_vs_player(
        cls,
        player1: CombatStats,
        player2: CombatStats,
        combat_type: int = 1,
        pet_context1: Optional[Dict] = None,
        pet_context2: Optional[Dict] = None,
    ) -> Dict:
        combat_log = []
        combat_log.append("☆━━━━ 对战开始 ━━━━☆")
        combat_log.append(f"{player1.name} VS {player2.name}")
        combat_log.append(f"{player1.name}：HP {player1.hp}/{player1.max_hp}，ATK {player1.atk}")
        combat_log.append(f"{player2.name}：HP {player2.hp}/{player2.max_hp}，ATK {player2.atk}")
        cls._log_pet_intro(combat_log, player1.name, pet_context1)
        cls._log_pet_intro(combat_log, player2.name, pet_context2)
        combat_log.append("")

        round_num = 0
        max_rounds = 100

        while player1.hp > 0 and player2.hp > 0 and round_num < max_rounds:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")

            atk_bonus1 = cls._apply_pet_round_start(pet_context1, player1, combat_log)
            player1_attack_missed = cls._roll_pet_enemy_miss(pet_context2, combat_log, player1.name)
            if player1_attack_missed:
                is_crit1, damage1 = False, 0
            else:
                effective_p2_defense = cls._get_enemy_defense_after_pet_effect(pet_context1, player2, combat_log)
                is_crit1, damage1 = cls.calculate_turn_attack(player1.atk, player1.crit_rate, atk_bonus1)
                damage1 = cls.apply_damage_reduction(damage1, effective_p2_defense)
                damage1 = cls._apply_pet_damage_reduction(pet_context2, damage1, combat_log, player2.name)
                player2.hp -= damage1

            if is_crit1:
                combat_log.append(f"{player1.name} 发起会心一击，造成 {damage1} 点伤害！")
            else:
                combat_log.append(f"{player1.name} 发起攻击，造成 {damage1} 点伤害")
            combat_log.append(f"{player2.name} 剩余 HP: {max(0, player2.hp)}")
            cls._try_pet_revive(pet_context2, player2, combat_log)

            if player2.hp <= 0:
                break

            atk_bonus2 = cls._apply_pet_round_start(pet_context2, player2, combat_log)
            player2_attack_missed = cls._roll_pet_enemy_miss(pet_context1, combat_log, player2.name)
            if player2_attack_missed:
                is_crit2, damage2 = False, 0
            else:
                effective_p1_defense = cls._get_enemy_defense_after_pet_effect(pet_context2, player1, combat_log)
                is_crit2, damage2 = cls.calculate_turn_attack(player2.atk, player2.crit_rate, atk_bonus2)
                damage2 = cls.apply_damage_reduction(damage2, effective_p1_defense)
                damage2 = cls._apply_pet_damage_reduction(pet_context1, damage2, combat_log, player1.name)
                player1.hp -= damage2

            if is_crit2:
                combat_log.append(f"{player2.name} 发起会心一击，造成 {damage2} 点伤害！")
            else:
                combat_log.append(f"{player2.name} 发起攻击，造成 {damage2} 点伤害")
            combat_log.append(f"{player1.name} 剩余 HP: {max(0, player1.hp)}")
            combat_log.append("")
            cls._try_pet_revive(pet_context1, player1, combat_log)

            cls._advance_pet_round(pet_context1)
            cls._advance_pet_round(pet_context2)

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
    def player_vs_boss(cls, player: CombatStats, boss: CombatStats, player_pet_context: Optional[Dict] = None) -> Dict:
        combat_log = []
        combat_log.append("☆━━━━ Boss战开始 ━━━━☆")
        combat_log.append(f"{player.name} 挑战 {boss.name}")
        combat_log.append(f"{player.name}：HP {player.hp}/{player.max_hp}，ATK {player.atk}")
        combat_log.append(f"{boss.name}：HP {boss.hp}/{boss.max_hp}，ATK {boss.atk}")
        cls._log_pet_intro(combat_log, player.name, player_pet_context)
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
                combat_log.append(f"{boss.name} 在你出手前恢复了 {actual_heal} 点生命（{heal_percent}%）")

            player_can_attack = True
            if fear_rounds_left > 0:
                player_can_attack = False
                combat_log.append(f"{player.name} 被咆哮震慑，本回合无法造成伤害！")

            atk_bonus = cls._apply_pet_round_start(player_pet_context, player, combat_log)
            is_crit, damage = cls.calculate_turn_attack(player.atk, player.crit_rate, atk_bonus)
            effective_boss_defense = cls._get_enemy_defense_after_pet_effect(player_pet_context, boss, combat_log)
            damage = cls.apply_damage_reduction(damage, effective_boss_defense)
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
                combat_log.append(f"{boss.name} 处于石化状态，本回合减伤 {current_stone_reduction}%，实际仅受到 {actual_damage_to_boss} 点伤害。")
                combat_log.append(f"{player.name} 受到反伤，损失 {reflected_damage} 点 HP")
                combat_log.append(f"{player.name} 剩余 HP: {max(0, player.hp)}")

            combat_log.append(f"{boss.name} 剩余 HP: {max(0, boss.hp)}")

            if enrage_skill is None and boss.hp > 0 and boss.max_hp > 0 and boss.hp <= int(boss.max_hp * cls.BOSS_ENRAGE_THRESHOLD):
                enrage_skill = cls._trigger_boss_enrage(combat_log, boss)
                enrage_rounds_left = cls.BOSS_ENRAGE_DURATION
                if enrage_skill == "roar":
                    fear_rounds_left = 3
                combat_log.append("")

            cls._try_pet_revive(player_pet_context, player, combat_log)
            if player.hp <= 0 or boss.hp <= 0:
                break

            boss_atk = boss.atk
            if round_enrage_active and enrage_skill == "rage":
                boss_atk = int(boss.atk * 3)
                combat_log.append(f"{boss.name} 进入暴怒状态，本回合攻击力提升至 {boss_atk}！")

            is_boss_crit, boss_damage = cls.calculate_turn_attack(boss_atk, 30)
            boss_damage = cls.apply_damage_reduction(boss_damage, player.defense)
            boss_damage = cls._apply_pet_damage_reduction(player_pet_context, boss_damage, combat_log, player.name)
            player_dodged = round_enrage_active and enrage_skill == "roar" and random.randint(1, 100) <= 30
            if not player_dodged:
                player_dodged = cls._roll_pet_enemy_miss(player_pet_context, combat_log, boss.name)

            if player_dodged:
                boss_damage = 0
            else:
                player.hp -= boss_damage

            if player_dodged:
                combat_log.append(f"{player.name} 成功避开了这次攻击！")
            elif is_boss_crit:
                combat_log.append(f"{boss.name} 发起会心一击，造成 {boss_damage} 点伤害！")
            else:
                combat_log.append(f"{boss.name} 发起攻击，造成 {boss_damage} 点伤害")
            combat_log.append(f"{player.name} 剩余 HP: {max(0, player.hp)}")
            combat_log.append("")

            cls._try_pet_revive(player_pet_context, player, combat_log)
            if fear_rounds_left > 0:
                fear_rounds_left -= 1

            if round_enrage_active:
                enrage_rounds_left -= 1
                if enrage_rounds_left <= 0:
                    combat_log.append(f"{boss.name} 的狂暴状态结束了。")
                    combat_log.append("")

            cls._advance_pet_round(player_pet_context)

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
