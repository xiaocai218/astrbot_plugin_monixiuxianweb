"""灵石银行系统管理器。"""

import time
from decimal import Decimal, ROUND_DOWN
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..data import DataBase
from ..models import Player

if TYPE_CHECKING:
    from ..config_manager import ConfigManager

__all__ = ["BankManager"]


DEFAULT_DAILY_INTEREST_RATE = 0.001
DEFAULT_MAX_DEPOSIT = 10_000_000
DEFAULT_LOAN_INTEREST_RATE = 0.005
DEFAULT_LOAN_DURATION_DAYS = 7
DEFAULT_MAX_LOAN_AMOUNT = 1_000_000
DEFAULT_MIN_LOAN_AMOUNT = 1_000
DEFAULT_BREAKTHROUGH_LOAN_RATE = 0.008
DEFAULT_BREAKTHROUGH_LOAN_DURATION = 3
DEFAULT_BREAKTHROUGH_LOAN_BUFFER = 1.3

REALM_LOAN_CAPS = [
    (0, 9, 10_000),
    (10, 12, 30_000),
    (13, 15, 80_000),
    (16, 18, 150_000),
    (19, 21, 300_000),
    (22, 24, 600_000),
    (25, 35, 1_000_000),
]


class BankManager:
    """灵石银行管理器。"""

    def __init__(
        self,
        db: DataBase,
        config: Optional[dict] = None,
        config_manager: Optional["ConfigManager"] = None,
    ):
        self.db = db
        self.config = config or {}
        self.config_manager = config_manager

        bank_config = self.config.get("BANK") or self.config.get("bank") or {}
        self.daily_interest_rate = bank_config.get("DAILY_INTEREST_RATE", DEFAULT_DAILY_INTEREST_RATE)
        self.max_deposit = bank_config.get("MAX_DEPOSIT", DEFAULT_MAX_DEPOSIT)
        self.loan_interest_rate = bank_config.get("LOAN_INTEREST_RATE", DEFAULT_LOAN_INTEREST_RATE)
        self.loan_duration_days = bank_config.get("LOAN_DURATION_DAYS", DEFAULT_LOAN_DURATION_DAYS)
        self.max_loan_amount = bank_config.get("MAX_LOAN_AMOUNT", DEFAULT_MAX_LOAN_AMOUNT)
        self.min_loan_amount = bank_config.get("MIN_LOAN_AMOUNT", DEFAULT_MIN_LOAN_AMOUNT)
        self.breakthrough_loan_rate = bank_config.get("BREAKTHROUGH_LOAN_RATE", DEFAULT_BREAKTHROUGH_LOAN_RATE)
        self.breakthrough_loan_duration = bank_config.get(
            "BREAKTHROUGH_LOAN_DURATION", DEFAULT_BREAKTHROUGH_LOAN_DURATION
        )
        self.breakthrough_loan_buffer = bank_config.get(
            "BREAKTHROUGH_LOAN_BUFFER", DEFAULT_BREAKTHROUGH_LOAN_BUFFER
        )

    async def ensure_tables(self):
        """确保银行相关数据表存在。"""
        await self.db.ext.ensure_bank_tables()

    async def get_bank_info(self, player: Player) -> dict:
        """获取银行账户信息。"""
        await self.ensure_tables()
        bank_data = await self.db.ext.get_bank_account(player.user_id)
        if not bank_data:
            bank_info = {"balance": 0, "last_interest_time": 0, "pending_interest": 0}
        else:
            bank_info = {
                "balance": bank_data["balance"],
                "last_interest_time": bank_data["last_interest_time"],
                "pending_interest": self._calculate_interest(
                    bank_data["balance"], bank_data["last_interest_time"]
                ),
            }

        bank_info["loan"] = await self.db.ext.get_active_loan(player.user_id)
        return bank_info

    def _calculate_interest(self, balance: int, last_time: int) -> int:
        """计算待领取利息。"""
        if balance <= 0 or last_time <= 0:
            return 0

        now = int(time.time())
        days_passed = (now - last_time) // 86400
        if days_passed < 1:
            return 0

        balance_d = Decimal(str(balance))
        rate_d = Decimal(str(self.daily_interest_rate))
        compound = (1 + rate_d) ** days_passed - 1
        interest = balance_d * compound
        return int(interest.quantize(Decimal("1"), rounding=ROUND_DOWN))

    def _get_realm_loan_cap(self, level_index: int) -> int:
        """按境界段获取普通贷款理论上限。"""
        for min_level, max_level, cap in REALM_LOAN_CAPS:
            if min_level <= level_index <= max_level:
                return min(cap, self.max_loan_amount)
        return self.max_loan_amount

    def _get_breakthrough_pill_price(self, player: Player) -> Optional[int]:
        """获取当前境界对应的突破丹价格。"""
        if not self.config_manager:
            return None

        prices = []
        for pill_data in self.config_manager.pills_data.values():
            if pill_data.get("subtype") != "breakthrough":
                continue
            required_level = int(pill_data.get("required_level_index", -1))
            if required_level == player.level_index:
                price = int(pill_data.get("price", 0))
                if price > 0:
                    prices.append(price)

        if not prices:
            return None
        return max(prices)

    async def get_loan_limits(self, player: Player) -> dict:
        """获取当前玩家可申请的贷款额度信息。"""
        await self.ensure_tables()
        bank_data = await self.db.ext.get_bank_account(player.user_id)
        bank_balance = bank_data["balance"] if bank_data else 0
        total_assets = max(0, int(player.gold)) + max(0, int(bank_balance))
        realm_cap = self._get_realm_loan_cap(player.level_index)

        # 普通贷款：以境界为主，上限再受总资产软限制影响。
        asset_soft_cap = max(10_000, total_assets * 3)
        normal_cap = max(self.min_loan_amount, min(realm_cap, asset_soft_cap))

        breakthrough_pill_price = self._get_breakthrough_pill_price(player)
        if breakthrough_pill_price:
            breakthrough_cap = max(
                self.min_loan_amount,
                int(breakthrough_pill_price * float(self.breakthrough_loan_buffer)),
            )
        else:
            breakthrough_cap = normal_cap

        return {
            "realm_cap": realm_cap,
            "normal_cap": normal_cap,
            "breakthrough_cap": breakthrough_cap,
            "bank_balance": bank_balance,
            "total_assets": total_assets,
            "breakthrough_pill_price": breakthrough_pill_price,
        }

    async def deposit(self, player: Player, amount: int) -> Tuple[bool, str]:
        """存入灵石。"""
        await self.ensure_tables()
        if amount <= 0:
            return False, "存款金额必须大于 0。"

        await self.ensure_tables()
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            await self.ensure_tables()
            player = await self.db.get_player_by_id(player.user_id)
            if player.gold < amount:
                await self.db.conn.rollback()
                return False, f"灵石不足，你当前只有 {player.gold:,} 灵石。"

            bank_data = await self.db.ext.get_bank_account(player.user_id)
            current_balance = bank_data["balance"] if bank_data else 0
            if current_balance + amount > self.max_deposit:
                await self.db.conn.rollback()
                return False, f"存款上限为 {self.max_deposit:,} 灵石，当前余额 {current_balance:,}。"

            player.gold -= amount
            await self.db.update_player(player)

            new_balance = current_balance + amount
            now = int(time.time())
            await self.db.ext.update_bank_account(
                player.user_id,
                new_balance,
                now if current_balance == 0 else bank_data["last_interest_time"],
            )
            await self._add_transaction(player.user_id, "deposit", amount, new_balance, "存入灵石")
            await self.db.conn.commit()
            return True, f"成功存入 {amount:,} 灵石。\n当前余额：{new_balance:,} 灵石"
        except Exception:
            await self.db.conn.rollback()
            raise

    async def withdraw(self, player: Player, amount: int) -> Tuple[bool, str]:
        """取出灵石。"""
        await self.ensure_tables()
        if amount <= 0:
            return False, "取款金额必须大于 0。"

        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            bank_data = await self.db.ext.get_bank_account(player.user_id)
            if not bank_data or bank_data["balance"] < amount:
                await self.db.conn.rollback()
                current_balance = bank_data["balance"] if bank_data else 0
                return False, f"银行余额不足，当前余额：{current_balance:,} 灵石。"

            new_balance = bank_data["balance"] - amount
            await self.db.ext.update_bank_account(
                player.user_id, new_balance, bank_data["last_interest_time"]
            )

            player.gold += amount
            await self.db.update_player(player)
            await self._add_transaction(player.user_id, "withdraw", -amount, new_balance, "取出灵石")
            await self.db.conn.commit()
            return (
                True,
                f"成功取出 {amount:,} 灵石。\n当前余额：{new_balance:,} 灵石\n当前持有：{player.gold:,} 灵石",
            )
        except Exception:
            await self.db.conn.rollback()
            raise

    async def claim_interest(self, player: Player) -> Tuple[bool, str]:
        """领取利息。"""
        await self.ensure_tables()
        bank_data = await self.db.ext.get_bank_account(player.user_id)
        if not bank_data or bank_data["balance"] <= 0:
            return False, "你还没有存款，无法领取利息。"

        interest = self._calculate_interest(bank_data["balance"], bank_data["last_interest_time"])
        if interest <= 0:
            return False, "利息不足 1 灵石，请明日再来。"

        new_balance = bank_data["balance"] + interest
        now = int(time.time())
        await self.db.ext.update_bank_account(player.user_id, new_balance, now)
        await self._add_transaction(player.user_id, "interest", interest, new_balance, "领取利息")
        return True, f"成功领取利息 {interest:,} 灵石。\n当前余额：{new_balance:,} 灵石"

    async def get_loan_info(self, player: Player) -> Optional[dict]:
        """获取贷款详情。"""
        await self.ensure_tables()
        loan = await self.db.ext.get_active_loan(player.user_id)
        if not loan:
            return None

        now = int(time.time())
        days_borrowed = (now - loan["borrowed_at"]) // 86400
        days_remaining = max(0, (loan["due_at"] - now) // 86400)
        interest = int(loan["principal"] * loan["interest_rate"] * max(1, days_borrowed))
        total_due = loan["principal"] + interest

        return {
            **loan,
            "days_borrowed": days_borrowed,
            "days_remaining": days_remaining,
            "current_interest": interest,
            "total_due": total_due,
            "is_overdue": now > loan["due_at"],
        }

    async def borrow(self, player: Player, amount: int, loan_type: str = "normal") -> Tuple[bool, str]:
        """申请贷款。"""
        await self.ensure_tables()
        if amount < self.min_loan_amount:
            return False, f"最小贷款金额为 {self.min_loan_amount:,} 灵石。"

        player = await self.db.get_player_by_id(player.user_id)
        limits = await self.get_loan_limits(player)
        if loan_type == "breakthrough":
            loan_cap = limits["breakthrough_cap"]
            type_name = "突破贷款"
        else:
            loan_cap = limits["normal_cap"]
            type_name = "普通贷款"

        if amount > loan_cap:
            extra_lines = [
                f"当前可贷款上限：{loan_cap:,} 灵石",
                f"境界额度上限：{limits['realm_cap']:,} 灵石",
                f"当前总资产（现金+存款）：{limits['total_assets']:,} 灵石",
            ]
            if loan_type == "breakthrough" and limits["breakthrough_pill_price"]:
                extra_lines.append(f"当前突破丹参考价格：{limits['breakthrough_pill_price']:,} 灵石")
            return False, "申请金额超出当前可贷款额度。\n" + "\n".join(extra_lines)

        await self.ensure_tables()
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            existing_loan = await self.db.ext.get_active_loan(player.user_id)
            if existing_loan:
                await self.db.conn.rollback()
                return False, "你已有未还清的贷款，请先还款后再申请新贷款。"

            if loan_type == "breakthrough":
                interest_rate = self.breakthrough_loan_rate
                duration_days = self.breakthrough_loan_duration
            else:
                interest_rate = self.loan_interest_rate
                duration_days = self.loan_duration_days

            now = int(time.time())
            due_at = now + duration_days * 86400
            await self.db.ext.create_loan(player.user_id, amount, interest_rate, now, due_at, loan_type)

            player.gold += amount
            await self.db.update_player(player)

            bank_data = await self.db.ext.get_bank_account(player.user_id)
            balance = bank_data["balance"] if bank_data else 0
            await self._add_transaction(player.user_id, "loan", amount, balance, f"{type_name}：借入{amount:,}灵石")

            total_interest = int(amount * interest_rate * duration_days)
            total_due = amount + total_interest
            await self.db.conn.commit()

            result_lines = [
                f"💰 {type_name}成功",
                "━━━━━━━━━━━━━━",
                f"借入金额：{amount:,} 灵石",
                f"日利率：{interest_rate:.1%}",
                f"还款期限：{duration_days} 天",
                f"到期应还：约 {total_due:,} 灵石",
                f"当前持有：{player.gold:,} 灵石",
            ]
            if loan_type == "normal":
                result_lines.append(f"本境界普通贷款上限：{limits['normal_cap']:,} 灵石")
            else:
                if limits["breakthrough_pill_price"]:
                    result_lines.append(f"当前突破丹参考价格：{limits['breakthrough_pill_price']:,} 灵石")
                result_lines.append(f"当前突破贷款上限：{limits['breakthrough_cap']:,} 灵石")
            result_lines.append("逾期将被银行追杀致死。")
            return True, "\n".join(result_lines)
        except Exception:
            await self.db.conn.rollback()
            raise

    async def repay(self, player: Player) -> Tuple[bool, str]:
        """还款。"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            player = await self.db.get_player_by_id(player.user_id)
            loan_info = await self.get_loan_info(player)
            if not loan_info:
                await self.db.conn.rollback()
                return False, "你当前没有需要偿还的贷款。"

            total_due = loan_info["total_due"]
            if player.gold < total_due:
                await self.db.conn.rollback()
                return (
                    False,
                    f"灵石不足。\n应还金额：{total_due:,} 灵石\n"
                    f"（本金 {loan_info['principal']:,} + 利息 {loan_info['current_interest']:,}）\n"
                    f"当前持有：{player.gold:,} 灵石\n还差：{total_due - player.gold:,} 灵石",
                )

            player.gold -= total_due
            await self.db.update_player(player)
            await self.db.ext.close_loan(loan_info["id"])

            bank_data = await self.db.ext.get_bank_account(player.user_id)
            balance = bank_data["balance"] if bank_data else 0
            await self._add_transaction(
                player.user_id,
                "repay",
                -total_due,
                balance,
                f"还款：本金{loan_info['principal']:,}+利息{loan_info['current_interest']:,}",
            )
            await self.db.conn.commit()

            loan_type_name = "突破贷款" if loan_info["loan_type"] == "breakthrough" else "普通贷款"
            return (
                True,
                f"✅ 还款成功\n"
                f"━━━━━━━━━━━━━━\n"
                f"贷款类型：{loan_type_name}\n"
                f"已还本金：{loan_info['principal']:,} 灵石\n"
                f"已还利息：{loan_info['current_interest']:,} 灵石\n"
                f"合计支付：{total_due:,} 灵石\n"
                f"当前持有：{player.gold:,} 灵石"
            )
        except Exception:
            await self.db.conn.rollback()
            raise

    async def check_and_process_overdue_loans(self) -> List[dict]:
        """检查并处理逾期贷款。"""
        await self.ensure_tables()
        now = int(time.time())
        overdue_loans = await self.db.ext.get_overdue_loans(now)
        processed = []

        for loan in overdue_loans:
            player = await self.db.get_player_by_id(loan["user_id"])
            if not player:
                await self.db.ext.mark_loan_overdue(loan["id"])
                continue

            player_name = player.user_name or f"道友{player.user_id[:6]}"
            await self.db.delete_player_cascade(player.user_id)
            await self.db.ext.mark_loan_overdue(loan["id"])
            await self._add_transaction(
                loan["user_id"],
                "bank_kill",
                0,
                0,
                "逾期未还款，被银行追杀致死",
            )
            processed.append({**loan, "player_name": player_name, "death": True})

        return processed

    async def _add_transaction(
        self, user_id: str, trans_type: str, amount: int, balance_after: int, description: str
    ):
        """添加银行交易流水。"""
        await self.db.ext.add_bank_transaction(
            user_id, trans_type, amount, balance_after, description, int(time.time())
        )

    async def get_transactions(self, user_id: str, limit: int = 20) -> List[dict]:
        """获取交易流水。"""
        return await self.db.ext.get_bank_transactions(user_id, limit)

    async def get_deposit_ranking(self, limit: int = 10) -> List[dict]:
        """获取存款排行榜。"""
        return await self.db.ext.get_deposit_ranking(limit)
