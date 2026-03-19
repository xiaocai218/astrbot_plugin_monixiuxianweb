from astrbot.api.event import AstrMessageEvent

from ..data import DataBase
from ..managers.bounty_manager import BountyManager
from ..models import Player
from .utils import player_required

__all__ = ["BountyHandlers"]


class BountyHandlers:
    def __init__(self, db: DataBase, bounty_mgr: BountyManager):
        self.db = db
        self.bounty_mgr = bounty_mgr

    @player_required
    async def handle_bounty_list(self, player: Player, event: AstrMessageEvent):
        bounties = await self.bounty_mgr.get_bounty_list(player)

        lines = ["📜 悬赏任务 · 今日委托", "━━━━━━━━━━━━━━"]
        for bounty in bounties:
            reward = bounty.get("reward", {})
            lines.append(
                f"[{bounty['id']}] {bounty['name']} · {bounty.get('difficulty_name', '未知难度')} · {bounty.get('category', '任务')}\n"
                f"  - 目标数量：{bounty.get('count')} 次 | 时限：{bounty.get('time_limit', 0) // 60} 分钟\n"
                f"  - 奖励：{reward.get('stone', 0):,} 灵石 + {reward.get('exp', 0):,} 修为\n"
                f"  - 描述：{bounty.get('description', '')}"
            )
        lines.append("━━━━━━━━━━━━━━")
        lines.append("请输入 /接取悬赏 <编号> 来领取任务")

        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_accept_bounty(self, player: Player, event: AstrMessageEvent, bounty_id: str = ""):
        bounty_id_text = str(bounty_id).strip()
        if not bounty_id_text.isdigit():
            yield event.plain_result("❌ 请输入正确的悬赏编号，例如：/接取悬赏 1")
            return

        bounty_id_value = int(bounty_id_text)
        if bounty_id_value <= 0:
            yield event.plain_result("❌ 请输入正确的悬赏编号，例如：/接取悬赏 1")
            return

        success, msg = await self.bounty_mgr.accept_bounty(player, bounty_id_value)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_bounty_status(self, player: Player, event: AstrMessageEvent):
        _success, msg = await self.bounty_mgr.check_bounty_status(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_complete_bounty(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.bounty_mgr.complete_bounty(player)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")

    @player_required
    async def handle_abandon_bounty(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.bounty_mgr.abandon_bounty(player)
        prefix = "✅" if success else "❌"
        yield event.plain_result(f"{prefix} {msg}")
