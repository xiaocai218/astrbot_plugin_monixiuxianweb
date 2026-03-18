"""突破与轻量天劫逻辑。"""

import random
from typing import Optional, Tuple

from astrbot.api import logger

from ..config_manager import ConfigManager
from ..data import DataBase
from ..models import Player

__all__ = ["BreakthroughManager"]


class BreakthroughManager:
    """处理境界突破、失败惩罚与轻量天劫。"""

    TRIBULATION_TRIGGER_LEVEL = 13
    TRIBULATION_SUCCESS_RATES = [
        (13, 15, 0.70),
        (16, 18, 0.60),
        (19, 21, 0.50),
        (22, 24, 0.40),
        (25, 999, 0.30),
    ]
    TRIBULATION_MENTAL_THRESHOLD = 1000
    TRIBULATION_MENTAL_BONUS = 0.02
    TRIBULATION_MENTAL_BONUS_CAP = 0.10
    TRIBULATION_SUCCESS_EXP_BONUS = 0.05
    TRIBULATION_FAILURE_EXP_PENALTY = 0.05

    def __init__(self, db: DataBase, config_manager: ConfigManager, config: dict):
        self.db = db
        self.config_manager = config_manager
        self.config = config

    def check_breakthrough_requirements(self, player: Player) -> Tuple[bool, str]:
        """检查玩家是否满足突破条件。"""
        level_data = self.config_manager.get_level_data(player.cultivation_type)

        if player.level_index >= len(level_data) - 1:
            return False, "你已经达到当前体系的最高境界，无法继续突破。"

        next_level_data = level_data[player.level_index + 1]
        required_exp = next_level_data.get("exp_needed", 0)
        if player.experience < required_exp:
            current_level = level_data[player.level_index]["level_name"]
            next_level = next_level_data["level_name"]
            return False, (
                f"修为不足，无法突破。\n"
                f"当前境界：{current_level}\n"
                f"当前修为：{player.experience:,}\n"
                f"突破至【{next_level}】需要修为：{required_exp:,}"
            )

        return True, ""

    def should_trigger_tribulation(self, target_level_index: int) -> bool:
        """判断目标境界是否触发轻量天劫。"""
        return target_level_index >= self.TRIBULATION_TRIGGER_LEVEL

    def calculate_tribulation_success_rate(self, player: Player, target_level_index: int) -> float:
        """计算轻量天劫成功率。"""
        base_rate = 0.30
        for start, end, rate in self.TRIBULATION_SUCCESS_RATES:
            if start <= target_level_index <= end:
                base_rate = rate
                break

        mental_bonus = min(
            (player.mental_power // self.TRIBULATION_MENTAL_THRESHOLD) * self.TRIBULATION_MENTAL_BONUS,
            self.TRIBULATION_MENTAL_BONUS_CAP,
        )
        return max(0.10, min(0.90, base_rate + mental_bonus))

    def get_tribulation_preview(self, player: Player, target_level_index: int) -> str:
        """返回突破信息中的天劫预警。"""
        if not self.should_trigger_tribulation(target_level_index):
            return ""

        rate = self.calculate_tribulation_success_rate(player, target_level_index)
        return (
            "\n【天劫预警】\n"
            f"此次突破会触发轻量天劫校验，预计渡劫成功率：{rate:.1%}\n"
            "天劫失败不会额外死亡，但会导致本次突破作废，并额外损失少量修为。"
        )

    def calculate_breakthrough_success_rate(
        self,
        player: Player,
        pill_name: Optional[str] = None,
        temp_bonus: float = 0.0,
    ) -> Tuple[float, str]:
        """计算突破成功率。"""
        level_data = self.config_manager.get_level_data(player.cultivation_type)
        next_level_data = level_data[player.level_index + 1]

        base_success_rate = next_level_data.get("success_rate", 0.5)
        final_rate = base_success_rate + temp_bonus
        max_rate = 1.0

        info_lines = [f"基础成功率：{base_success_rate:.1%}"]
        if temp_bonus:
            info_lines.append(f"临时丹药加成：{temp_bonus:+.1%}")

        if pill_name:
            pill_data = self.config_manager.pills_data.get(pill_name)
            if pill_data and pill_data.get("subtype") == "breakthrough":
                breakthrough_bonus = pill_data.get("breakthrough_bonus", 0)
                max_rate = pill_data.get("max_success_rate", 1.0)
                final_rate = min(base_success_rate + temp_bonus + breakthrough_bonus, max_rate)
                info_lines.append(f"破境丹加成：+{breakthrough_bonus:.1%}")
                info_lines.append(f"最大成功率限制：{max_rate:.1%}")
            else:
                logger.warning("无效的破境丹：%s", pill_name)

        final_rate = max(0.0, min(final_rate, max_rate))
        info_lines.append(f"最终成功率：{final_rate:.1%}")
        return final_rate, "\n".join(info_lines)

    async def execute_breakthrough(
        self,
        player: Player,
        pill_name: Optional[str] = None,
        temp_bonus: float = 0.0,
        death_rate_multiplier: float = 1.0,
    ) -> Tuple[bool, str, bool]:
        """执行突破。"""
        can_breakthrough, error_msg = self.check_breakthrough_requirements(player)
        if not can_breakthrough:
            return False, error_msg, False

        success_rate, rate_info = self.calculate_breakthrough_success_rate(player, pill_name, temp_bonus)
        level_data = self.config_manager.get_level_data(player.cultivation_type)
        current_level_name = level_data[player.level_index]["level_name"]
        next_level_index = player.level_index + 1
        next_level_data = level_data[next_level_index]
        next_level_name = next_level_data["level_name"]

        if random.random() < success_rate:
            return await self._handle_breakthrough_success(
                player,
                rate_info,
                current_level_name,
                next_level_index,
                next_level_name,
                next_level_data,
            )

        return await self._handle_breakthrough_failure(
            player,
            rate_info,
            next_level_name,
            current_level_name,
            death_rate_multiplier,
        )

    async def _handle_breakthrough_success(
        self,
        player: Player,
        rate_info: str,
        current_level_name: str,
        next_level_index: int,
        next_level_name: str,
        next_level_data: dict,
    ) -> Tuple[bool, str, bool]:
        """处理突破成功分支。"""
        snapshot = {
            "level_index": player.level_index,
            "experience": player.experience,
            "lifespan": player.lifespan,
            "mental_power": player.mental_power,
            "physical_damage": player.physical_damage,
            "magic_damage": player.magic_damage,
            "physical_defense": player.physical_defense,
            "magic_defense": player.magic_defense,
            "blood_qi": player.blood_qi,
            "max_blood_qi": player.max_blood_qi,
            "spiritual_qi": player.spiritual_qi,
            "max_spiritual_qi": player.max_spiritual_qi,
        }

        player.level_index = next_level_index

        lifespan_gain = next_level_data.get("breakthrough_lifespan_gain", 0)
        mental_power_gain = next_level_data.get("breakthrough_mental_power_gain", 0)
        physical_damage_gain = next_level_data.get("breakthrough_physical_damage_gain", 0)
        magic_damage_gain = next_level_data.get("breakthrough_magic_damage_gain", 0)
        physical_defense_gain = next_level_data.get("breakthrough_physical_defense_gain", 0)
        magic_defense_gain = next_level_data.get("breakthrough_magic_defense_gain", 0)

        if player.cultivation_type == "体修":
            energy_gain = next_level_data.get("breakthrough_blood_qi_gain", 0)
            player.max_blood_qi += energy_gain
            player.blood_qi = player.max_blood_qi
            energy_name = "最大气血"
        else:
            energy_gain = next_level_data.get("breakthrough_spiritual_qi_gain", 0)
            player.max_spiritual_qi += energy_gain
            player.spiritual_qi = player.max_spiritual_qi
            energy_name = "最大灵气"

        player.lifespan += lifespan_gain
        player.physical_damage += physical_damage_gain
        player.magic_damage += magic_damage_gain
        player.physical_defense += physical_defense_gain
        player.magic_defense += magic_defense_gain
        player.mental_power += mental_power_gain

        tribulation_msg = ""
        if self.should_trigger_tribulation(next_level_index):
            tribulation_rate = self.calculate_tribulation_success_rate(player, next_level_index)
            if random.random() > tribulation_rate:
                for attr, value in snapshot.items():
                    setattr(player, attr, value)

                exp_penalty = int(snapshot["experience"] * self.TRIBULATION_FAILURE_EXP_PENALTY)
                player.experience = max(0, snapshot["experience"] - exp_penalty)
                await self.db.update_player(player)

                logger.info(
                    "玩家 %s 突破后天劫失败：%s -> %s，渡劫成功率 %.2f%%，额外损失修为 %s",
                    player.user_id,
                    current_level_name,
                    next_level_name,
                    tribulation_rate * 100,
                    exp_penalty,
                )
                return False, (
                    f"⚡ 天劫降临！\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"{rate_info}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"你原本已经触及【{next_level_name}】的门槛，却未能渡过天劫。\n"
                    f"本次突破最终失败，额外损失修为：{exp_penalty:,}\n"
                    f"当前修为：{player.experience:,}\n"
                    f"预计渡劫成功率：{tribulation_rate:.1%}\n"
                    f"提示：提升精神力可略微提高渡劫成功率。"
                ), False

            tribulation_bonus = int(player.experience * self.TRIBULATION_SUCCESS_EXP_BONUS)
            player.experience += tribulation_bonus
            tribulation_msg = (
                f"\n\n⚡ 天劫降临！\n"
                f"你成功渡过天劫，额外获得修为：{tribulation_bonus:,}\n"
                f"渡劫成功率：{tribulation_rate:.1%}"
            )

        await self.db.update_player(player)
        loan_msg = await self._handle_breakthrough_loan_repay(player)

        success_msg = (
            f"✅ 突破成功！\n"
            f"━━━━━━━━━━━━━━\n"
            f"{rate_info}\n"
            f"━━━━━━━━━━━━━━\n"
            f"恭喜你从【{current_level_name}】突破至【{next_level_name}】！\n"
            f"\n【属性增长】\n"
            f"寿命 +{lifespan_gain}\n"
            f"{energy_name} +{energy_gain}\n"
            f"物伤 +{physical_damage_gain}\n"
            f"法伤 +{magic_damage_gain}\n"
            f"物防 +{physical_defense_gain}\n"
            f"法防 +{magic_defense_gain}\n"
            f"精神力 +{mental_power_gain}"
        )

        if player.cultivation_type == "体修":
            success_msg += (
                f"\n\n【当前属性】\n"
                f"寿命：{player.lifespan}\n"
                f"最大气血：{player.max_blood_qi}\n"
                f"物伤：{player.physical_damage}\n"
                f"法伤：{player.magic_damage}\n"
                f"物防：{player.physical_defense}\n"
                f"法防：{player.magic_defense}\n"
                f"精神力：{player.mental_power}"
            )
        else:
            success_msg += (
                f"\n\n【当前属性】\n"
                f"寿命：{player.lifespan}\n"
                f"最大灵气：{player.max_spiritual_qi}\n"
                f"法伤：{player.magic_damage}\n"
                f"物伤：{player.physical_damage}\n"
                f"法防：{player.magic_defense}\n"
                f"物防：{player.physical_defense}\n"
                f"精神力：{player.mental_power}"
            )

        if tribulation_msg:
            success_msg += tribulation_msg
        if loan_msg:
            success_msg += f"\n\n{loan_msg}"

        logger.info("玩家 %s 突破成功：%s -> %s", player.user_id, current_level_name, next_level_name)
        return True, success_msg, False

    async def _handle_breakthrough_failure(
        self,
        player: Player,
        rate_info: str,
        next_level_name: str,
        current_level_name: str,
        death_rate_multiplier: float,
    ) -> Tuple[bool, str, bool]:
        """处理突破失败分支。"""
        death_probability_range = self.config.get("VALUES", {}).get("BREAKTHROUGH_DEATH_PROBABILITY", [0.01, 0.1])
        death_rate = random.uniform(death_probability_range[0], death_probability_range[1])
        death_rate = max(0.0, min(1.0, death_rate * death_rate_multiplier))

        if random.random() < death_rate:
            from .pill_manager import PillManager

            pill_manager = PillManager(self.db, self.config_manager)
            resurrected = await pill_manager.handle_resurrection(player)
            if resurrected:
                logger.info("玩家 %s 突破失败触发回生丹成功复活", player.user_id)
                return False, (
                    f"💥 突破失败，走火入魔！\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"{rate_info}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"你在突破【{next_level_name}】时走火入魔……\n\n"
                    f"⚡ 回生丹效果触发！\n"
                    f"你侥幸重生，但属性被压回到之前的一半，回生丹也已消耗。"
                ), False

            await self.db.delete_player_cascade(player.user_id)
            logger.info(
                "玩家 %s 突破失败并死亡：%s -> %s，死亡概率 %.2f%%",
                player.user_id,
                current_level_name,
                next_level_name,
                death_rate * 100,
            )
            return False, (
                f"💥 突破失败，走火入魔！\n"
                f"━━━━━━━━━━━━━━\n"
                f"{rate_info}\n"
                f"━━━━━━━━━━━━━━\n"
                f"你在突破【{next_level_name}】时身死道消。\n"
                f"所有修为与物品化为乌有。\n"
                f"若想重新修仙，请再次使用“我要修仙”。"
            ), True

        exp_penalty = int(player.experience * 0.1)
        player.experience = max(0, player.experience - exp_penalty)
        await self.db.update_player(player)
        logger.info(
            "玩家 %s 突破失败：%s -> %s，损失修为 %s",
            player.user_id,
            current_level_name,
            next_level_name,
            exp_penalty,
        )
        return False, (
            f"❌ 突破失败\n"
            f"━━━━━━━━━━━━━━\n"
            f"{rate_info}\n"
            f"━━━━━━━━━━━━━━\n"
            f"突破【{next_level_name}】失败，但侥幸保住了性命。\n"
            f"修为受损，损失修为：{exp_penalty:,}\n"
            f"当前修为：{player.experience:,}\n"
            f"请继续积累底蕴，再接再厉。"
        ), False

    async def _handle_breakthrough_loan_repay(self, player: Player) -> str:
        """处理突破贷款自动还款。"""
        try:
            loan = await self.db.ext.get_active_loan(player.user_id)
            if not loan or loan["loan_type"] != "breakthrough":
                return ""

            import time

            now = int(time.time())
            days_borrowed = max(1, (now - loan["borrowed_at"]) // 86400)
            interest = int(loan["principal"] * loan["interest_rate"] * days_borrowed)
            total_due = loan["principal"] + interest

            if player.gold >= total_due:
                player.gold -= total_due
                await self.db.update_player(player)
                await self.db.ext.close_loan(loan["id"])

                bank_data = await self.db.ext.get_bank_account(player.user_id)
                balance = bank_data["balance"] if bank_data else 0
                await self.db.ext.add_bank_transaction(
                    player.user_id,
                    "auto_repay",
                    -total_due,
                    balance,
                    f"突破成功自动还款：本金{loan['principal']:,}+利息{interest:,}",
                    now,
                )

                return (
                    f"💵 突破贷款已自动还清\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"已还本金：{loan['principal']:,} 灵石\n"
                    f"已还利息：{interest:,} 灵石\n"
                    f"当前持有：{player.gold:,} 灵石"
                )

            return (
                f"⚠ 你还有未还清的突破贷款\n"
                f"应还金额：{total_due:,} 灵石\n"
                f"当前持有：{player.gold:,} 灵石\n"
                f"请尽快使用 /还款 处理贷款。"
            )
        except Exception as exc:
            logger.warning("处理突破贷款自动还款异常: %s", exc)
            return ""
