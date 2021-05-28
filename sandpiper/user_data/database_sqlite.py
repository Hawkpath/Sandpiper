import datetime as dt
import logging
from pathlib import Path
from sqlite3 import PARSE_DECLTYPES
from typing import Any, NoReturn, Optional, Union, cast

import aiosqlite
import pytz

from .database import *
from .enums import PrivacyType
from sandpiper.common.time import TimezoneType

__all__ = ['DatabaseSQLite']

logger = logging.getLogger('sandpiper.user_data.database_sqlite')


class DatabaseSQLite(Database):

    _con: Optional[aiosqlite.Connection] = None
    db_path: Union[str, Path]

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = db_path

    async def connect(self):
        logger.info(f'Connecting to database (path={self.db_path})')
        self._con = await aiosqlite.connect(
            self.db_path, detect_types=PARSE_DECLTYPES
        )
        await self.create_table()

    async def disconnect(self):
        logger.info(f'Disconnecting from database (path={self.db_path})')
        await self._con.close()
        self._con = None

    async def connected(self):
        return self._con is not None

    async def create_table(self):
        logger.info('Creating user_data table if not exists')
        stmt = '''
            CREATE TABLE IF NOT EXISTS user_data (
                user_id INTEGER PRIMARY KEY UNIQUE, 
                preferred_name TEXT, 
                pronouns TEXT, 
                birthday DATE, 
                timezone TEXT, 
                privacy_preferred_name TINYINT, 
                privacy_pronouns TINYINT, 
                privacy_birthday TINYINT, 
                privacy_age TINYINT, 
                privacy_timezone TINYINT
            )
        '''
        try:
            await self._con.execute(stmt)
            await self._con.commit()
        except aiosqlite.Error:
            logger.error('Failed to create table', exc_info=True)
        await self.create_indices()

    async def create_indices(self):
        logger.info('Creating indices for user_data table if not exist')
        stmt = '''
            CREATE INDEX IF NOT EXISTS index_users_preferred_name
            ON user_data(preferred_name)
        '''
        try:
            await self._con.execute(stmt)
            await self._con.commit()
        except aiosqlite.Error:
            logger.error('Failed to create indices', exc_info=True)

    # region Getter/setter helpers

    async def _do_execute_get(
            self, col_name: str, user_id: int, default: Any = None
    ) -> Optional[Any]:
        logger.info(f'Getting data from column {col_name} (user_id={user_id})')
        stmt = f'SELECT {col_name} FROM user_data WHERE user_id = ?'
        try:
            cur = await self._con.execute(stmt, (user_id,))
            result = await cur.fetchone()
        except aiosqlite.Error:
            logger.error(
                f'Failed to get value (column={col_name!r} user_id={user_id})',
                exc_info=True
            )
            raise DatabaseError('Failed to get value')
        if result is None or result[0] is None:
            return default
        return result[0]

    async def _do_execute_set(
            self, col_name: str, user_id: int, new_value: Any
    ) -> NoReturn:
        logger.info(
            f'Setting data in column {col_name} (user_id={user_id} '
            f'new_value={new_value!r})'
        )
        stmt = f'''
            INSERT INTO user_data(user_id, {col_name})
            VALUES (:user_id, :new_value)
            ON CONFLICT (user_id) DO
            UPDATE SET {col_name} = :new_value
        '''
        args = {'user_id': user_id, 'new_value': new_value}
        try:
            await self._con.execute(stmt, args)
            await self._con.commit()
        except aiosqlite.Error:
            logger.error(
                f'Failed to set value (column={col_name!r} user_id={user_id} '
                f'new_value={new_value!r})',
                exc_info=True
            )
            raise DatabaseError('Failed to set value')

    # endregion
    # region Batch

    async def delete_user(self, user_id: int):
        logger.info(f'Deleting user (user_id={user_id})')
        stmt = 'DELETE FROM user_data WHERE user_id = ?'
        args = (user_id,)
        try:
            await self._con.execute(stmt, args)
            await self._con.commit()
        except aiosqlite.Error:
            logger.error(
                f'Failed to delete row (user_id={user_id})',
                exc_info=True
            )
            raise DatabaseError('Failed to delete user data')

    # endregion
    # region Name

    async def get_preferred_name(self, user_id: int) -> Optional[str]:
        return await self._do_execute_get('preferred_name', user_id)

    async def set_preferred_name(
            self, user_id: int, new_preferred_name: Optional[str]
    ):
        await self._do_execute_set(
            'preferred_name', user_id, new_preferred_name
        )

    async def get_privacy_preferred_name(self, user_id: int) -> PrivacyType:
        privacy = await self._do_execute_get(
            'privacy_preferred_name', user_id, DEFAULT_PRIVACY
        )
        return PrivacyType(privacy)

    async def set_privacy_preferred_name(
            self, user_id: int, new_privacy: PrivacyType
    ):
        await self._do_execute_set(
            'privacy_preferred_name', user_id, new_privacy
        )

    async def find_users_by_preferred_name(
            self, name: str
    ) -> list[tuple[int, str]]:
        logger.info(f'Finding users by preferred name (name={name!r})')
        if name == '':
            logger.info('Skipping empty string')
            return []

        stmt = '''
            SELECT user_id, preferred_name FROM user_data
            WHERE preferred_name like :name
                AND privacy_preferred_name = :privacy
        '''
        args = {'name': f'%{name}%', 'privacy': PrivacyType.PUBLIC}
        try:
            cur = await self._con.execute(stmt, args)
            return cast(list[tuple[int, str]], await cur.fetchall())
        except aiosqlite.Error:
            logger.error('Failed to find users by name', exc_info=True)

    # endregion
    # region Pronouns

    async def get_pronouns(self, user_id: int) -> Optional[str]:
        return await self._do_execute_get('pronouns', user_id)

    async def set_pronouns(self, user_id: int, new_pronouns: Optional[str]):
        await self._do_execute_set('pronouns', user_id, new_pronouns)

    async def get_privacy_pronouns(self, user_id: int) -> PrivacyType:
        privacy = await self._do_execute_get(
            'privacy_pronouns', user_id, DEFAULT_PRIVACY
        )
        return PrivacyType(privacy)

    async def set_privacy_pronouns(
            self, user_id: int, new_privacy: PrivacyType
    ):
        await self._do_execute_set('privacy_pronouns', user_id, new_privacy)

    # endregion
    # region Birthday

    async def get_birthday(self, user_id: int) -> Optional[dt.date]:
        return await self._do_execute_get('birthday', user_id)

    async def set_birthday(
            self, user_id: int, new_birthday: Optional[dt.date]
    ):
        await self._do_execute_set('birthday', user_id, new_birthday)

    async def get_privacy_birthday(self, user_id: int) -> PrivacyType:
        privacy = await self._do_execute_get(
            'privacy_birthday', user_id, DEFAULT_PRIVACY
        )
        return PrivacyType(privacy)

    async def set_privacy_birthday(
            self, user_id: int, new_privacy: PrivacyType
    ):
        await self._do_execute_set('privacy_birthday', user_id, new_privacy)

    async def get_birthdays_range(
            self, start: dt.date, end: dt.date
    ) -> list[tuple[int, dt.date, Optional[TimezoneType]]]:
        logger.info(f"Getting all birthdays between {start} and {end}")
        if not isinstance(start, dt.date) or not isinstance(end, dt.date):
            raise TypeError("start and end must be instances of datetime.date")
        if start > end:
            raise ValueError(
                f"Start date {start} is greater than end date {end}"
            )

        stmt = '''
WITH start_date (month, day) AS (
    VALUES (:start_month, :start_day)
),

end_date (month, day) AS (
    VALUES (:end_month, :end_day)
),

split_birthday (user_id, month, day) AS (
    SELECT
        user_id,
        CAST(strftime('%m', birthday) AS INT),
        CAST(strftime('%d', birthday) AS INT)
        FROM user_data
        WHERE birthday NOTNULL
)

SELECT user_data.user_id, birthday, timezone
    FROM user_data, start_date, end_date
    INNER JOIN split_birthday ON (
        user_data.user_id = split_birthday.user_id
    )
    WHERE
        CASE WHEN
            -- Ensure we're between the start and end month (inclusive)
            split_birthday.month >= start_date.month
            AND split_birthday.month <= end_date.month
        THEN
            CASE WHEN
                -- If we're between the start and end month (exclusive),
                -- we don't have to check the day
                split_birthday.month > start_date.month
                AND split_birthday.month < end_date.month
            THEN
                1
            ELSE
                CASE WHEN split_birthday.month = start_date.month THEN
                    -- We're in the start month, so check we're at least the earliest day
                    split_birthday.day >= start_date.day
                ELSE
                    1
                END AND CASE WHEN split_birthday.month = end_date.month THEN
                    -- We're in the end month, so check we're at most the latest day
                    split_birthday.day <= end_date.day
                ELSE
                    1
                END
            END
        ELSE
            0
        END
        '''
        args = {
            'start_month': start.month,
            'start_day': start.day,
            'end_month': end.month,
            'end_day': end.day,
        }
        try:
            cur = await self._con.execute(stmt, args)
            out = []
            async for user_id, birthday, timezone in cur:
                user_id: int
                birthday: dt.date
                if timezone is not None:
                    timezone: TimezoneType = pytz.timezone(timezone)
                out.append((user_id, birthday, timezone))
            return out
        except aiosqlite.Error:
            logger.error("Failed to get birthdays range", exc_info=True)

    # endregion
    # region Age

    async def get_privacy_age(self, user_id: int) -> PrivacyType:
        privacy = await self._do_execute_get(
            'privacy_age', user_id, DEFAULT_PRIVACY
        )
        return PrivacyType(privacy)

    async def set_privacy_age(self, user_id: int, new_privacy: PrivacyType):
        await self._do_execute_set('privacy_age', user_id, new_privacy)

    # endregion
    # region Timezone

    async def get_timezone(self, user_id: int) -> Optional[TimezoneType]:
        timezone_name = await self._do_execute_get('timezone', user_id)
        if timezone_name:
            return pytz.timezone(timezone_name)
        return None

    async def set_timezone(
            self, user_id: int, new_timezone: Optional[TimezoneType]
    ):
        if new_timezone:
            new_timezone = new_timezone.zone
        await self._do_execute_set('timezone', user_id, new_timezone)

    async def get_privacy_timezone(self, user_id: int) -> PrivacyType:
        privacy = await self._do_execute_get(
            'privacy_timezone', user_id, DEFAULT_PRIVACY
        )
        return PrivacyType(privacy)

    async def set_privacy_timezone(
            self, user_id: int, new_privacy: PrivacyType
    ):
        await self._do_execute_set('privacy_timezone', user_id, new_privacy)

    async def get_all_timezones(self) -> list[tuple[int, TimezoneType]]:
        logger.info(f'Getting all user timezones')
        stmt = '''
            SELECT user_id, timezone FROM user_data
            WHERE privacy_timezone = :privacy
        '''
        args = {'privacy': PrivacyType.PUBLIC}
        try:
            cur = await self._con.execute(stmt, args)
            result = await cur.fetchall()
            return [(user_id, pytz.timezone(tz_name))
                    for user_id, tz_name in result
                    if tz_name is not None]
        except aiosqlite.Error:
            logger.error('Failed to get all user timezones', exc_info=True)

    # endregion
