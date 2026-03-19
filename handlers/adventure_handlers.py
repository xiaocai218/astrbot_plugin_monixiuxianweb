# handlers/adventure_handlers.py
from astrbot.api.event import AstrMessageEvent

from ..data.data_manager import DataBase
from ..managers.adventure_manager import AdventureManager


class AdventureHandlers:
    def __init__(self, db: DataBase, adv_mgr: AdventureManager):
        self.db = db
        self.adv_mgr = adv_mgr

    async def handle_adventure_info(self, event: AstrMessageEvent):
        """显示历练路线总览。"""
        routes = self.adv_mgr.get_route_overview()
        lines = ["📖 历练路线总览", "━━━━━━━━━━━━━━━"]
        for route in routes:
            duration = route.get("duration", 0) // 60
            lines.append(
                f"· {route['name']} ({route.get('risk', '未知风险')}风险)\n"
                f"  时长：{duration} 分钟 | 推荐境界 ≥ {route.get('min_level', 0)}\n"
                f"  说明：{route.get('description', '')}"
            )

        if routes:
            example_routes = "\n".join([f"  /开始历练 {route['name']}" for route in routes[:3]])
        else:
            example_routes = "  /开始历练 巡山问道"

        lines.append(
            "\n💡 指令用法：\n"
            f"{example_routes}\n"
            "  /历练状态 → 查看当前进度\n"
            "  /完成历练 → 领取奖励"
        )
        lines.append("━━━━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    async def handle_start_adventure(self, event: AstrMessageEvent, route: str = ""):
        """开始历练。"""
        user_id = event.get_sender_id()
        _success, msg = await self.adv_mgr.start_adventure(user_id, route)
        yield event.plain_result(msg)

    async def handle_complete_adventure(self, event: AstrMessageEvent):
        """完成历练。"""
        user_id = event.get_sender_id()
        _success, msg, _ = await self.adv_mgr.finish_adventure(user_id)
        yield event.plain_result(msg)

    async def handle_adventure_status(self, event: AstrMessageEvent):
        """查看历练状态。"""
        user_id = event.get_sender_id()
        _success, msg = await self.adv_mgr.check_adventure_status(user_id)
        yield event.plain_result(msg)
