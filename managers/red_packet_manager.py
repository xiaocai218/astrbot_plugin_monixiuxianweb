"""仙缘红包管理器。"""

from __future__ import annotations

import random
import time
from typing import Tuple

from ..data import DataBase
from ..models import Player

__all__ = ["RedPacketManager"]


RED_PACKET_CONFIG = {
    "min_amount": 100,
    "min_count": 1,
    "max_count": 50,
    "expire_seconds": 3600,
    "min_per_packet": 1,
}


class RedPacketManager:
    """处理仙缘红包的发放、领取和过期退款。"""

    def __init__(self, db: DataBase):
        self.db = db

    async def ensure_tables(self):
        """确保红包相关表存在。"""
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS red_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_code TEXT NOT NULL UNIQUE,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL,
                total_amount INTEGER NOT NULL,
                total_count INTEGER NOT NULL,
                remaining_amount INTEGER NOT NULL,
                remaining_count INTEGER NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                refunded INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                expire_at INTEGER NOT NULL
            )
            """
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_red_packets_group_status ON red_packets(group_id, status, created_at)"
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_red_packets_sender_status ON red_packets(sender_id, status)"
        )
        await self.db.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS red_packet_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL,
                claimed_at INTEGER NOT NULL,
                UNIQUE(packet_id, user_id),
                FOREIGN KEY(packet_id) REFERENCES red_packets(id) ON DELETE CASCADE
            )
            """
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_red_packet_claims_packet ON red_packet_claims(packet_id)"
        )
        await self.db.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_red_packet_claims_user ON red_packet_claims(user_id)"
        )
        await self.db.conn.commit()

    def _generate_packet_code(self) -> str:
        return f"rp_{int(time.time())}_{random.randint(1000, 9999)}"

    def _split_amount(self, total_amount: int, count: int) -> list[int]:
        if count <= 1:
            return [total_amount]

        min_per = RED_PACKET_CONFIG["min_per_packet"]
        amounts: list[int] = []
        remaining = total_amount

        for index in range(count - 1):
            rest_count = count - index - 1
            max_can_take = remaining - rest_count * min_per
            if max_can_take <= min_per:
                amount = min_per
            else:
                average = max(min_per, remaining // (rest_count + 1))
                lower = max(min_per, average // 2)
                upper = max(lower, min(max_can_take, average * 2))
                amount = random.randint(lower, upper)

            amounts.append(amount)
            remaining -= amount

        amounts.append(remaining)
        random.shuffle(amounts)
        return amounts

    async def _refund_expired_packets(self, group_id: str | None = None):
        """退回过期未领完的红包余额。"""
        now = int(time.time())
        sql = (
            "SELECT id, sender_id, remaining_amount FROM red_packets "
            "WHERE status = 'active' AND refunded = 0 AND expire_at <= ?"
        )
        params: tuple = (now,)
        if group_id:
            sql += " AND group_id = ?"
            params = (now, group_id)

        async with self.db.conn.execute(sql, params) as cursor:
            expired_packets = await cursor.fetchall()

        if not expired_packets:
            return

        for packet in expired_packets:
            refund_amount = int(packet["remaining_amount"] or 0)
            sender = await self.db.get_player_by_id(packet["sender_id"])
            if sender and refund_amount > 0:
                sender.gold += refund_amount
                await self.db.update_player(sender, commit=False)

            await self.db.conn.execute(
                """
                UPDATE red_packets
                SET status = 'expired', refunded = 1, remaining_amount = 0, remaining_count = 0
                WHERE id = ?
                """,
                (packet["id"],),
            )

        await self.db.conn.commit()

    async def create_packet(
        self,
        sender: Player,
        group_id: str,
        total_amount: int,
        count: int,
        message: str = "",
    ) -> Tuple[bool, str]:
        """发放一个仙缘红包。"""
        await self.ensure_tables()
        await self._refund_expired_packets(group_id)

        if total_amount < RED_PACKET_CONFIG["min_amount"]:
            return False, f"红包总金额至少需要 {RED_PACKET_CONFIG['min_amount']} 灵石。"
        if count < RED_PACKET_CONFIG["min_count"] or count > RED_PACKET_CONFIG["max_count"]:
            return False, (
                f"红包份数需要在 {RED_PACKET_CONFIG['min_count']}-{RED_PACKET_CONFIG['max_count']} 之间。"
            )
        if total_amount < count * RED_PACKET_CONFIG["min_per_packet"]:
            return False, "红包总金额不足以覆盖每份至少 1 灵石。"
        if sender.gold < total_amount:
            return False, f"灵石不足，当前仅有 {sender.gold:,} 灵石。"

        now = int(time.time())
        packet_code = self._generate_packet_code()
        sender_name = sender.user_name or f"道友{sender.user_id[:6]}"
        blessing = message.strip() if message and message.strip() else "愿诸位仙缘丰厚，福运自来。"

        sender.gold -= total_amount
        await self.db.update_player(sender, commit=False)
        await self.db.conn.execute(
            """
            INSERT INTO red_packets (
                packet_code, sender_id, sender_name, group_id,
                total_amount, total_count, remaining_amount, remaining_count,
                message, status, refunded, created_at, expire_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)
            """,
            (
                packet_code,
                sender.user_id,
                sender_name,
                str(group_id),
                total_amount,
                count,
                total_amount,
                count,
                blessing,
                now,
                now + RED_PACKET_CONFIG["expire_seconds"],
            ),
        )
        await self.db.conn.commit()

        return True, (
            "🧧 仙缘红包已发出\n"
            "━━━━━━━━━━━━━━━\n"
            f"发送者：{sender_name}\n"
            f"总金额：{total_amount:,} 灵石\n"
            f"份数：{count}\n"
            f"祝福：{blessing}\n"
            f"有效期：{RED_PACKET_CONFIG['expire_seconds'] // 60} 分钟\n"
            "发送 `/抢仙缘` 即可领取。"
        )

    async def grab_packet(self, player: Player, group_id: str) -> Tuple[bool, str]:
        """领取当前群内最早的一份有效红包。"""
        await self.ensure_tables()
        await self._refund_expired_packets(group_id)

        async with self.db.conn.execute(
            """
            SELECT * FROM red_packets
            WHERE group_id = ? AND status = 'active'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (str(group_id),),
        ) as cursor:
            packet = await cursor.fetchone()

        if not packet:
            return False, "当前没有可领取的仙缘红包。"

        async with self.db.conn.execute(
            "SELECT 1 FROM red_packet_claims WHERE packet_id = ? AND user_id = ?",
            (packet["id"], player.user_id),
        ) as cursor:
            already_claimed = await cursor.fetchone()
        if already_claimed:
            return False, "你已经领取过这个仙缘红包了。"

        remaining_amount = int(packet["remaining_amount"] or 0)
        remaining_count = int(packet["remaining_count"] or 0)
        if remaining_count <= 0 or remaining_amount <= 0:
            await self.db.conn.execute(
                "UPDATE red_packets SET status = 'finished', remaining_amount = 0, remaining_count = 0 WHERE id = ?",
                (packet["id"],),
            )
            await self.db.conn.commit()
            return False, "这个仙缘红包已经被抢完了。"

        amounts = self._split_amount(remaining_amount, remaining_count)
        amount = amounts[0]
        new_remaining_amount = remaining_amount - amount
        new_remaining_count = remaining_count - 1
        new_status = "finished" if new_remaining_count <= 0 else "active"

        now = int(time.time())
        player.gold += amount
        await self.db.update_player(player, commit=False)
        await self.db.conn.execute(
            """
            INSERT INTO red_packet_claims (packet_id, user_id, user_name, amount, claimed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                packet["id"],
                player.user_id,
                player.user_name or f"道友{player.user_id[:6]}",
                amount,
                now,
            ),
        )
        await self.db.conn.execute(
            """
            UPDATE red_packets
            SET remaining_amount = ?, remaining_count = ?, status = ?
            WHERE id = ?
            """,
            (new_remaining_amount, new_remaining_count, new_status, packet["id"]),
        )
        await self.db.conn.commit()

        lines = [
            "🎉 抢到仙缘红包",
            "━━━━━━━━━━━━━━━",
            f"发送者：{packet['sender_name']}",
            f"你抢到：{amount:,} 灵石",
            f"你的灵石：{player.gold:,}",
            f"剩余份数：{new_remaining_count}/{packet['total_count']}",
        ]
        if new_status == "finished":
            lines.append("这个仙缘红包已经被抢完了。")
        return True, "\n".join(lines)

    async def get_info(self) -> str:
        """返回仙缘红包帮助说明。"""
        await self.ensure_tables()
        return (
            "🧧 仙缘红包说明\n"
            "━━━━━━━━━━━━━━━\n"
            "发放格式：/发仙缘 <金额> <份数> [祝福语]\n"
            "领取命令：/抢仙缘\n"
            f"最低金额：{RED_PACKET_CONFIG['min_amount']} 灵石\n"
            f"份数范围：{RED_PACKET_CONFIG['min_count']}-{RED_PACKET_CONFIG['max_count']}\n"
            f"有效期：{RED_PACKET_CONFIG['expire_seconds'] // 60} 分钟\n"
            "过期未领完的部分会自动退回发送者。"
        )
