"""灵宠系统管理器。"""

import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..data import DataBase
from ..models import Player

__all__ = ["PetManager"]


class PetManager:
    PET_SLOTS = 3
    EGG_PRICE = 10000
    WEEKLY_LIMIT = 1
    HATCH_DURATION = 24 * 3600

    RANK_RATES = {
        "normal": 50,
        "rare": 30,
        "epic": 15,
        "legendary": 5,
    }

    RANK_LABELS = {
        "normal": "普通",
        "rare": "稀有",
        "epic": "罕见",
        "legendary": "传说",
    }

    PET_NAMES = {
        "normal": ["云尾狐", "青羽雀", "岩甲龟", "霜耳兔", "赤鬃犬", "月纹猫", "金铃貂", "竹影鹿", "灰羽鸦", "小角灵羊"],
        "rare": ["炎翎隼", "玄甲猞猁", "寒晶鹿", "雷纹豹", "灵雾鸢", "碧瞳狼", "赤炎麟犬", "星尾狐"],
        "epic": ["紫电狻猊", "玄冥灵鹤", "炽羽凰鸟", "苍岳龙龟", "幻月白泽"],
        "legendary": ["太虚天狐", "九霄凰灵", "镇狱麒麟"],
    }

    SKILL_LABELS = {
        "heal": "回春",
        "guard": "坚毅",
        "inspire": "鼓舞",
        "gaze": "凝视",
        "rebirth": "涅槃",
        "illusion": "幻象",
    }

    SKILL_WEIGHTS = {
        "heal": 20,
        "guard": 20,
        "inspire": 20,
        "gaze": 20,
        "illusion": 15,
        "rebirth": 5,
    }

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _week_token() -> str:
        now = datetime.now()
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    @staticmethod
    def _purchase_key(user_id: str) -> str:
        return f"pet_weekly_purchase:{user_id}"

    async def get_weekly_purchase_status(self, user_id: str) -> Tuple[int, int]:
        token = self._week_token()
        stored = await self.db.ext.get_system_config(self._purchase_key(user_id))
        used = self.WEEKLY_LIMIT if stored == token else 0
        return used, max(0, self.WEEKLY_LIMIT - used)

    async def _mark_weekly_purchase(self, user_id: str):
        await self.db.ext.set_system_config(self._purchase_key(user_id), self._week_token())

    async def _sync_pet_states(self, pets: List[Dict]):
        for pet in pets:
            await self.db.conn.execute(
                "UPDATE pets SET state = ? WHERE id = ?",
                (pet["state"], pet["id"]),
            )
        await self.db.conn.commit()

    async def get_user_pets(self, user_id: str) -> List[Dict]:
        async with self.db.conn.execute(
            """
            SELECT * FROM pets
            WHERE user_id = ? AND state != 'released'
            ORDER BY slot_index ASC
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        pets = [dict(row) for row in rows]
        changed = False
        now = int(time.time())
        for pet in pets:
            if pet["state"] == "hatching" and int(pet.get("hatch_finish_at", 0) or 0) <= now:
                pet["state"] = "awaiting_identify"
                changed = True

        if changed:
            await self._sync_pet_states(pets)

        return pets

    async def get_pet_by_slot(self, user_id: str, slot_index: int) -> Optional[Dict]:
        pets = await self.get_user_pets(user_id)
        for pet in pets:
            if int(pet["slot_index"]) == slot_index:
                return pet
        return None

    async def get_equipped_pet(self, user_id: str) -> Optional[Dict]:
        pets = await self.get_user_pets(user_id)
        for pet in pets:
            if int(pet.get("is_equipped", 0) or 0) == 1 and pet["state"] == "active":
                return pet
        return None

    async def _get_empty_slot(self, user_id: str) -> Optional[int]:
        occupied = {int(p["slot_index"]) for p in await self.get_user_pets(user_id)}
        for slot in range(1, self.PET_SLOTS + 1):
            if slot not in occupied:
                return slot
        return None

    def _roll_rank(self) -> str:
        roll = random.randint(1, 100)
        total = 0
        for rank, rate in self.RANK_RATES.items():
            total += rate
            if roll <= total:
                return rank
        return "normal"

    def _roll_skills(self) -> Tuple[str, str]:
        weighted_skills = list(self.SKILL_WEIGHTS.items())
        first = random.choices(
            [skill for skill, _weight in weighted_skills],
            weights=[weight for _skill, weight in weighted_skills],
            k=1,
        )[0]
        remaining = [(skill, weight) for skill, weight in weighted_skills if skill != first]
        second = random.choices(
            [skill for skill, _weight in remaining],
            weights=[weight for _skill, weight in remaining],
            k=1,
        )[0]
        return first, second

    async def purchase_egg(self, player: Player) -> Tuple[bool, str]:
        _used, remaining = await self.get_weekly_purchase_status(player.user_id)
        if remaining <= 0:
            return False, "你本周已经购买过兽蛋了，请下周再来。"

        slot = await self._get_empty_slot(player.user_id)
        if slot is None:
            return False, "兽栏已满，请先释放灵宠后再购买。"

        if player.gold < self.EGG_PRICE:
            return False, f"购买兽蛋需要 {self.EGG_PRICE:,} 灵石。"

        player.gold -= self.EGG_PRICE
        await self.db.update_player(player)

        now = int(time.time())
        await self.db.conn.execute(
            """
            INSERT INTO pets (
                user_id, slot_index, name, rank, state,
                skill_1, skill_2, is_equipped,
                created_at, hatch_start_at, hatch_finish_at, identified_at
            ) VALUES (?, ?, ?, ?, ?, '', '', 0, ?, 0, 0, 0)
            """,
            (player.user_id, slot, "灵宠（未孵化）", "unknown", "egg", now),
        )
        await self.db.conn.commit()
        await self._mark_weekly_purchase(player.user_id)
        return True, f"成功购买兽蛋，已放入兽栏 {slot} 号位。请使用 /孵化灵宠 {slot} 开始孵化。"

    async def start_hatching(self, user_id: str, slot_index: int) -> Tuple[bool, str]:
        pet = await self.get_pet_by_slot(user_id, slot_index)
        if not pet:
            return False, "该栏位没有灵宠。"
        if pet["state"] == "hatching":
            return False, "这枚兽蛋正在孵化中。"
        if pet["state"] == "awaiting_identify":
            return False, "该灵宠已经孵化完成，请直接鉴定。"
        if pet["state"] != "egg":
            return False, "只有未孵化的兽蛋才能开始孵化。"

        now = int(time.time())
        finish_at = now + self.HATCH_DURATION
        await self.db.conn.execute(
            "UPDATE pets SET state = 'hatching', hatch_start_at = ?, hatch_finish_at = ? WHERE id = ?",
            (now, finish_at, pet["id"]),
        )
        await self.db.conn.commit()
        return True, "孵化已开始，24 小时后可进行鉴定。"

    async def identify_pet(self, user_id: str, slot_index: int) -> Tuple[bool, str]:
        pet = await self.get_pet_by_slot(user_id, slot_index)
        if not pet:
            return False, "该栏位没有灵宠。"
        if pet["state"] == "egg":
            return False, "这还是一枚未孵化的兽蛋，请先开始孵化。"
        if pet["state"] == "active":
            return False, "该灵宠已经完成鉴定。"
        if pet["state"] == "hatching":
            now = int(time.time())
            finish_at = int(pet.get("hatch_finish_at", 0) or 0)
            if now < finish_at:
                remaining = finish_at - now
                return False, f"孵化尚未完成，还需 {remaining // 3600} 小时 {(remaining % 3600) // 60} 分钟。"

        rank = self._roll_rank()
        name = random.choice(self.PET_NAMES[rank])
        skill_1, skill_2 = self._roll_skills()
        identified_at = int(time.time())
        await self.db.conn.execute(
            """
            UPDATE pets
            SET name = ?, rank = ?, state = 'active', skill_1 = ?, skill_2 = ?, identified_at = ?
            WHERE id = ?
            """,
            (name, rank, skill_1, skill_2, identified_at, pet["id"]),
        )
        await self.db.conn.commit()
        return True, (
            "鉴定成功！\n"
            f"名称：{name}\n"
            f"品阶：{self.RANK_LABELS.get(rank, rank)}\n"
            f"技能：{self.SKILL_LABELS[skill_1]}、{self.SKILL_LABELS[skill_2]}"
        )

    async def equip_pet(self, user_id: str, slot_index: int) -> Tuple[bool, str]:
        pet = await self.get_pet_by_slot(user_id, slot_index)
        if not pet:
            return False, "该栏位没有灵宠。"
        if pet["state"] != "active":
            return False, "只有完成鉴定的灵宠才能携带。"

        await self.db.conn.execute("UPDATE pets SET is_equipped = 0 WHERE user_id = ?", (user_id,))
        await self.db.conn.execute("UPDATE pets SET is_equipped = 1 WHERE id = ?", (pet["id"],))
        await self.db.conn.commit()
        return True, f"已携带灵宠【{pet['name']}】出战。"

    async def release_pet(self, user_id: str, slot_index: int) -> Tuple[bool, str]:
        pet = await self.get_pet_by_slot(user_id, slot_index)
        if not pet:
            return False, "该栏位没有灵宠。"

        await self.db.conn.execute("DELETE FROM pets WHERE id = ?", (pet["id"],))
        await self.db.conn.commit()
        return True, f"已释放灵宠【{pet['name']}】，栏位已腾出。"

    async def get_market_info(self, player: Player) -> str:
        _used, remaining = await self.get_weekly_purchase_status(player.user_id)
        occupied = len(await self.get_user_pets(player.user_id))
        return (
            "灵兽阁\n"
            "━━━━━━━━━━━━━━\n"
            f"兽蛋价格：{self.EGG_PRICE:,} 灵石\n"
            f"本周剩余购买次数：{remaining}/{self.WEEKLY_LIMIT}\n"
            f"当前兽栏占用：{occupied}/{self.PET_SLOTS}\n"
            "说明：\n"
            "  1. 每位玩家每周限购 1 枚兽蛋\n"
            "  2. 兽蛋需手动孵化，孵化时长 24 小时\n"
            "  3. 孵化完成后需手动鉴定，随机获得 2 个技能\n"
            "  4. 每次只能携带 1 只灵宠出战\n"
            "请输入 /购买兽蛋 进行购买。"
        )

    async def get_pet_barn_info(self, user_id: str) -> str:
        pets = await self.get_user_pets(user_id)
        pet_map = {int(p["slot_index"]): p for p in pets}
        now = int(time.time())

        lines = ["我的灵宠", "━━━━━━━━━━━━━━"]
        for slot in range(1, self.PET_SLOTS + 1):
            pet = pet_map.get(slot)
            if not pet:
                lines.append(f"{slot} 号位：空")
                continue

            state = pet["state"]
            if state == "egg":
                state_text = "兽蛋（未孵化）"
            elif state == "hatching":
                finish_at = int(pet.get("hatch_finish_at", 0) or 0)
                remaining = max(0, finish_at - now)
                state_text = f"孵化中（剩余 {remaining // 3600} 小时 {(remaining % 3600) // 60} 分钟）"
            elif state == "awaiting_identify":
                state_text = "已孵化，待鉴定"
            else:
                equipped = "【已携带】" if int(pet.get("is_equipped", 0) or 0) == 1 else ""
                skill_1 = self.SKILL_LABELS.get(pet.get("skill_1", ""), pet.get("skill_1", ""))
                skill_2 = self.SKILL_LABELS.get(pet.get("skill_2", ""), pet.get("skill_2", ""))
                state_text = (
                    f"{pet['name']} {equipped}\n"
                    f"  品阶：{self.RANK_LABELS.get(pet.get('rank', ''), pet.get('rank', '未知'))}\n"
                    f"  技能：{skill_1}、{skill_2}"
                )

            lines.append(f"{slot} 号位：{state_text}")

        lines.append("")
        lines.append("命令：/孵化灵宠 <栏位>  /鉴定灵宠 <栏位>  /携带灵宠 <栏位>  /释放灵宠 <栏位>")
        return "\n".join(lines)
