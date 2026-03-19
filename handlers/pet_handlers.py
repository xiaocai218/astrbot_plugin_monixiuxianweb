"""灵宠指令处理器。"""

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.pet_manager import PetManager
from ..models import Player
from .utils import player_required

__all__ = ["PetHandlers"]


class PetHandlers:
    def __init__(self, db: DataBase, pet_mgr: PetManager):
        self.db = db
        self.pet_mgr = pet_mgr

    @player_required
    async def handle_market_info(self, player: Player, event: AstrMessageEvent):
        yield event.plain_result(await self.pet_mgr.get_market_info(player))

    @player_required
    async def handle_buy_egg(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.pet_mgr.purchase_egg(player)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_pet_barn(self, player: Player, event: AstrMessageEvent):
        yield event.plain_result(await self.pet_mgr.get_pet_barn_info(player.user_id))

    @player_required
    async def handle_start_hatching(self, player: Player, event: AstrMessageEvent, slot_text: str = ""):
        if not str(slot_text).strip().isdigit():
            yield event.plain_result("❌ 请输入正确的栏位编号，例如：/孵化灵宠 1")
            return
        success, msg = await self.pet_mgr.start_hatching(player.user_id, int(slot_text))
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_identify(self, player: Player, event: AstrMessageEvent, slot_text: str = ""):
        if not str(slot_text).strip().isdigit():
            yield event.plain_result("❌ 请输入正确的栏位编号，例如：/鉴定灵宠 1")
            return
        success, msg = await self.pet_mgr.identify_pet(player.user_id, int(slot_text))
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_equip(self, player: Player, event: AstrMessageEvent, slot_text: str = ""):
        if not str(slot_text).strip().isdigit():
            yield event.plain_result("❌ 请输入正确的栏位编号，例如：/携带灵宠 1")
            return
        success, msg = await self.pet_mgr.equip_pet(player.user_id, int(slot_text))
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_release(self, player: Player, event: AstrMessageEvent, slot_text: str = ""):
        if not str(slot_text).strip().isdigit():
            yield event.plain_result("❌ 请输入正确的栏位编号，例如：/释放灵宠 1")
            return
        success, msg = await self.pet_mgr.release_pet(player.user_id, int(slot_text))
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")
