import asyncio
import datetime as dt
import logging
from typing import Optional

import discord.ext.commands as commands
import discord.ext.tasks as tasks
import pytz

from sandpiper.common.time import utc_now
from sandpiper.user_data import UserData
from sandpiper.user_data.database import Database

__all__ = ['Birthdays']

logger = logging.getLogger('sandpiper.birthdays')


class Birthdays(commands.Cog):

    def __init__(
            self, bot: commands.Bot, *, past_birthdays_day_range: int = 7,
            upcoming_birthdays_day_range: int = 14
    ):
        self.bot = bot
        self.past_birthdays_day_range = past_birthdays_day_range
        self.upcoming_birthdays_day_range = upcoming_birthdays_day_range
        self.daily_loop.start()

    async def _get_database(self) -> Database:
        user_data: Optional[UserData] = self.bot.get_cog('UserData')
        if user_data is None:
            raise RuntimeError('UserData cog is not loaded.')
        return await user_data.get_database()

    @tasks.loop(hours=24)
    async def daily_loop(self):
        await self.schedule_todays_birthdays()

    async def schedule_todays_birthdays(self):
        db = await self._get_database()
        now = utc_now()
        today = now.date()
        for user_id, birthday, timezone in await db.get_birthdays_range(
                today, today + dt.timedelta(days=1)
        ):
            midnight_local: dt.datetime = timezone.localize(
                dt.datetime(today.year, birthday.month, birthday.day)
            )
            midnight_utc = midnight_local.astimezone(pytz.UTC)
            midnight_delta = midnight_utc - now
            # TODO I'm worried that it could be possible we lose a birthday
            #   in a race condition here...
            if (midnight_delta > dt.timedelta(0)
                    and midnight_delta <= dt.timedelta(hours=24)):
                await self.bot.loop.create_task(
                    self.send_birthday_message(user_id, midnight_delta)
                )

    async def send_birthday_message(self, user_id: int, delta: dt.timedelta):
        await asyncio.sleep(delta.total_seconds())
        # send message here

    async def get_past_upcoming_birthdays(self) -> tuple[list, list]:
        db = await self._get_database()
        now = utc_now()
        today = now.date()
        past_delta = dt.timedelta(days=self.past_birthdays_day_range)
        upcoming_delta = dt.timedelta(days=self.upcoming_birthdays_day_range)
        past_birthdays = await db.get_birthdays_range(
            today - past_delta, today
        )
        upcoming_birthdays = await db.get_birthdays_range(
            today + dt.timedelta(days=1), today + upcoming_delta
        )
        return past_birthdays, upcoming_birthdays
