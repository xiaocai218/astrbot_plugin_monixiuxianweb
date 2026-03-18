"""洞天福地处理器"""

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.blessed_land_manager import BlessedLandManager
from ..models import Player
from .utils import player_required

__all__ = ["BlessedLandHandlers"]


class BlessedLandHandlers:
    """洞天福地处理器"""

    def __init__(self, db: DataBase, blessed_land_mgr: BlessedLandManager):
        self.db = db
        self.mgr = blessed_land_mgr

    @player_required
    async def handle_blessed_land_info(self, player: Player, event: AstrMessageEvent):
        """查看洞天信息"""
        info = await self.mgr.get_blessed_land_info(player.user_id)
        yield event.plain_result(info)

    @player_required
    async def handle_purchase(self, player: Player, event: AstrMessageEvent, land_type: str = ""):
        """购买洞天"""
        land_type_text = str(land_type).strip()
        if not land_type_text.isdigit():
            yield event.plain_result(
                "🏔️ 购买洞天\n"
                "━━━━━━━━━━━━━━━\n"
                "1. 小洞天 - 10,000灵石 (+5%修炼)\n"
                "2. 中洞天 - 50,000灵石 (+10%修炼)\n"
                "3. 大洞天 - 200,000灵石 (+20%修炼)\n"
                "4. 福地 - 500,000灵石 (+30%修炼)\n"
                "5. 洞天福地 - 1,000,000灵石 (+50%修炼)\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 使用 /购买洞天 <编号>\n"
                "💡 已有洞天可使用 /置换洞天 <编号>"
            )
            return

        success, msg = await self.mgr.purchase_blessed_land(player, int(land_type_text))
        yield event.plain_result(msg)

    @player_required
    async def handle_replace(self, player: Player, event: AstrMessageEvent, land_type: str = ""):
        """置换洞天"""
        land_type_text = str(land_type).strip()
        if not land_type_text.isdigit():
            yield event.plain_result(
                "🏔️ 置换洞天\n"
                "━━━━━━━━━━━━━━━\n"
                "规则：旧洞天按原价 60% 折算抵扣，新洞天保留当前等级但受新类型等级上限约束。\n"
                "置换后会重置洞天收取时间，避免重复领取产出。\n"
                "1. 小洞天 - 10,000灵石\n"
                "2. 中洞天 - 50,000灵石\n"
                "3. 大洞天 - 200,000灵石\n"
                "4. 福地 - 500,000灵石\n"
                "5. 洞天福地 - 1,000,000灵石\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 使用 /置换洞天 <编号>"
            )
            return

        success, msg = await self.mgr.replace_blessed_land(player, int(land_type_text))
        yield event.plain_result(msg)

    @player_required
    async def handle_upgrade(self, player: Player, event: AstrMessageEvent):
        """升级洞天"""
        success, msg = await self.mgr.upgrade_blessed_land(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_collect(self, player: Player, event: AstrMessageEvent):
        """收取洞天产出"""
        success, msg = await self.mgr.collect_income(player)
        yield event.plain_result(msg)
