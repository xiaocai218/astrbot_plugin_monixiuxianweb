"""仙缘红包指令处理器。"""

from __future__ import annotations

from astrbot.api.all import Plain
from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.red_packet_manager import RedPacketManager
from ..models import Player
from .utils import player_required

__all__ = ["RedPacketHandlers"]


class RedPacketHandlers:
    """处理仙缘红包相关命令。"""

    def __init__(self, db: DataBase, red_packet_mgr: RedPacketManager):
        self.db = db
        self.red_packet_mgr = red_packet_mgr

    def _extract_plain_text(self, event: AstrMessageEvent) -> str:
        """优先从消息链中提取纯文本参数。"""
        message_chain = event.message_obj.message if getattr(event, "message_obj", None) else []
        text_parts = [component.text for component in message_chain if isinstance(component, Plain)]
        text_content = "".join(text_parts).strip()
        for prefix in ("/发仙缘", "发仙缘"):
            if text_content.startswith(prefix):
                return text_content[len(prefix):].strip()
        return text_content

    @player_required
    async def handle_packet_info(self, player: Player, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("仙缘红包仅支持在群聊中查看。")
            return
        yield event.plain_result(await self.red_packet_mgr.get_info())

    @player_required
    async def handle_send_packet(self, player: Player, event: AstrMessageEvent, args: str = ""):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("仙缘红包仅支持在群聊中发放。")
            return

        raw_text = self._extract_plain_text(event) or (args or "").strip()
        if len(raw_text.split()) < 2:
            raw_message = event.get_message_str().strip()
            for prefix in ("/发仙缘", "发仙缘"):
                if raw_message.startswith(prefix):
                    raw_text = raw_message[len(prefix):].strip()
                    break

        if not raw_text:
            yield event.plain_result("用法：/发仙缘 <金额> <份数> [祝福语]")
            return

        parts = raw_text.split(maxsplit=2)
        if len(parts) < 2:
            yield event.plain_result("格式不正确，请使用：/发仙缘 <金额> <份数> [祝福语]")
            return

        try:
            total_amount = int(parts[0])
            count = int(parts[1])
        except ValueError:
            yield event.plain_result("金额和份数必须是数字。")
            return

        message = parts[2] if len(parts) > 2 else ""
        success, text = await self.red_packet_mgr.create_packet(player, str(group_id), total_amount, count, message)
        yield event.plain_result(text)

    @player_required
    async def handle_grab_packet(self, player: Player, event: AstrMessageEvent):
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("仙缘红包仅支持在群聊中领取。")
            return

        success, text = await self.red_packet_mgr.grab_packet(player, str(group_id))
        yield event.plain_result(text)
