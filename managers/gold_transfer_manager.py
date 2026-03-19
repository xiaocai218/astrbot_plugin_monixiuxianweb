"""灵石转账管理器。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Tuple

from ..data import DataBase
from ..models import Player

__all__ = ["GoldTransferManager"]


TRANSFER_CONFIG = {
    "min_amount": 100,
    "max_amount_per_transfer": 50000,
    "daily_limit": 200000,
}


class GoldTransferManager:
    """处理玩家之间的灵石转账。"""

    DAILY_STATE_KEY_PREFIX = "gold_transfer_daily"

    def __init__(self, db: DataBase):
        self.db = db

    def _build_daily_key(self, user_id: str) -> str:
        return f"{self.DAILY_STATE_KEY_PREFIX}:{user_id}"

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    async def _get_daily_transfer_amount(self, user_id: str) -> int:
        raw_value = await self.db.ext.get_system_config(self._build_daily_key(user_id))
        if not raw_value:
            return 0

        try:
            data = json.loads(raw_value)
        except json.JSONDecodeError:
            return 0

        if data.get("date") != self._today():
            return 0
        return max(0, int(data.get("amount", 0)))

    async def _set_daily_transfer_amount(self, user_id: str, amount: int):
        payload = {"date": self._today(), "amount": max(0, int(amount))}
        await self.db.ext.set_system_config(
            self._build_daily_key(user_id),
            json.dumps(payload, ensure_ascii=False),
        )

    async def gift_gold(self, sender: Player, target_text: str, amount: int) -> Tuple[bool, str]:
        """向另一位玩家转账灵石。"""
        if amount < TRANSFER_CONFIG["min_amount"]:
            return False, f"单次至少需要转出 {TRANSFER_CONFIG['min_amount']:,} 灵石。"

        if amount > TRANSFER_CONFIG["max_amount_per_transfer"]:
            return False, f"单次最多只能转出 {TRANSFER_CONFIG['max_amount_per_transfer']:,} 灵石。"

        if sender.gold < amount:
            return False, (
                "灵石不足，无法完成转账。\n"
                f"需要灵石：{amount:,}\n"
                f"当前灵石：{sender.gold:,}"
            )

        receiver = await self.db.get_player_by_id(target_text)
        if not receiver:
            receiver = await self.db.get_player_by_name(target_text)

        if not receiver:
            return False, f"未找到目标玩家【{target_text}】。"

        if receiver.user_id == sender.user_id:
            return False, "不能转账给自己。"

        transferred_today = await self._get_daily_transfer_amount(sender.user_id)
        daily_limit = TRANSFER_CONFIG["daily_limit"]
        if transferred_today + amount > daily_limit:
            remaining = max(0, daily_limit - transferred_today)
            return False, (
                "今日送灵石额度不足。\n"
                f"今日已送出：{transferred_today:,}\n"
                f"今日剩余额度：{remaining:,}\n"
                f"每日上限：{daily_limit:,}"
            )

        sender.gold -= amount
        receiver.gold += amount

        await self.db.update_player(sender)
        await self.db.update_player(receiver)
        await self._set_daily_transfer_amount(sender.user_id, transferred_today + amount)

        sender_name = sender.user_name or f"道友{sender.user_id[:6]}"
        receiver_name = receiver.user_name or f"道友{receiver.user_id[:6]}"
        remaining_daily = max(0, daily_limit - transferred_today - amount)

        return True, (
            "💸 送灵石成功\n"
            "━━━━━━━━━━━━━━━\n"
            f"转出方：{sender_name}\n"
            f"接收方：{receiver_name}\n"
            f"转账金额：{amount:,} 灵石\n"
            f"你当前灵石：{sender.gold:,}\n"
            f"今日剩余额度：{remaining_daily:,}/{daily_limit:,}\n"
            "━━━━━━━━━━━━━━━"
        )

    async def get_transfer_info(self, user_id: str) -> str:
        """查看送灵石规则与剩余额度。"""
        transferred_today = await self._get_daily_transfer_amount(user_id)
        daily_limit = TRANSFER_CONFIG["daily_limit"]
        remaining = max(0, daily_limit - transferred_today)
        return (
            "💸 送灵石说明\n"
            "━━━━━━━━━━━━━━━\n"
            f"单次最低：{TRANSFER_CONFIG['min_amount']:,} 灵石\n"
            f"单次最高：{TRANSFER_CONFIG['max_amount_per_transfer']:,} 灵石\n"
            f"每日上限：{daily_limit:,} 灵石\n"
            f"今日已送出：{transferred_today:,} 灵石\n"
            f"今日剩余：{remaining:,} 灵石\n"
            "用法：/送灵石 @某人 数量\n"
            "也支持：/送灵石 道号 数量\n"
            "━━━━━━━━━━━━━━━"
        )
