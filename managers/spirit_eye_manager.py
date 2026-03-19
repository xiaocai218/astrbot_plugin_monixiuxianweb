"""天地灵眼系统管理器。"""

import random
import time
from typing import Dict, List, Optional, Tuple

from ..data import DataBase
from ..models import Player

__all__ = ["SpiritEyeManager"]


SPIRIT_EYE_TYPES = {
    1: {"name": "下品灵眼", "exp_per_hour": 500, "spawn_rate": 50},
    2: {"name": "中品灵眼", "exp_per_hour": 2000, "spawn_rate": 30},
    3: {"name": "上品灵眼", "exp_per_hour": 8000, "spawn_rate": 15},
    4: {"name": "极品灵眼", "exp_per_hour": 30000, "spawn_rate": 5},
}


class SpiritEyeManager:
    MIN_EYE_COUNT = 6
    HARD_MAX_EYE_COUNT = 15
    PLAYER_STEP = 5

    def __init__(self, db: DataBase):
        self.db = db

    async def get_total_player_count(self) -> int:
        async with self.db.conn.execute("SELECT COUNT(*) AS c FROM players") as cursor:
            row = await cursor.fetchone()
            return int(row["c"] or 0) if row else 0

    async def get_total_spirit_eye_count(self) -> int:
        async with self.db.conn.execute("SELECT COUNT(*) AS c FROM spirit_eyes") as cursor:
            row = await cursor.fetchone()
            return int(row["c"] or 0) if row else 0

    async def get_spirit_eye_spawn_cap(self) -> Tuple[int, int, int]:
        player_count = await self.get_total_player_count()
        total_eyes = await self.get_total_spirit_eye_count()
        dynamic_cap = self.MIN_EYE_COUNT + (player_count // self.PLAYER_STEP)
        max_eyes = max(self.MIN_EYE_COUNT, min(self.HARD_MAX_EYE_COUNT, dynamic_cap))
        return player_count, total_eyes, max_eyes

    async def get_user_spirit_eye(self, user_id: str) -> Optional[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM spirit_eyes WHERE owner_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_spirit_eye_by_id(self, eye_id: int) -> Optional[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM spirit_eyes WHERE eye_id = ?",
            (eye_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_spirit_eyes(self) -> List[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM spirit_eyes ORDER BY eye_id ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_available_spirit_eyes(self) -> List[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM spirit_eyes WHERE owner_id IS NULL OR owner_id = '' ORDER BY eye_id ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def spawn_spirit_eye(self) -> Tuple[bool, str]:
        player_count, total_eyes, max_eyes = await self.get_spirit_eye_spawn_cap()
        if total_eyes >= max_eyes:
            return False, f"\u5f53\u524d\u7075\u773c\u603b\u6570\u5df2\u8fbe\u5230\u4e0a\u9650\uff08{total_eyes}/{max_eyes}\uff09\uff0c\u672c\u8f6e\u4e0d\u518d\u751f\u6210\u65b0\u7075\u773c\u3002"

        roll = random.randint(1, 100)
        eye_type = 1
        cumulative = 0
        for spirit_eye_type, config in SPIRIT_EYE_TYPES.items():
            cumulative += config["spawn_rate"]
            if roll <= cumulative:
                eye_type = spirit_eye_type
                break

        config = SPIRIT_EYE_TYPES[eye_type]
        await self.db.conn.execute(
            """
            INSERT INTO spirit_eyes (eye_type, eye_name, exp_per_hour, spawn_time)
            VALUES (?, ?, ?, ?)
            """,
            (eye_type, config["name"], config["exp_per_hour"], int(time.time())),
        )
        await self.db.conn.commit()
        return (
            True,
            f"\u5929\u5730\u95f4\u51fa\u73b0\u4e86\u4e00\u5904\u3010{config['name']}\u3011\uff01\u901f\u6765\u62a2\u5360\uff01\n"
            f"\u5f53\u524d\u7075\u773c\u603b\u6570\uff1a{total_eyes + 1}/{max_eyes}\uff08\u73a9\u5bb6\u6570\uff1a{player_count}\uff09",
        )

    async def claim_spirit_eye(self, player: Player, eye_id: int) -> Tuple[bool, str]:
        existing = await self.get_user_spirit_eye(player.user_id)
        if existing:
            return False, f"❌ 你已占据【{existing['eye_name']}】，无法再抢占。"

        eye = await self.get_spirit_eye_by_id(eye_id)
        if not eye:
            return False, "❌ 灵眼不存在。"

        if eye["owner_id"]:
            return False, f"❌ 此灵眼已被【{eye['owner_name'] or '某人'}】占据。"

        now = int(time.time())
        try:
            cursor = await self.db.conn.execute(
                """
                UPDATE spirit_eyes
                SET owner_id = ?, owner_name = ?, claim_time = ?, last_collect_time = ?
                WHERE eye_id = ? AND (owner_id IS NULL OR owner_id = '')
                """,
                (player.user_id, player.user_name or player.user_id[:8], now, now, eye_id),
            )
            if cursor.rowcount == 0:
                await self.db.conn.rollback()
                return False, "❌ 抢占失败，灵眼已被他人占据。"

            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

        return True, (
            f"✅ 成功抢占【{eye['eye_name']}】！\n"
            f"每小时可获得 {eye['exp_per_hour']:,} 修为\n"
            "使用 /灵眼收取 领取收益"
        )

    async def seize_spirit_eye(self, player: Player, eye_id: int, expected_owner_id: str) -> Tuple[bool, str]:
        existing = await self.get_user_spirit_eye(player.user_id)
        if existing:
            return False, f"❌ 你已占据【{existing['eye_name']}】，无法再抢占。"

        eye = await self.get_spirit_eye_by_id(eye_id)
        if not eye:
            return False, "❌ 灵眼不存在。"

        if not eye["owner_id"]:
            return False, "❌ 该灵眼已变为无主，请重新执行抢占。"

        if str(eye["owner_id"]) != str(expected_owner_id):
            return False, "❌ 灵眼归属已发生变化，请重新查看灵眼信息。"

        now = int(time.time())
        try:
            cursor = await self.db.conn.execute(
                """
                UPDATE spirit_eyes
                SET owner_id = ?, owner_name = ?, claim_time = ?, last_collect_time = ?
                WHERE eye_id = ? AND owner_id = ?
                """,
                (player.user_id, player.user_name or player.user_id[:8], now, now, eye_id, expected_owner_id),
            )
            if cursor.rowcount == 0:
                await self.db.conn.rollback()
                return False, "❌ 抢占失败，灵眼归属已变化。"

            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

        return True, (
            f"✅ 你击败了原主人，成功夺取【{eye['eye_name']}】！\n"
            f"每小时可获得 {eye['exp_per_hour']:,} 修为\n"
            "使用 /灵眼收取 领取收益"
        )

    async def collect_spirit_eye(self, player: Player) -> Tuple[bool, str]:
        eye = await self.get_user_spirit_eye(player.user_id)
        if not eye:
            return False, "❌ 你还没有占据灵眼。"

        last_collect = eye.get("last_collect_time") or eye.get("claim_time", 0)
        now = int(time.time())
        hours_passed = (now - last_collect) / 3600
        if hours_passed < 1:
            remaining = int(3600 - (now - last_collect))
            return False, f"❌ 收取冷却中，还需 {remaining // 60} 分钟。"

        hours = min(24, int(hours_passed))
        exp_income = eye["exp_per_hour"] * hours
        player.experience += exp_income
        await self.db.update_player(player)

        await self.db.conn.execute(
            "UPDATE spirit_eyes SET last_collect_time = ? WHERE owner_id = ?",
            (now, player.user_id),
        )
        await self.db.conn.commit()

        return True, (
            "✅ 灵眼收取成功！\n"
            "━━━━━━━━\n"
            f"【{eye['eye_name']}】\n"
            f"累计时长：{hours} 小时\n"
            f"获得修为：{exp_income:,}"
        )

    async def release_spirit_eye(self, user_id: str) -> Tuple[bool, str]:
        eye = await self.get_user_spirit_eye(user_id)
        if not eye:
            return False, "❌ 你没有占据灵眼。"

        try:
            await self.db.conn.execute(
                """
                UPDATE spirit_eyes
                SET owner_id = NULL, owner_name = NULL, claim_time = NULL, last_collect_time = 0
                WHERE owner_id = ?
                """,
                (user_id,),
            )
            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

        return True, f"已释放【{eye['eye_name']}】。"

    async def get_spirit_eye_info(self, user_id: str) -> str:
        my_eye = await self.get_user_spirit_eye(user_id)
        eyes = await self.get_all_spirit_eyes()

        lines = ["👁️ 天地灵眼", "━━━━━━━━"]
        if my_eye:
            now = int(time.time())
            hours = (now - my_eye.get("claim_time", now)) / 3600
            pending = int(min(24, hours) * my_eye["exp_per_hour"])
            lines.append(f"【我的灵眼】{my_eye['eye_name']}")
            lines.append(f"每小时：+{my_eye['exp_per_hour']:,} 修为")
            lines.append(f"待收取：约 +{pending:,} 修为")
            lines.append("")

        if eyes:
            lines.append("【灵眼列表】")
            for eye in eyes[:10]:
                owner_name = eye["owner_name"] if eye["owner_id"] else "无主"
                lines.append(
                    f"  [{eye['eye_id']}] {eye['eye_name']} (+{eye['exp_per_hour']:,}/小时) - {owner_name}"
                )
            lines.append("")
            lines.append("【抢夺规则】")
            lines.append("  无主灵眼：直接发送 /抢占灵眼 <ID>")
            lines.append("  有主灵眼：发送 /抢占灵眼 <ID> 确认")
            lines.append("  抢夺方式：确认后立即与当前主人决斗")
            lines.append("  失败限制：决斗败者 30 分钟内无法再次发起决斗")
        else:
            lines.append("当前没有灵眼。")

        return "\n".join(lines)
