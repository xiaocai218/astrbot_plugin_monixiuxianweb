from __future__ import annotations

import secrets
import string
import time
from typing import Any

from ..data import DataBase
from ..models import Player


class WebBindingManager:
    """Web 绑定最小闭环管理器。"""

    BIND_CODE_EXPIRE_SECONDS = 600

    def __init__(self, db: DataBase):
        self.db = db

    async def create_bind_code(self, player: Player, platform: str, chat_user_id: str) -> tuple[bool, str]:
        await self.db.ensure_connection()
        now = int(time.time())
        expire_at = now + self.BIND_CODE_EXPIRE_SECONDS
        bind_code = self._generate_code()

        # 同一玩家同一平台只保留一条待使用绑定码，避免旧码堆积。
        await self.db.conn.execute(
            "DELETE FROM web_bind_keys WHERE user_id = ? AND platform = ? AND status = 'pending'",
            (player.user_id, platform),
        )
        await self.db.conn.execute(
            """
            INSERT INTO web_bind_keys (
                bind_code, user_id, platform, chat_id, status, created_at, expire_at, used_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, 0)
            """,
            (bind_code, player.user_id, platform, chat_user_id, now, expire_at),
        )
        await self.db.conn.commit()

        player_name = player.user_name or f"道友{player.user_id[:6]}"
        minutes = self.BIND_CODE_EXPIRE_SECONDS // 60
        return (
            True,
            "🌐 网页绑定码已生成\n"
            "━━━━━━━━━━━━━━━\n"
            f"玩家：{player_name}\n"
            f"绑定码：{bind_code}\n"
            f"有效期：{minutes} 分钟\n"
            "说明：后续 Web 端可使用该绑定码与当前聊天账号建立关联。\n"
            "如需重新生成，直接再次发送“网页绑定码”即可。",
        )

    async def bind_with_code(
        self,
        player: Player,
        bind_code: str,
        platform: str,
        chat_user_id: str,
        chat_user_name: str,
    ) -> tuple[bool, str]:
        await self.db.ensure_connection()
        bind_code = bind_code.strip().upper()
        now = int(time.time())

        async with self.db.conn.execute(
            """
            SELECT * FROM web_bind_keys
            WHERE bind_code = ? AND status = 'pending'
            LIMIT 1
            """,
            (bind_code,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False, "❌ 未找到可用的网页绑定码，可能已失效或已被使用。"

        if int(row["expire_at"] or 0) < now:
            await self.db.conn.execute(
                "UPDATE web_bind_keys SET status = 'expired' WHERE id = ?",
                (row["id"],),
            )
            await self.db.conn.commit()
            return False, "❌ 该绑定码已过期，请重新生成。"

        if str(row["user_id"]) != str(player.user_id):
            return False, "❌ 该绑定码不属于当前角色，请确认后再试。"

        await self.db.conn.execute(
            """
            INSERT INTO web_chat_bindings (
                user_id, platform, chat_user_id, chat_user_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, platform) DO UPDATE SET
                chat_user_id = excluded.chat_user_id,
                chat_user_name = excluded.chat_user_name,
                updated_at = excluded.updated_at
            """,
            (player.user_id, platform, chat_user_id, chat_user_name, now, now),
        )
        await self.db.conn.execute(
            "UPDATE web_bind_keys SET status = 'used', used_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        await self.db.conn.commit()

        player_name = player.user_name or f"道友{player.user_id[:6]}"
        return (
            True,
            "✅ 网页绑定成功\n"
            "━━━━━━━━━━━━━━━\n"
            f"玩家：{player_name}\n"
            f"平台：{platform}\n"
            f"账号：{chat_user_name or chat_user_id}\n"
            "当前已完成聊天端绑定，后续可继续接入网页登录能力。",
        )

    async def get_binding_status(self, player: Player, platform: str) -> str:
        await self.db.ensure_connection()

        async with self.db.conn.execute(
            """
            SELECT chat_user_id, chat_user_name, created_at, updated_at
            FROM web_chat_bindings
            WHERE user_id = ? AND platform = ?
            LIMIT 1
            """,
            (player.user_id, platform),
        ) as cursor:
            binding = await cursor.fetchone()

        async with self.db.conn.execute(
            """
            SELECT bind_code, expire_at
            FROM web_bind_keys
            WHERE user_id = ? AND platform = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (player.user_id, platform),
        ) as cursor:
            pending = await cursor.fetchone()

        lines = ["🌐 网页绑定状态", "━━━━━━━━━━━━━━━", f"平台：{platform}"]
        if binding:
            lines.append("状态：已绑定")
            lines.append(f"聊天账号：{binding['chat_user_name'] or binding['chat_user_id']}")
        else:
            lines.append("状态：未绑定")

        if pending:
            remaining = max(0, int(pending["expire_at"] or 0) - int(time.time()))
            lines.append(f"待使用绑定码：{pending['bind_code']}")
            lines.append(f"剩余有效期：{remaining // 60}分{remaining % 60}秒")
        else:
            lines.append("待使用绑定码：无")

        lines.append("可用指令：网页绑定码 / 绑定网页 <绑定码>")
        return "\n".join(lines)

    @staticmethod
    def _generate_code(length: int = 8) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))
