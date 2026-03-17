# handlers/rift_handlers.py
from astrbot.api.event import AstrMessageEvent

from ..data.data_manager import DataBase
from ..managers.rift_manager import RiftManager


class RiftHandlers:
    def __init__(self, db: DataBase, rift_mgr: RiftManager):
        self.db = db
        self.rift_mgr = rift_mgr

    async def handle_rift_list(self, event: AstrMessageEvent):
        """查看秘境列表"""
        success, msg = await self.rift_mgr.list_rifts()
        yield event.plain_result(msg)

    async def handle_rift_explore(self, event: AstrMessageEvent, rift_id: str = ""):
        """探索秘境"""
        user_id = event.get_sender_id()
        rift_id_text = str(rift_id).strip()

        if not rift_id_text.isdigit():
            yield event.plain_result("❌ 请输入正确的秘境ID，例如：/探索秘境 1")
            return

        rift_id_value = int(rift_id_text)
        if rift_id_value <= 0:
            yield event.plain_result("❌ 请输入正确的秘境ID，例如：/探索秘境 1")
            return

        success, msg = await self.rift_mgr.enter_rift(user_id, rift_id_value)
        yield event.plain_result(msg)

    async def handle_rift_complete(self, event: AstrMessageEvent):
        """完成探索"""
        user_id = event.get_sender_id()
        success, msg, _ = await self.rift_mgr.finish_exploration(user_id)
        yield event.plain_result(msg)

    async def handle_rift_exit(self, event: AstrMessageEvent):
        """退出秘境"""
        user_id = event.get_sender_id()
        success, msg = await self.rift_mgr.exit_rift(user_id)
        yield event.plain_result(msg)
