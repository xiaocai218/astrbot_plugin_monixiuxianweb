from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.enlightenment_manager import EnlightenmentManager

__all__ = ["EnlightenmentHandlers"]


class EnlightenmentHandlers:
    """悟道系统处理器。"""

    def __init__(self, db: DataBase, enlightenment_mgr: EnlightenmentManager):
        self.db = db
        self.enlightenment_mgr = enlightenment_mgr

    async def handle_enlightenment_info(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        player = await self.db.get_player_by_id(user_id)
        if not player:
            yield event.plain_result("你还没有开始修仙，请先使用“我要修仙”。")
            return

        info = await self.enlightenment_mgr.get_enlightenment_info(player)
        yield event.plain_result(info)
