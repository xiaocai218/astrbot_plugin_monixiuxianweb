"""灵石转账指令处理器。"""

from __future__ import annotations

import re

from astrbot.api.all import At, Plain
from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.gold_transfer_manager import GoldTransferManager
from ..models import Player
from .utils import player_required

__all__ = ["GoldTransferHandlers"]


class GoldTransferHandlers:
    """处理送灵石相关命令。"""

    def __init__(self, db: DataBase, gold_transfer_mgr: GoldTransferManager):
        self.db = db
        self.gold_transfer_mgr = gold_transfer_mgr

    def _extract_at_target(self, event: AstrMessageEvent) -> str:
        """优先从 Discord 原始 mentions 和消息链中提取被 @ 的目标。"""
        raw_message = getattr(getattr(event, "message_obj", None), "raw_message", None)
        mentions = getattr(raw_message, "mentions", None)
        if mentions:
            first_mention = mentions[0]
            mention_id = getattr(first_mention, "id", None)
            if mention_id:
                return str(mention_id)

        message_chain = event.message_obj.message if getattr(event, "message_obj", None) else []
        for component in message_chain:
            if isinstance(component, At):
                for attr in ("qq", "target", "uin", "user_id"):
                    value = getattr(component, attr, None)
                    if value:
                        return str(value)
        return ""

    def _extract_plain_text(self, event: AstrMessageEvent) -> str:
        """提取命令中的纯文本参数。"""
        message_chain = event.message_obj.message if getattr(event, "message_obj", None) else []
        text_parts = [component.text for component in message_chain if isinstance(component, Plain)]
        text_content = "".join(text_parts).strip()
        for prefix in ("/送灵石", "送灵石"):
            if text_content.startswith(prefix):
                return text_content[len(prefix):].strip()
        return text_content

    @player_required
    async def handle_transfer_info(self, player: Player, event: AstrMessageEvent):
        """查看送灵石规则。"""
        yield event.plain_result(await self.gold_transfer_mgr.get_transfer_info(player.user_id))

    @player_required
    async def handle_gift_gold(self, player: Player, event: AstrMessageEvent, args: str = ""):
        """向其他玩家转账灵石。"""
        target_text = self._extract_at_target(event)
        raw_text = self._extract_plain_text(event) or (args or "").strip()

        if not raw_text:
            yield event.plain_result(
                "请指定转账对象与数量。\n"
                "用法：/送灵石 @某人 数量\n"
                "或：/送灵石 道号 数量"
            )
            return

        parts = raw_text.rsplit(" ", 1)
        if len(parts) != 2:
            yield event.plain_result("格式不正确，请使用：/送灵石 @某人 数量")
            return

        target_part, amount_part = parts[0].strip(), parts[1].strip()
        if not target_text:
            cleaned_target = re.sub(r"\[CQ:[^\]]+\]", "", target_part).strip().lstrip("@")
            cleaned_target = re.sub(r"\[At:\d+\]", "", cleaned_target).strip() or target_part.strip().lstrip("@")
            target_text = cleaned_target

        if not target_text:
            yield event.plain_result("请指定转账对象。")
            return

        try:
            amount = int(amount_part)
        except ValueError:
            yield event.plain_result("请输入有效的灵石数量。")
            return

        if amount <= 0:
            yield event.plain_result("转账数量必须大于 0。")
            return

        success, message = await self.gold_transfer_mgr.gift_gold(player, target_text, amount)
        prefix = "✅ " if success else "❌ "
        yield event.plain_result(prefix + message)
