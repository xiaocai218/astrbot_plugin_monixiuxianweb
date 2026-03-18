"""突破系统处理器。"""

from astrbot.api.event import AstrMessageEvent

from ..config_manager import ConfigManager
from ..core import BreakthroughManager, PillManager
from ..data import DataBase
from ..models import Player
from .utils import player_required

CMD_BREAKTHROUGH = "突破"
CMD_BREAKTHROUGH_INFO = "突破信息"

__all__ = ["BreakthroughHandler"]


class BreakthroughHandler:
    """处理突破信息展示与实际突破。"""

    def __init__(self, db: DataBase, config_manager: ConfigManager, config: dict):
        self.db = db
        self.config_manager = config_manager
        self.config = config
        self.breakthrough_manager = BreakthroughManager(db, config_manager, config)
        self.pill_manager = PillManager(db, config_manager)

    @player_required
    async def handle_breakthrough_info(self, player: Player, event: AstrMessageEvent):
        """查看突破信息。"""
        display_name = event.get_sender_name()
        level_data = self.config_manager.get_level_data(player.cultivation_type)

        if player.level_index >= len(level_data) - 1:
            yield event.plain_result("你已经达到当前体系的最高境界，无法继续突破。")
            return

        await self.pill_manager.update_temporary_effects(player)
        modifiers = self.pill_manager.get_breakthrough_modifiers(player)

        current_level_data = level_data[player.level_index]
        next_level_data = level_data[player.level_index + 1]
        current_level_name = current_level_data["level_name"]
        next_level_name = next_level_data["level_name"]
        required_exp = next_level_data.get("exp_needed", 0)
        base_success_rate = next_level_data.get("success_rate", 0.5)
        temp_bonus = modifiers["temp_bonus"]

        exp_satisfied = player.experience >= required_exp
        exp_status = "已满足" if exp_satisfied else "未满足"

        available_pills = []
        for pill_name, pill_data in self.config_manager.pills_data.items():
            if pill_data.get("subtype") != "breakthrough":
                continue
            if pill_data.get("target_level_index") != player.level_index + 1:
                continue

            max_rate = pill_data.get("max_success_rate", 1.0)
            breakthrough_bonus = pill_data.get("breakthrough_bonus", 0)
            final_rate = min(base_success_rate + temp_bonus + breakthrough_bonus, max_rate)
            available_pills.append(
                {
                    "name": pill_name,
                    "rank": pill_data.get("rank", ""),
                    "final_rate": final_rate,
                    "max_rate": max_rate,
                }
            )

        info_lines = [
            f"=== {display_name} 的突破信息 ===\n",
            f"当前境界：{current_level_name}\n",
            f"下一境界：{next_level_name}\n",
            "━━━━━━━━━━━━━━\n",
            "【突破条件】\n",
            f"所需修为：{required_exp:,}\n",
            f"当前修为：{player.experience:,}\n",
            f"修为状态：{exp_status}\n",
            "━━━━━━━━━━━━━━\n",
            "【突破成功率】\n",
            f"基础成功率：{base_success_rate:.1%}\n",
        ]

        if temp_bonus:
            info_lines.append(f"临时丹药加成：{temp_bonus:+.1%}\n")

        death_reduce = 1 - modifiers["permanent_death_multiplier"]
        if death_reduce > 0:
            info_lines.append(f"突破死亡概率降低：{death_reduce:.1%}\n")

        if available_pills:
            info_lines.append("\n【可用破境丹】\n")
            for pill in available_pills:
                info_lines.append(
                    f"· {pill['name']}（{pill['rank']}）\n"
                    f"  使用后成功率：{pill['final_rate']:.1%}（上限 {pill['max_rate']:.1%}）\n"
                )
        else:
            info_lines.append("\n暂无适用的破境丹\n")

        tribulation_preview = self.breakthrough_manager.get_tribulation_preview(player, player.level_index + 1)
        if tribulation_preview:
            info_lines.append(f"\n{tribulation_preview}\n")

        common_lines = [
            "━━━━━━━━━━━━━━\n",
            "【突破说明】\n",
            f"· 使用命令：{CMD_BREAKTHROUGH} 或 {CMD_BREAKTHROUGH} [丹药名]\n",
            "· 突破失败：损失 10% 修为，且有概率死亡\n",
            "· 死亡后：角色数据会被清除，需要重新修仙\n",
            "· 金丹及以上突破成功后，还需额外通过天劫校验\n",
            "============================",
        ]

        if player.cultivation_type == "体修":
            info_lines.extend(["· 体修突破成功后，肉身会进一步强化\n", *common_lines])
        else:
            info_lines.extend(["· 灵修突破成功后，灵力与术法都会进一步提升\n", *common_lines])

        yield event.plain_result("".join(info_lines))

    @player_required
    async def handle_breakthrough(self, player: Player, event: AstrMessageEvent, pill_name: str = None):
        """执行突破。"""
        await self.pill_manager.update_temporary_effects(player)
        modifiers = self.pill_manager.get_breakthrough_modifiers(player)
        level_data = self.config_manager.get_level_data(player.cultivation_type)

        if pill_name and pill_name.strip():
            pill_name = pill_name.strip()
            pill_data = self.config_manager.pills_data.get(pill_name)

            if not pill_data:
                yield event.plain_result(f"未找到破境丹：{pill_name}")
                return
            if pill_data.get("subtype") != "breakthrough":
                yield event.plain_result(f"{pill_name} 不是破境丹。")
                return

            target_level = pill_data.get("target_level_index", -1)
            if target_level != player.level_index + 1:
                current_level = level_data[player.level_index]["level_name"]
                target_level_name = f"境界{target_level}"
                if 0 <= target_level < len(level_data):
                    target_level_name = level_data[target_level]["level_name"]
                yield event.plain_result(
                    f"{pill_name} 不适用于当前突破。\n"
                    f"当前境界：{current_level}\n"
                    f"此丹药用于突破到：【{target_level_name}】"
                )
                return

            inventory = player.get_pills_inventory()
            if inventory.get(pill_name, 0) <= 0:
                yield event.plain_result(f"你的丹药背包中没有【{pill_name}】。")
                return

            can_breakthrough, error_msg = self.breakthrough_manager.check_breakthrough_requirements(player)
            if not can_breakthrough:
                yield event.plain_result(error_msg)
                return

            inventory[pill_name] -= 1
            if inventory[pill_name] <= 0:
                del inventory[pill_name]
            player.set_pills_inventory(inventory)
            await self.db.update_player(player)

            yield event.plain_result(f"使用【{pill_name}】进行突破……")
        else:
            pill_name = None
            yield event.plain_result("开始尝试突破……")

        success, message, died = await self.breakthrough_manager.execute_breakthrough(
            player,
            pill_name,
            modifiers["temp_bonus"],
            modifiers["permanent_death_multiplier"],
        )

        if modifiers["has_temp_effects"]:
            await self.pill_manager.consume_breakthrough_effects(player)

        yield event.plain_result(message)
