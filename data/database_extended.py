"""
数据库扩展层，封装宗门、Boss、秘境、传承、用户忙碌状态、
银行、悬赏、赠予等系统的 CRUD 操作。
"""

import json
import time
from dataclasses import fields
from typing import List, Optional

import aiosqlite

from ..battle_hp_utils import merge_battle_hp_state
from ..models import Player
from ..models_extended import Boss, BuffInfo, ImpartInfo, Rift, Sect, UserCd

PLAYER_FIELDS = {field.name for field in fields(Player)}


class DatabaseExtended:
    """数据库扩展操作类。"""

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create_sect(self, sect: Sect):
        """创建宗门并返回新宗门 ID。"""
        await self.conn.execute(
            """
            INSERT INTO sects (
                sect_name, sect_owner, sect_scale, sect_used_stone,
                sect_fairyland, sect_materials, mainbuff, secbuff, elixir_room_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sect.sect_name,
                sect.sect_owner,
                sect.sect_scale,
                sect.sect_used_stone,
                sect.sect_fairyland,
                sect.sect_materials,
                sect.mainbuff,
                sect.secbuff,
                sect.elixir_room_level,
            ),
        )
        await self.conn.commit()
        async with self.conn.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def get_sect_by_id(self, sect_id: int) -> Optional[Sect]:
        """按 ID 查询宗门。"""
        async with self.conn.execute("SELECT * FROM sects WHERE sect_id = ?", (sect_id,)) as cursor:
            row = await cursor.fetchone()
        return Sect(**dict(row)) if row else None

    async def get_sect_by_owner(self, owner_id: str) -> Optional[Sect]:
        """按宗主 ID 查询宗门。"""
        async with self.conn.execute("SELECT * FROM sects WHERE sect_owner = ?", (owner_id,)) as cursor:
            row = await cursor.fetchone()
        return Sect(**dict(row)) if row else None

    async def get_sect_by_name(self, sect_name: str) -> Optional[Sect]:
        """按宗门名查询宗门。"""
        async with self.conn.execute("SELECT * FROM sects WHERE sect_name = ?", (sect_name,)) as cursor:
            row = await cursor.fetchone()
        return Sect(**dict(row)) if row else None

    async def update_sect(self, sect: Sect):
        """更新宗门信息。"""
        await self.conn.execute(
            """
            UPDATE sects SET
                sect_name = ?, sect_owner = ?, sect_scale = ?, sect_used_stone = ?,
                sect_fairyland = ?, sect_materials = ?, mainbuff = ?, secbuff = ?,
                elixir_room_level = ?
            WHERE sect_id = ?
            """,
            (
                sect.sect_name,
                sect.sect_owner,
                sect.sect_scale,
                sect.sect_used_stone,
                sect.sect_fairyland,
                sect.sect_materials,
                sect.mainbuff,
                sect.secbuff,
                sect.elixir_room_level,
                sect.sect_id,
            ),
        )
        await self.conn.commit()

    async def delete_sect(self, sect_id: int):
        """删除宗门。"""
        await self.conn.execute("DELETE FROM sects WHERE sect_id = ?", (sect_id,))
        await self.conn.commit()

    async def get_all_sects(self) -> List[Sect]:
        """按建设度倒序获取全部宗门。"""
        async with self.conn.execute("SELECT * FROM sects ORDER BY sect_scale DESC") as cursor:
            rows = await cursor.fetchall()
        return [Sect(**dict(row)) for row in rows]

    async def update_sect_materials(self, sect_id: int, materials: int, operation: int = 1):
        """更新宗门材料。"""
        if operation == 1:
            await self.conn.execute(
                "UPDATE sects SET sect_materials = sect_materials + ? WHERE sect_id = ?",
                (materials, sect_id),
            )
        else:
            await self.conn.execute(
                "UPDATE sects SET sect_materials = sect_materials - ? WHERE sect_id = ?",
                (materials, sect_id),
            )
        await self.conn.commit()

    async def donate_to_sect(self, sect_id: int, stone_num: int):
        """宗门捐献，同时增加建设度。"""
        await self.conn.execute(
            """
            UPDATE sects SET
                sect_used_stone = sect_used_stone + ?,
                sect_scale = sect_scale + ?
            WHERE sect_id = ?
            """,
            (stone_num, stone_num * 10, sect_id),
        )
        await self.conn.commit()

    async def create_buff_info(self, user_id: str):
        """初始化用户 buff 记录。"""
        await self.conn.execute(
            """
            INSERT INTO buff_info (
                user_id, main_buff, sec_buff, faqi_buff, fabao_weapon,
                armor_buff, atk_buff, blessed_spot, sub_buff
            ) VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0)
            """,
            (user_id,),
        )
        await self.conn.commit()

    async def get_buff_info(self, user_id: str) -> Optional[BuffInfo]:
        """获取用户 buff 信息。"""
        async with self.conn.execute("SELECT * FROM buff_info WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return BuffInfo(**dict(row)) if row else None

    async def update_buff_info(self, buff_info: BuffInfo):
        """更新用户 buff 信息。"""
        await self.conn.execute(
            """
            UPDATE buff_info SET
                main_buff = ?, sec_buff = ?, faqi_buff = ?, fabao_weapon = ?,
                armor_buff = ?, atk_buff = ?, blessed_spot = ?, sub_buff = ?
            WHERE user_id = ?
            """,
            (
                buff_info.main_buff,
                buff_info.sec_buff,
                buff_info.faqi_buff,
                buff_info.fabao_weapon,
                buff_info.armor_buff,
                buff_info.atk_buff,
                buff_info.blessed_spot,
                buff_info.sub_buff,
                buff_info.user_id,
            ),
        )
        await self.conn.commit()

    async def update_user_main_buff(self, user_id: str, buff_id: int):
        """更新主修功法。"""
        await self.conn.execute("UPDATE buff_info SET main_buff = ? WHERE user_id = ?", (buff_id, user_id))
        await self.conn.commit()

    async def update_user_sec_buff(self, user_id: str, buff_id: int):
        """更新辅修功法。"""
        await self.conn.execute("UPDATE buff_info SET sec_buff = ? WHERE user_id = ?", (buff_id, user_id))
        await self.conn.commit()

    async def create_boss(self, boss: Boss) -> int:
        """创建 Boss。"""
        await self.conn.execute(
            """
            INSERT INTO boss (
                boss_name, boss_level, hp, max_hp, atk, defense,
                stone_reward, create_time, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                boss.boss_name,
                boss.boss_level,
                boss.hp,
                boss.max_hp,
                boss.atk,
                boss.defense,
                boss.stone_reward,
                boss.create_time,
                boss.status,
            ),
        )
        await self.conn.commit()
        async with self.conn.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def get_active_boss(self) -> Optional[Boss]:
        """获取当前存活 Boss。"""
        await self.ensure_bank_tables()
        async with self.conn.execute(
            "SELECT * FROM boss WHERE status = 1 ORDER BY create_time DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        return Boss(**dict(row)) if row else None

    async def get_boss_by_id(self, boss_id: int) -> Optional[Boss]:
        """按 ID 查询 Boss。"""
        async with self.conn.execute("SELECT * FROM boss WHERE boss_id = ?", (boss_id,)) as cursor:
            row = await cursor.fetchone()
        return Boss(**dict(row)) if row else None

    async def update_boss(self, boss: Boss):
        """更新 Boss 数据。"""
        await self.conn.execute(
            """
            UPDATE boss SET
                boss_name = ?, boss_level = ?, hp = ?, max_hp = ?, atk = ?,
                defense = ?, stone_reward = ?, status = ?
            WHERE boss_id = ?
            """,
            (
                boss.boss_name,
                boss.boss_level,
                boss.hp,
                boss.max_hp,
                boss.atk,
                boss.defense,
                boss.stone_reward,
                boss.status,
                boss.boss_id,
            ),
        )
        await self.conn.commit()

    async def defeat_boss(self, boss_id: int):
        """标记 Boss 为已击败。"""
        await self.conn.execute("UPDATE boss SET status = 0 WHERE boss_id = ?", (boss_id,))
        await self.conn.commit()

    async def create_rift(self, rift: Rift) -> int:
        """创建秘境。"""
        await self.conn.execute(
            """
            INSERT INTO rifts (
                rift_name, rift_level, required_level, rewards
            ) VALUES (?, ?, ?, ?)
            """,
            (rift.rift_name, rift.rift_level, rift.required_level, rift.rewards),
        )
        await self.conn.commit()
        async with self.conn.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def get_rift_by_id(self, rift_id: int) -> Optional[Rift]:
        """按 ID 查询秘境。"""
        async with self.conn.execute("SELECT * FROM rifts WHERE rift_id = ?", (rift_id,)) as cursor:
            row = await cursor.fetchone()
        return Rift(**dict(row)) if row else None

    async def get_all_rifts(self) -> List[Rift]:
        """获取全部秘境。"""
        async with self.conn.execute("SELECT * FROM rifts ORDER BY rift_level ASC") as cursor:
            rows = await cursor.fetchall()
        return [Rift(**dict(row)) for row in rows]

    async def create_impart_info(self, user_id: str):
        """初始化传承信息。"""
        await self.conn.execute(
            """
            INSERT INTO impart_info (
                user_id, impart_hp_per, impart_mp_per, impart_atk_per,
                impart_know_per, impart_burst_per
            ) VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0)
            """,
            (user_id,),
        )
        await self.conn.commit()

    async def get_impart_info(self, user_id: str) -> Optional[ImpartInfo]:
        """获取传承信息。"""
        async with self.conn.execute("SELECT * FROM impart_info WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return ImpartInfo(**dict(row)) if row else None

    async def update_impart_info(self, impart: ImpartInfo):
        """更新传承信息。"""
        await self.conn.execute(
            """
            UPDATE impart_info SET
                impart_hp_per = ?, impart_mp_per = ?, impart_atk_per = ?,
                impart_know_per = ?, impart_burst_per = ?
            WHERE user_id = ?
            """,
            (
                impart.impart_hp_per,
                impart.impart_mp_per,
                impart.impart_atk_per,
                impart.impart_know_per,
                impart.impart_burst_per,
                impart.user_id,
            ),
        )
        await self.conn.commit()

    async def create_user_cd(self, user_id: str):
        """初始化用户忙碌状态记录。"""
        await self.conn.execute(
            """
            INSERT INTO user_cd (user_id, type, create_time, scheduled_time)
            VALUES (?, 0, 0, 0)
            """,
            (user_id,),
        )
        await self.conn.commit()

    async def get_user_cd(self, user_id: str) -> Optional[UserCd]:
        """获取用户忙碌状态。"""
        async with self.conn.execute("SELECT * FROM user_cd WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return UserCd(**dict(row)) if row else None

    async def update_user_cd(self, user_cd: UserCd):
        """更新用户忙碌状态。"""
        await self.conn.execute(
            """
            UPDATE user_cd SET
                type = ?, create_time = ?, scheduled_time = ?, extra_data = ?
            WHERE user_id = ?
            """,
            (user_cd.type, user_cd.create_time, user_cd.scheduled_time, user_cd.extra_data, user_cd.user_id),
        )
        await self.conn.commit()

    async def set_user_busy(self, user_id: str, busy_type: int, scheduled_time: int = 0, extra_data: dict = None):
        """设置用户忙碌状态。"""
        current_extra = {}
        current_user_cd = await self.get_user_cd(user_id)
        if current_user_cd:
            current_extra = current_user_cd.get_extra_data()

        merged_extra = merge_battle_hp_state(current_extra, extra_data)
        extra_json = json.dumps(merged_extra, ensure_ascii=False)
        current_time = int(time.time())
        await self.conn.execute(
            """
            INSERT INTO user_cd (user_id, type, create_time, scheduled_time, extra_data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                type = excluded.type,
                create_time = excluded.create_time,
                scheduled_time = excluded.scheduled_time,
                extra_data = excluded.extra_data
            """,
            (user_id, busy_type, current_time, scheduled_time, extra_json),
        )
        await self.conn.commit()

    async def set_user_free(self, user_id: str):
        """设置用户为空闲状态。"""
        await self.set_user_busy(user_id, 0, 0)

    async def update_player_hp_mp(self, user_id: str, hp: int, mp: int):
        """更新玩家战斗 HP/MP。"""
        await self.conn.execute("UPDATE players SET hp = ?, mp = ? WHERE user_id = ?", (hp, mp, user_id))
        await self.conn.commit()

    async def update_player_sect_info(self, user_id: str, sect_id: int, sect_position: int):
        """更新玩家宗门信息。"""
        await self.conn.execute(
            "UPDATE players SET sect_id = ?, sect_position = ? WHERE user_id = ?",
            (sect_id, sect_position, user_id),
        )
        await self.conn.commit()

    async def update_player_sect_contribution(self, user_id: str, contribution: int):
        """更新玩家宗门贡献。"""
        await self.conn.execute(
            "UPDATE players SET sect_contribution = ? WHERE user_id = ?",
            (contribution, user_id),
        )
        await self.conn.commit()

    async def increment_sect_task_count(self, user_id: str, count: int = 1):
        """增加宗门任务完成次数。"""
        await self.conn.execute("UPDATE players SET sect_task = sect_task + ? WHERE user_id = ?", (count, user_id))
        await self.conn.commit()

    async def reset_sect_tasks(self):
        """重置所有玩家的宗门任务次数。"""
        await self.conn.execute("UPDATE players SET sect_task = 0")
        await self.conn.commit()

    async def reset_sect_elixir_get(self):
        """重置所有玩家的宗门丹药领取标记。"""
        await self.conn.execute("UPDATE players SET sect_elixir_get = 0")
        await self.conn.commit()

    async def get_sect_members(self, sect_id: int) -> List[Player]:
        """获取宗门成员列表。"""
        async with self.conn.execute(
            "SELECT * FROM players WHERE sect_id = ? ORDER BY sect_position ASC, level_index DESC",
            (sect_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [Player(**{key: value for key, value in dict(row).items() if key in PLAYER_FIELDS}) for row in rows]

    async def get_bank_account(self, user_id: str) -> Optional[dict]:
        """获取银行账户信息。"""
        async with self.conn.execute(
            "SELECT balance, last_interest_time FROM bank_accounts WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            return {"balance": row[0], "last_interest_time": row[1]}
        return None

    async def update_bank_account(self, user_id: str, balance: int, last_interest_time: int):
        """创建或更新银行账户。"""
        await self.conn.execute(
            """
            INSERT INTO bank_accounts (user_id, balance, last_interest_time)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance = excluded.balance,
                last_interest_time = excluded.last_interest_time
            """,
            (user_id, balance, last_interest_time),
        )
        await self.conn.commit()

    async def ensure_bounty_tables(self):
        """确保悬赏任务表存在。"""
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bounty_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                bounty_id INTEGER NOT NULL,
                bounty_name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_count INTEGER NOT NULL,
                current_progress INTEGER NOT NULL DEFAULT 0,
                rewards TEXT NOT NULL DEFAULT '{}',
                start_time INTEGER NOT NULL,
                expire_time INTEGER NOT NULL,
                status INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bounty_user ON bounty_tasks(user_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bounty_status_expire ON bounty_tasks(status, expire_time)")
        await self._repair_legacy_bounty_tasks()
        await self.conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bounty_active_unique
            ON bounty_tasks(user_id)
            WHERE status = 1
            """
        )
        await self.conn.commit()

    async def _repair_legacy_bounty_tasks(self):
        """修复历史脏数据，确保每位玩家最多只有一条进行中的悬赏。"""
        async with self.conn.execute(
            """
            SELECT user_id
            FROM bounty_tasks
            WHERE status = 1
            GROUP BY user_id
            HAVING COUNT(*) > 1
            """
        ) as cursor:
            duplicate_users = [row[0] async for row in cursor]

        for user_id in duplicate_users:
            async with self.conn.execute(
                """
                SELECT id
                FROM bounty_tasks
                WHERE user_id = ? AND status = 1
                ORDER BY start_time DESC, id DESC
                """,
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()

            if len(rows) <= 1:
                continue

            stale_ids = [row[0] for row in rows[1:]]
            placeholders = ",".join("?" for _ in stale_ids)
            await self.conn.execute(
                f"UPDATE bounty_tasks SET status = 3 WHERE id IN ({placeholders})",
                tuple(stale_ids),
            )

    async def ensure_bank_tables(self):
        """确保银行相关数据表存在。"""
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_accounts (
                user_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                last_interest_time INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await self._repair_legacy_bank_loans_schema()
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                principal INTEGER NOT NULL,
                interest_rate REAL NOT NULL,
                borrowed_at INTEGER NOT NULL,
                due_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                loan_type TEXT NOT NULL DEFAULT 'normal'
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                trans_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_loans_user ON bank_loans(user_id, status)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_loans_due ON bank_loans(status, due_at)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_trans_user ON bank_transactions(user_id, created_at DESC)")
        await self.conn.commit()

    async def _repair_legacy_bank_loans_schema(self):
        """修复旧版 bank_loans 上错误的唯一约束。"""
        async with self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'bank_loans'"
        ) as cursor:
            row = await cursor.fetchone()

        if not row or not row[0]:
            return

        normalized_sql = "".join(str(row[0]).lower().split())
        needs_rebuild = "unique(user_id,status)" in normalized_sql

        if not needs_rebuild:
            async with self.conn.execute("PRAGMA index_list(bank_loans)") as cursor:
                indexes = await cursor.fetchall()
            for index_row in indexes:
                if not bool(index_row[2]):
                    continue
                index_name = index_row[1]
                async with self.conn.execute(f"PRAGMA index_info({index_name})") as cursor:
                    columns = [info_row[2] async for info_row in cursor]
                if columns == ["user_id", "status"]:
                    needs_rebuild = True
                    break

        if not needs_rebuild:
            return

        await self.conn.execute("DROP TABLE IF EXISTS bank_loans_new")
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_loans_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                principal INTEGER NOT NULL,
                interest_rate REAL NOT NULL,
                borrowed_at INTEGER NOT NULL,
                due_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                loan_type TEXT NOT NULL DEFAULT 'normal'
            )
            """
        )
        await self.conn.execute(
            """
            INSERT INTO bank_loans_new (
                id, user_id, principal, interest_rate, borrowed_at, due_at, status, loan_type
            )
            SELECT id, user_id, principal, interest_rate, borrowed_at, due_at, status, loan_type
            FROM bank_loans
            """
        )
        await self.conn.execute("DROP TABLE bank_loans")
        await self.conn.execute("ALTER TABLE bank_loans_new RENAME TO bank_loans")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_loans_user ON bank_loans(user_id, status)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_loans_due ON bank_loans(status, due_at)")

    async def get_active_bounty(self, user_id: str) -> Optional[dict]:
        """获取当前进行中的悬赏。"""
        await self.ensure_bounty_tables()
        async with self.conn.execute(
            "SELECT * FROM bounty_tasks WHERE user_id = ? AND status = 1 ORDER BY start_time DESC, id DESC LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_bounty(
        self,
        user_id: str,
        bounty_id: int,
        bounty_name: str,
        target_type: str,
        target_count: int,
        rewards: str,
        expire_time: int,
    ):
        """创建悬赏任务。"""
        await self.conn.execute(
            """
            INSERT INTO bounty_tasks (
                user_id, bounty_id, bounty_name, target_type,
                target_count, current_progress, rewards,
                start_time, expire_time, status
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 1)
            """,
            (user_id, bounty_id, bounty_name, target_type, target_count, rewards, int(time.time()), expire_time),
        )
        await self.conn.commit()

    async def update_bounty_progress(self, user_id: str, progress: int):
        """更新悬赏进度。"""
        await self.conn.execute(
            "UPDATE bounty_tasks SET current_progress = ? WHERE user_id = ? AND status = 1",
            (progress, user_id),
        )
        await self.conn.commit()

    async def complete_bounty(self, user_id: str) -> bool:
        """完成悬赏。"""
        await self.conn.execute("UPDATE bounty_tasks SET status = 2 WHERE user_id = ? AND status = 1", (user_id,))
        await self.conn.commit()
        return True

    async def cancel_bounty(self, user_id: str):
        """放弃悬赏。"""
        await self.conn.execute("UPDATE bounty_tasks SET status = 0 WHERE user_id = ? AND status = 1", (user_id,))
        await self.conn.commit()

    async def ensure_system_config_table(self):
        """确保 system_config 表存在。"""
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER DEFAULT 0
            )
            """
        )
        await self.conn.commit()

    async def get_system_config(self, key: str) -> Optional[str]:
        """获取系统配置项。"""
        await self.ensure_system_config_table()
        async with self.conn.execute("SELECT value FROM system_config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def set_system_config(self, key: str, value: str):
        """设置系统配置项。"""
        now = int(time.time())
        await self.ensure_system_config_table()
        await self.conn.execute(
            """
            INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
            """,
            (key, value, now, value, now),
        )
        await self.conn.commit()

    async def create_pending_gift(
        self,
        receiver_id: str,
        sender_id: str,
        sender_name: str,
        item_name: str,
        count: int,
        expires_hours: int = 24,
    ) -> int:
        """创建赠予请求。"""
        now = int(time.time())
        expires_at = now + expires_hours * 3600
        await self.conn.execute(
            """
            INSERT INTO pending_gifts (
                receiver_id, sender_id, sender_name, item_name, count, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (receiver_id, sender_id, sender_name, item_name, count, now, expires_at),
        )
        await self.conn.commit()
        async with self.conn.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_pending_gift(self, receiver_id: str) -> Optional[dict]:
        """获取接收者最新一条未过期赠予请求。"""
        now = int(time.time())
        await self.cleanup_expired_gifts()
        async with self.conn.execute(
            """
            SELECT id, receiver_id, sender_id, sender_name, item_name, count, created_at, expires_at
            FROM pending_gifts
            WHERE receiver_id = ? AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (receiver_id, now),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "receiver_id": row[1],
            "sender_id": row[2],
            "sender_name": row[3],
            "item_name": row[4],
            "count": row[5],
            "created_at": row[6],
            "expires_at": row[7],
        }

    async def get_all_pending_gifts(self, receiver_id: str) -> List[dict]:
        """获取接收者全部未过期赠予请求。"""
        now = int(time.time())
        async with self.conn.execute(
            """
            SELECT id, receiver_id, sender_id, sender_name, item_name, count, created_at, expires_at
            FROM pending_gifts
            WHERE receiver_id = ? AND expires_at > ?
            ORDER BY created_at DESC
            """,
            (receiver_id, now),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "receiver_id": row[1],
                "sender_id": row[2],
                "sender_name": row[3],
                "item_name": row[4],
                "count": row[5],
                "created_at": row[6],
                "expires_at": row[7],
            }
            for row in rows
        ]

    async def delete_pending_gift(self, gift_id: int):
        """删除单条赠予请求。"""
        await self.conn.execute("DELETE FROM pending_gifts WHERE id = ?", (gift_id,))
        await self.conn.commit()

    async def delete_pending_gift_by_receiver(self, receiver_id: str):
        """删除接收者的全部赠予请求。"""
        await self.conn.execute("DELETE FROM pending_gifts WHERE receiver_id = ?", (receiver_id,))
        await self.conn.commit()

    async def cleanup_expired_gifts(self):
        """清理过期赠予请求。"""
        await self.conn.execute("DELETE FROM pending_gifts WHERE expires_at < ?", (int(time.time()),))
        await self.conn.commit()

    async def get_active_loan(self, user_id: str) -> Optional[dict]:
        """获取当前活跃贷款。"""
        async with self.conn.execute(
            """
            SELECT id, user_id, principal, interest_rate, borrowed_at, due_at, status, loan_type
            FROM bank_loans WHERE user_id = ? AND status = 'active'
            """,
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "user_id": row[1],
            "principal": row[2],
            "interest_rate": row[3],
            "borrowed_at": row[4],
            "due_at": row[5],
            "status": row[6],
            "loan_type": row[7],
        }

    async def create_loan(
        self,
        user_id: str,
        principal: int,
        interest_rate: float,
        borrowed_at: int,
        due_at: int,
        loan_type: str = "normal",
    ) -> int:
        """创建贷款记录。"""
        await self.conn.execute(
            """
            INSERT INTO bank_loans (user_id, principal, interest_rate, borrowed_at, due_at, status, loan_type)
            VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (user_id, principal, interest_rate, borrowed_at, due_at, loan_type),
        )
        await self.conn.commit()
        async with self.conn.execute("SELECT last_insert_rowid()") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def close_loan(self, loan_id: int):
        """关闭贷款。"""
        await self.conn.execute("UPDATE bank_loans SET status = 'closed' WHERE id = ?", (loan_id,))
        await self.conn.commit()

    async def mark_loan_overdue(self, loan_id: int):
        """标记贷款逾期。"""
        await self.conn.execute("UPDATE bank_loans SET status = 'overdue' WHERE id = ?", (loan_id,))
        await self.conn.commit()

    async def get_overdue_loans(self, current_time: int) -> List[dict]:
        """获取全部逾期贷款。"""
        loans = []
        async with self.conn.execute(
            """
            SELECT id, user_id, principal, interest_rate, borrowed_at, due_at, loan_type
            FROM bank_loans WHERE status = 'active' AND due_at < ?
            """,
            (current_time,),
        ) as cursor:
            async for row in cursor:
                loans.append(
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "principal": row[2],
                        "interest_rate": row[3],
                        "borrowed_at": row[4],
                        "due_at": row[5],
                        "loan_type": row[6],
                    }
                )
        return loans

    async def add_bank_transaction(
        self,
        user_id: str,
        trans_type: str,
        amount: int,
        balance_after: int,
        description: str,
        created_at: int,
    ):
        """新增银行流水。"""
        await self.conn.execute(
            """
            INSERT INTO bank_transactions (user_id, trans_type, amount, balance_after, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, trans_type, amount, balance_after, description, created_at),
        )
        await self.conn.commit()

    async def get_bank_transactions(self, user_id: str, limit: int = 20) -> List[dict]:
        """获取银行流水列表。"""
        transactions = []
        async with self.conn.execute(
            """
            SELECT id, trans_type, amount, balance_after, description, created_at
            FROM bank_transactions WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            async for row in cursor:
                transactions.append(
                    {
                        "id": row[0],
                        "trans_type": row[1],
                        "amount": row[2],
                        "balance_after": row[3],
                        "description": row[4],
                        "created_at": row[5],
                    }
                )
        return transactions

    async def get_deposit_ranking(self, limit: int = 10) -> List[dict]:
        """获取存款排行榜。"""
        rankings = []
        async with self.conn.execute(
            """
            SELECT user_id, balance FROM bank_accounts
            WHERE balance > 0
            ORDER BY balance DESC LIMIT ?
            """,
            (limit,),
        ) as cursor:
            async for row in cursor:
                rankings.append({"user_id": row[0], "balance": row[1]})
        return rankings
