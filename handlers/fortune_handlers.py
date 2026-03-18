from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.fortune_manager import FortuneManager
from ..models import Player
from .utils import player_required

__all__ = ["FortuneHandlers"]


class FortuneHandlers:
    """福缘系统处理器。"""

    def __init__(self, db: DataBase, fortune_mgr: FortuneManager):
        self.db = db
        self.fortune_mgr = fortune_mgr

    async def handle_fortune_info(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("你还没有开始修仙，请先使用“我要修仙”。")
            return

        info = await self.fortune_mgr.get_fortune_info(player)
        yield event.plain_result(info)

    @player_required
    async def handle_claim_fortune(self, player: Player, event: AstrMessageEvent):
        _, msg = await self.fortune_mgr.claim_daily_fortune(player)
        yield event.plain_result(msg)
