"""Boss daily challenge usage service."""

import time

from ..data import DataBase

__all__ = ["BossChallengeService"]


class BossChallengeService:
    """Provide one shared daily Boss challenge counter workflow."""

    BOSS_DAILY_CHALLENGE_COUNT_KEY = "boss_daily_challenge_count"
    BOSS_DAILY_CHALLENGE_DATE_KEY = "boss_daily_challenge_date"
    BOSS_DAILY_CHALLENGE_LIMIT = 3

    def __init__(self, db: DataBase):
        self.db = db

    async def get_or_create_user_cd(self, user_id: str):
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)
        return user_cd

    def _today_str(self) -> str:
        return time.strftime("%Y-%m-%d", time.localtime())

    async def get_daily_status(self, user_id: str) -> tuple[int, int]:
        user_cd = await self.get_or_create_user_cd(user_id)
        return await self.get_daily_status_from_user_cd(user_cd)

    async def get_daily_status_from_user_cd(self, user_cd) -> tuple[int, int]:
        extra_data = user_cd.get_extra_data()
        today = self._today_str()
        saved_date = str(extra_data.get(self.BOSS_DAILY_CHALLENGE_DATE_KEY, "") or "")
        used_count = int(extra_data.get(self.BOSS_DAILY_CHALLENGE_COUNT_KEY, 0) or 0)

        if saved_date != today:
            extra_data[self.BOSS_DAILY_CHALLENGE_DATE_KEY] = today
            extra_data[self.BOSS_DAILY_CHALLENGE_COUNT_KEY] = 0
            user_cd.set_extra_data(extra_data)
            await self.db.ext.update_user_cd(user_cd)
            used_count = 0

        remaining = max(0, self.BOSS_DAILY_CHALLENGE_LIMIT - used_count)
        return used_count, remaining

    async def consume_daily_challenge(self, user_id: str) -> tuple[int, int]:
        user_cd = await self.get_or_create_user_cd(user_id)
        return await self.consume_daily_challenge_from_user_cd(user_cd)

    async def consume_daily_challenge_from_user_cd(self, user_cd) -> tuple[int, int]:
        extra_data = user_cd.get_extra_data()
        today = self._today_str()
        saved_date = str(extra_data.get(self.BOSS_DAILY_CHALLENGE_DATE_KEY, "") or "")
        used_count = int(extra_data.get(self.BOSS_DAILY_CHALLENGE_COUNT_KEY, 0) or 0)

        if saved_date != today:
            used_count = 0

        used_count += 1
        extra_data[self.BOSS_DAILY_CHALLENGE_DATE_KEY] = today
        extra_data[self.BOSS_DAILY_CHALLENGE_COUNT_KEY] = used_count
        user_cd.set_extra_data(extra_data)
        await self.db.ext.update_user_cd(user_cd)

        remaining = max(0, self.BOSS_DAILY_CHALLENGE_LIMIT - used_count)
        return used_count, remaining
