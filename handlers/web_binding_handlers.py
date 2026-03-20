from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.web_binding_manager import WebBindingManager
from ..models import Player
from .utils import player_required

__all__ = ["WebBindingHandlers"]


class WebBindingHandlers:
    """网页绑定指令处理器。"""

    def __init__(self, db: DataBase, web_binding_mgr: WebBindingManager):
        self.db = db
        self.web_binding_mgr = web_binding_mgr

    def _resolve_platform_name(self, event: AstrMessageEvent) -> str:
        raw_message = getattr(getattr(event, "message_obj", None), "raw_message", None)
        for attr in ("platform_name", "platform", "source_platform"):
            value = getattr(raw_message, attr, None)
            if value:
                return str(value)

        module_name = getattr(getattr(raw_message, "__class__", None), "__module__", "") or ""
        module_name = module_name.lower()
        if "discord" in module_name:
            return "discord"
        if "qq" in module_name or "aiocqhttp" in module_name:
            return "qq"
        return "astrbot"

    @player_required
    async def handle_generate_bind_code(self, player: Player, event: AstrMessageEvent):
        platform = self._resolve_platform_name(event)
        success, message = await self.web_binding_mgr.create_bind_code(
            player,
            platform=platform,
            chat_user_id=str(event.get_sender_id()),
        )
        yield event.plain_result(message)

    @player_required
    async def handle_bind_web(self, player: Player, event: AstrMessageEvent, args: str = ""):
        bind_code = (args or "").strip().upper()
        if not bind_code:
            yield event.plain_result("请输入绑定码，例如：绑定网页 ABCD2345")
            return

        platform = self._resolve_platform_name(event)
        success, message = await self.web_binding_mgr.bind_with_code(
            player,
            bind_code=bind_code,
            platform=platform,
            chat_user_id=str(event.get_sender_id()),
            chat_user_name=event.get_sender_name() or str(event.get_sender_id()),
        )
        yield event.plain_result(message)

    @player_required
    async def handle_binding_status(self, player: Player, event: AstrMessageEvent):
        platform = self._resolve_platform_name(event)
        message = await self.web_binding_mgr.get_binding_status(player, platform)
        yield event.plain_result(message)
