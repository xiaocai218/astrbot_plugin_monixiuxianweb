"""天地灵眼处理器。"""

from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.spirit_eye_manager import SpiritEyeManager
from ..models import Player
from .utils import player_required

__all__ = ["SpiritEyeHandlers"]


class SpiritEyeHandlers:
    def __init__(self, db: DataBase, eye_mgr: SpiritEyeManager, combat_handlers):
        self.db = db
        self.mgr = eye_mgr
        self.combat_handlers = combat_handlers

    @player_required
    async def handle_spirit_eye_info(self, player: Player, event: AstrMessageEvent):
        info = await self.mgr.get_spirit_eye_info(player.user_id)
        yield event.plain_result(info)

    @player_required
    async def handle_claim(self, player: Player, event: AstrMessageEvent, eye_id: str = ""):
        eye_id_text = str(eye_id).strip()
        if not eye_id_text.isdigit():
            yield event.plain_result("❌ 请输入灵眼ID，例如：/抢占灵眼 1")
            return

        eye_id_value = int(eye_id_text)
        if eye_id_value <= 0:
            yield event.plain_result("❌ 请输入灵眼ID，例如：/抢占灵眼 1")
            return

        eye = await self.mgr.get_spirit_eye_by_id(eye_id_value)
        if not eye:
            yield event.plain_result("❌ 灵眼不存在。")
            return

        owner_id = str(eye["owner_id"]) if eye.get("owner_id") else ""
        owner_name = eye.get("owner_name") or "某人"
        is_confirmed = "确认" in (event.get_message_str() or "")

        if owner_id and owner_id == player.user_id:
            yield event.plain_result(f"❌ 该灵眼已由你占据：{eye['eye_name']}")
            return

        if not owner_id:
            success, msg = await self.mgr.claim_spirit_eye(player, eye_id_value)
            yield event.plain_result(msg)
            return

        if not is_confirmed:
            yield event.plain_result(
                f"⚠️ 灵眼【{eye['eye_name']}】当前由【{owner_name}】占据。\n"
                f"发送 /抢占灵眼 {eye_id_value} 确认 后将与对方决斗。\n"
                "败者 30 分钟内无法再次发起决斗。"
            )
            return

        success, duel_msg, result = await self.combat_handlers.execute_duel(player.user_id, owner_id)
        if not success:
            yield event.plain_result(duel_msg)
            return

        if result["winner"] != player.user_id:
            yield event.plain_result(f"{duel_msg}\n\n❌ 夺取失败，灵眼仍归【{owner_name}】所有。")
            return

        claim_success, claim_msg = await self.mgr.seize_spirit_eye(player, eye_id_value, owner_id)
        yield event.plain_result(f"{duel_msg}\n\n{claim_msg}")

    @player_required
    async def handle_collect(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.mgr.collect_spirit_eye(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_release(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.mgr.release_spirit_eye(player.user_id)
        yield event.plain_result(msg)
