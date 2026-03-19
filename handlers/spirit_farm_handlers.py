"""灵田指令处理器。"""

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.spirit_farm_manager import SpiritFarmManager
from ..models import Player
from .utils import player_required

__all__ = ["SpiritFarmHandlers"]


class SpiritFarmHandlers:
    def __init__(self, db: DataBase, farm_mgr: SpiritFarmManager):
        self.db = db
        self.mgr = farm_mgr

    @player_required
    async def handle_farm_info(self, player: Player, event: AstrMessageEvent):
        info = await self.mgr.get_farm_info(player.user_id)
        yield event.plain_result(info)

    @player_required
    async def handle_create_farm(self, player: Player, event: AstrMessageEvent):
        _success, msg = await self.mgr.create_farm(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_plant(self, player: Player, event: AstrMessageEvent, herb_name: str = ""):
        if not herb_name.strip():
            yield event.plain_result(
                "🌱 可种植的灵草\n"
                "━━━━━━━━━━━━━━\n"
                "灵草 - Lv.1 / 1小时 / 修为+200 / 灵石+30 / 种植费20\n"
                "血灵草 - Lv.1 / 2小时 / 修为+600 / 灵石+80 / 种植费50\n"
                "冰心草 - Lv.2 / 4小时 / 修为+1500 / 灵石+200 / 种植费120\n"
                "火焰花 - Lv.3 / 8小时 / 修为+3500 / 灵石+500 / 种植费300\n"
                "九叶灵芝 - Lv.4 / 24小时 / 修为+10000 / 灵石+1200 / 种植费800\n"
                "━━━━━━━━━━━━━━\n"
                "请输入 /种植 <灵草名>"
            )
            return

        _success, msg = await self.mgr.plant_herb(player, herb_name.strip())
        yield event.plain_result(msg)

    @player_required
    async def handle_harvest(self, player: Player, event: AstrMessageEvent):
        _success, msg = await self.mgr.harvest(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_upgrade_farm(self, player: Player, event: AstrMessageEvent):
        _success, msg = await self.mgr.upgrade_farm(player)
        yield event.plain_result(msg)
