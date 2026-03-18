"""灵石银行处理器。"""

import time

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.bank_manager import BankManager
from ..models import Player
from .utils import player_required

__all__ = ["BankHandlers"]


class BankHandlers:
    """灵石银行处理器。"""

    def __init__(self, db: DataBase, bank_mgr: BankManager):
        self.db = db
        self.bank_mgr = bank_mgr

    def _parse_positive_amount(self, amount) -> int:
        amount_text = str(amount).strip()
        if not amount_text.isdigit():
            return 0
        return int(amount_text)

    @player_required
    async def handle_bank_info(self, player: Player, event: AstrMessageEvent):
        """查看银行信息。"""
        info = await self.bank_mgr.get_bank_info(player)
        limits = await self.bank_mgr.get_loan_limits(player)

        msg_lines = [
            "🏦 灵石银行",
            "━━━━━━━━━━━━━━",
            f"💰 存款余额：{info['balance']:,} 灵石",
            f"📈 待领利息：{info['pending_interest']:,} 灵石",
            f"💵 当前现金：{player.gold:,} 灵石",
            f"📦 总资产（现金+存款）：{limits['total_assets']:,} 灵石",
            f"📌 普通贷款上限：{limits['normal_cap']:,} 灵石",
            f"📌 突破贷款上限：{limits['breakthrough_cap']:,} 灵石",
        ]

        if info.get("loan"):
            loan_info = await self.bank_mgr.get_loan_info(player)
            if loan_info:
                loan_type_name = "突破贷款" if loan_info["loan_type"] == "breakthrough" else "普通贷款"
                status = "已逾期" if loan_info["is_overdue"] else f"剩余 {loan_info['days_remaining']} 天"
                msg_lines.extend(
                    [
                        "━━━━━━━━━━━━━━",
                        f"📋 当前贷款：{loan_type_name}",
                        f"  本金：{loan_info['principal']:,} 灵石",
                        f"  当前利息：{loan_info['current_interest']:,} 灵石",
                        f"  应还总额：{loan_info['total_due']:,} 灵石",
                        f"  状态：{status}",
                    ]
                )

        msg_lines.extend(
            [
                "━━━━━━━━━━━━━━",
                "指令：",
                "  /存灵石 <数量>",
                "  /取灵石 <数量>",
                "  /领取利息",
                "  /贷款 <数量>",
                "  /突破贷款 <数量>",
                "  /还款",
                "  /银行流水",
            ]
        )
        yield event.plain_result("\n".join(msg_lines))

    @player_required
    async def handle_deposit(self, player: Player, event: AstrMessageEvent, amount: str = ""):
        """存入灵石。"""
        amount_value = self._parse_positive_amount(amount)
        if amount_value <= 0:
            yield event.plain_result("❌ 请输入正确的存款金额，例如：/存灵石 10000")
            return

        success, msg = await self.bank_mgr.deposit(player, amount_value)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_withdraw(self, player: Player, event: AstrMessageEvent, amount: str = ""):
        """取出灵石。"""
        amount_value = self._parse_positive_amount(amount)
        if amount_value <= 0:
            yield event.plain_result("❌ 请输入正确的取款金额，例如：/取灵石 10000")
            return

        success, msg = await self.bank_mgr.withdraw(player, amount_value)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_claim_interest(self, player: Player, event: AstrMessageEvent):
        """领取利息。"""
        success, msg = await self.bank_mgr.claim_interest(player)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_loan(self, player: Player, event: AstrMessageEvent, amount: str = ""):
        """申请普通贷款。"""
        amount_value = self._parse_positive_amount(amount)
        if amount_value <= 0:
            limits = await self.bank_mgr.get_loan_limits(player)
            yield event.plain_result(
                "🏦 普通贷款说明\n"
                "━━━━━━━━━━━━━━\n"
                f"当前境界普通贷款上限：{limits['normal_cap']:,} 灵石\n"
                f"境界理论上限：{limits['realm_cap']:,} 灵石\n"
                f"当前总资产（现金+存款）：{limits['total_assets']:,} 灵石\n"
                "说明：普通贷款会按境界档位限制，并参考你当前总资产做软上限控制。\n"
                f"日利率：{self.bank_mgr.loan_interest_rate:.1%}\n"
                f"期限：{self.bank_mgr.loan_duration_days} 天\n"
                "逾期后会被银行追杀致死。\n"
                "用法：/贷款 <金额>"
            )
            return

        success, msg = await self.bank_mgr.borrow(player, amount_value, "normal")
        yield event.plain_result(msg)

    @player_required
    async def handle_repay(self, player: Player, event: AstrMessageEvent):
        """还款。"""
        success, msg = await self.bank_mgr.repay(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_transactions(self, player: Player, event: AstrMessageEvent):
        """查看银行流水。"""
        transactions = await self.bank_mgr.get_transactions(player.user_id, 15)
        if not transactions:
            yield event.plain_result("📒 暂无银行交易记录。")
            return

        type_names = {
            "deposit": "存入",
            "withdraw": "取出",
            "interest": "利息",
            "loan": "贷款",
            "repay": "还款",
            "bank_kill": "追杀",
            "overdue_penalty": "逾期",
        }

        msg_lines = ["📒 银行流水（最近 15 条）", "━━━━━━━━━━━━━━"]
        for trans in transactions:
            trans_time = time.strftime("%m-%d %H:%M", time.localtime(trans["created_at"]))
            type_name = type_names.get(trans["trans_type"], trans["trans_type"])
            amount = trans["amount"]
            amount_text = f"+{amount:,}" if amount > 0 else f"{amount:,}"
            msg_lines.append(f"{trans_time} [{type_name}] {amount_text}")

        msg_lines.append("━━━━━━━━━━━━━━")
        msg_lines.append(f"当前记录余额：{transactions[0]['balance_after']:,} 灵石")
        yield event.plain_result("\n".join(msg_lines))

    @player_required
    async def handle_breakthrough_loan(self, player: Player, event: AstrMessageEvent, amount: str = ""):
        """申请突破贷款。"""
        amount_value = self._parse_positive_amount(amount)
        if amount_value <= 0:
            limits = await self.bank_mgr.get_loan_limits(player)
            pill_price = limits["breakthrough_pill_price"]
            price_hint = (
                f"当前突破丹参考价格：{pill_price:,} 灵石\n" if pill_price else "当前境界未匹配到突破丹价格配置。\n"
            )
            yield event.plain_result(
                "🏦 突破贷款说明\n"
                "━━━━━━━━━━━━━━\n"
                f"{price_hint}"
                f"当前突破贷款上限：{limits['breakthrough_cap']:,} 灵石\n"
                "说明：突破贷款会按当前突破丹价格的约 1.3 倍计算，避免额度过低或过强。\n"
                f"日利率：{self.bank_mgr.breakthrough_loan_rate:.1%}\n"
                f"期限：{self.bank_mgr.breakthrough_loan_duration} 天\n"
                "逾期后会被银行追杀致死。\n"
                "用法：/突破贷款 <金额>"
            )
            return

        success, msg = await self.bank_mgr.borrow(player, amount_value, "breakthrough")
        yield event.plain_result(msg)
