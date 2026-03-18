import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config_manager import ConfigManager
from ..data import DataBase
from ..models import Player
from .utils import player_required

__all__ = ["BlackMarketHandler"]

BLACK_MARKET_RULES = {
    "common": {"label": "普通丹", "price_multiplier": 2.0, "daily_limit": 5},
    "advanced": {"label": "强化丹", "price_multiplier": 2.5, "daily_limit": 3},
    "breakthrough": {"label": "突破丹", "price_multiplier": 3.0, "daily_limit": 2},
    "special": {"label": "稀有丹", "price_multiplier": 4.0, "daily_limit": 1},
}


class BlackMarketHandler:
    """黑市相关指令处理器。"""

    def __init__(self, db: DataBase, config_manager: ConfigManager):
        self.db = db
        self.config_manager = config_manager
        self._all_pills = None

    async def _ensure_table_exists(self):
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS black_market_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                pill_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                purchase_time INTEGER NOT NULL
            )
            """
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_black_market_user_time "
            "ON black_market_purchases(user_id, purchase_time)"
        )
        await self.db.conn.commit()

    def _get_all_pills(self) -> list:
        if self._all_pills is None:
            pills = []
            pills.extend(self.config_manager.pills_data.values())
            pills.extend(self.config_manager.exp_pills_data.values())
            pills.extend(self.config_manager.utility_pills_data.values())
            self._all_pills = pills
        return self._all_pills

    def _get_pill_rule_key(self, pill: dict) -> str:
        subtype = pill.get("subtype", "")
        if subtype == "breakthrough":
            return "breakthrough"
        if subtype in {"resurrection", "permanent_attribute"}:
            return "special"
        if subtype in {
            "combat_boost",
            "defensive_boost",
            "breakthrough_boost",
            "breakthrough_debuff",
            "protection",
            "special",
            "chaos_boost",
            "debuff",
            "cultivation_boost",
        }:
            return "advanced"
        return "common"

    def _get_pill_rule(self, pill: dict) -> dict:
        return BLACK_MARKET_RULES[self._get_pill_rule_key(pill)]

    def _get_black_market_price(self, pill: dict) -> int:
        original_price = int(pill.get("price", 0))
        rule = self._get_pill_rule(pill)
        return int(original_price * rule["price_multiplier"])

    def _get_today_start_timestamp(self) -> int:
        now = time.localtime()
        return int(
            time.mktime(
                time.struct_time(
                    (now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, now.tm_wday, now.tm_yday, now.tm_isdst)
                )
            )
        )

    async def _get_today_purchase_rows(self, user_id: str) -> list[tuple[str, int]]:
        today_start = self._get_today_start_timestamp()
        async with self.db.conn.execute(
            """
            SELECT pill_name, quantity
            FROM black_market_purchases
            WHERE user_id = ? AND purchase_time >= ?
            """,
            (user_id, today_start),
        ) as cursor:
            rows = await cursor.fetchall()
        return [(str(row[0]), int(row[1])) for row in rows]

    async def _get_today_category_count(self, user_id: str, category_key: str) -> int:
        name_to_pill = {pill.get("name"): pill for pill in self._get_all_pills()}
        total = 0
        for pill_name, quantity in await self._get_today_purchase_rows(user_id):
            pill = name_to_pill.get(pill_name)
            if pill and self._get_pill_rule_key(pill) == category_key:
                total += quantity
        return total

    async def _record_purchase(self, user_id: str, pill_name: str, quantity: int):
        await self.db.conn.execute(
            """
            INSERT INTO black_market_purchases (user_id, pill_name, quantity, purchase_time)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, pill_name, quantity, int(time.time())),
        )

    def _parse_buy_args(self, raw: str) -> tuple[str, int]:
        raw = (raw or "").strip()
        if raw.startswith("/"):
            raw = raw[1:]
        if raw.startswith("黑市购买"):
            raw = raw[len("黑市购买"):].strip()
        raw = raw.replace("　", " ")
        raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

        if not raw:
            return "", 1

        match = re.match(r"^(.+?)(?:\s+(\d+)|[xX*]\s*(\d+))$", raw)
        if match:
            name = match.group(1).strip()
            qty = int(match.group(2) or match.group(3) or "1")
            return name, max(1, qty)
        return raw, 1

    async def handle_black_market(self, event: AstrMessageEvent):
        await self._ensure_table_exists()

        pills = self._get_all_pills()
        if not pills:
            yield event.plain_result("🏴 黑市暂无货物。")
            return

        user_id = event.get_sender_id()
        lines = [
            "🏴 黑市·暗巷丹铺",
            "━━━━━━━━━━━━━━",
            "说明：黑市出售全部丹药，但按类别采用不同价格与限购。",
            "【黑市规则】",
        ]
        for key, rule in BLACK_MARKET_RULES.items():
            bought = await self._get_today_category_count(user_id, key)
            remaining = max(0, int(rule["daily_limit"]) - bought)
            lines.append(f"  {rule['label']}：{rule['price_multiplier']:.1f}倍价格，今日剩余 {remaining}/{rule['daily_limit']}")

        rank_groups: dict[str, list] = {}
        for pill in pills:
            rank = pill.get("rank", "未知")
            rank_groups.setdefault(rank, []).append(pill)

        rank_order = ["灵品", "珍品", "圣品", "帝品", "道品", "仙品", "神品"]
        for rank in rank_order:
            items = rank_groups.get(rank)
            if not items:
                continue
            lines.append(f"\n【{rank}丹药】")
            for pill in items:
                rule = self._get_pill_rule(pill)
                price = self._get_black_market_price(pill)
                lines.append(f"  {pill['name']} - {price:,}灵石（{rule['label']}）")

        lines.extend(["", "用法：/黑市购买 <丹药名> [数量]", "示例：/黑市购买 筑基丹 2"])
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_black_market_buy(self, player: Player, event: AstrMessageEvent, item_spec: str = ""):
        await self._ensure_table_exists()

        pill_name, quantity = self._parse_buy_args(item_spec or event.get_message_str())
        if not pill_name:
            yield event.plain_result("❌ 请指定要购买的丹药，例如：/黑市购买 筑基丹 2")
            return

        target_pill = None
        for pill in self._get_all_pills():
            if pill.get("name") == pill_name:
                target_pill = pill
                break
        if not target_pill:
            yield event.plain_result(f"❌ 黑市没有【{pill_name}】这种丹药。")
            return

        rule_key = self._get_pill_rule_key(target_pill)
        rule = self._get_pill_rule(target_pill)
        bought_today = await self._get_today_category_count(player.user_id, rule_key)
        remaining = int(rule["daily_limit"]) - bought_today
        if remaining <= 0:
            yield event.plain_result(f"❌ 今日【{rule['label']}】额度已用尽，当前类别每日限购 {rule['daily_limit']} 颗。")
            return
        if quantity > remaining:
            yield event.plain_result(f"❌ 今日【{rule['label']}】剩余可购 {remaining} 颗，无法购买 {quantity} 颗。")
            return

        black_price = self._get_black_market_price(target_pill)
        total_price = black_price * quantity
        if player.gold < total_price:
            yield event.plain_result(
                f"❌ 灵石不足\n"
                f"【{pill_name}】黑市价：{black_price:,} 灵石\n"
                f"类别：{rule['label']}\n"
                f"购买数量：{quantity}\n"
                f"需要灵石：{total_price:,}\n"
                f"当前灵石：{player.gold:,}"
            )
            return

        try:
            latest_player = await self.db.get_player_by_id(player.user_id)
            if not latest_player:
                yield event.plain_result("❌ 未找到角色数据。")
                return
            if latest_player.gold < total_price:
                yield event.plain_result(f"❌ 灵石不足，购买需要 {total_price:,} 灵石。")
                return

            latest_player.gold -= total_price
            inventory = latest_player.get_pills_inventory()
            inventory[pill_name] = inventory.get(pill_name, 0) + quantity
            latest_player.set_pills_inventory(inventory)
            await self.db.update_player(latest_player)
            await self._record_purchase(latest_player.user_id, pill_name, quantity)
            await self.db.conn.commit()

            remaining_after = remaining - quantity
            qty_text = f" x{quantity}" if quantity > 1 else ""
            yield event.plain_result(
                "🏴 黑市交易成功！\n"
                "━━━━━━━━━━━━━━\n"
                f"购买：{pill_name}{qty_text}\n"
                f"类别：{rule['label']}\n"
                f"花费：{total_price:,} 灵石\n"
                f"剩余灵石：{latest_player.gold:,}\n"
                f"当前类别剩余限购：{remaining_after}/{rule['daily_limit']}"
            )
        except Exception as exc:
            logger.error(f"黑市购买异常: {exc}")
            yield event.plain_result("❌ 黑市交易失败，请稍后重试。")
