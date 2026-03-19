"""论道指令处理器。"""

from __future__ import annotations

import re

from astrbot.api.all import At, Plain
from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.debate_manager import DebateManager
from ..models import Player
from .utils import player_required

__all__ = ["DebateHandlers"]


class DebateHandlers:
    """处理论道相关命令。"""

    def __init__(self, db: DataBase, debate_mgr: DebateManager):
        self.db = db
        self.debate_mgr = debate_mgr

    def _extract_at_target(self, event: AstrMessageEvent) -> str:
        raw_message = getattr(getattr(event, "message_obj", None), "raw_message", None)
        mentions = getattr(raw_message, "mentions", None)
        if mentions:
            first_mention = mentions[0]
            mention_id = getattr(first_mention, "id", None)
            if mention_id:
                return str(mention_id)

        message_chain = event.message_obj.message if hasattr(event, "message_obj") and event.message_obj else []
        for component in message_chain:
            if isinstance(component, At):
                for attr in ("qq", "target", "uin", "user_id"):
                    value = getattr(component, attr, None)
                    if value:
                        return str(value)
        return ""

    def _extract_plain_text(self, event: AstrMessageEvent) -> str:
        message_chain = event.message_obj.message if hasattr(event, "message_obj") and event.message_obj else []
        text_parts = [component.text for component in message_chain if isinstance(component, Plain)]
        text_content = "".join(text_parts).strip()
        for prefix in ("/论道", "论道"):
            if text_content.startswith(prefix):
                return text_content[len(prefix):].strip()
        return text_content

    @player_required
    async def handle_debate(self, player: Player, event: AstrMessageEvent, args: str = ""):
        target_text = self._extract_at_target(event)
        raw_text = self._extract_plain_text(event) or (args or "").strip()

        if not target_text and raw_text:
            cleaned_target = re.sub(r"\[CQ:[^\]]+\]", "", raw_text).strip().lstrip("@")
            cleaned_target = re.sub(r"\[At:\d+\]", "", cleaned_target).strip() or raw_text.strip().lstrip("@")
            target_text = cleaned_target

        if not target_text:
            yield event.plain_result("请指定论道目标，例如：/论道 @某人")
            return

        success, message = await self.debate_mgr.debate(player, target_text)
        yield event.plain_result(message)
