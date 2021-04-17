import datetime as dt
import logging
from typing import List, Set, Tuple

import discord

from sandpiper.common.time import *
from sandpiper.common.misc import RuntimeMessages
from sandpiper.user_data.database import Database

__all__ = ['UserTimezoneUnset', 'convert_time_to_user_timezones']

logger = logging.getLogger('sandpiper.conversion.time_conversion')


class UserTimezoneUnset(Exception):

    def __str__(self):
        return (
            "Your timezone is not set. Use the `help timezone set` command "
            "for more info."
        )


class TimezoneNotFound(Exception):

    def __init__(self, timezone: str):
        self.timezone = timezone

    def __str__(self):
        return f"Timezone \"{self.timezone}\" not found"


def _get_timezone(name: str, msgs: RuntimeMessages):
    matches = fuzzy_match_timezone(
        name, best_match_threshold=50, limit=1
    )
    if not matches.best_match:
        # We don't want this to pass on to unit conversion
        msgs += TimezoneNotFound(name)
        return None

    msgs += f"Using timezone **{matches.best_match}**"
    return matches.best_match


async def convert_time_to_user_timezones(
        db: Database, user_id: int, guild: discord.Guild,
        time_strs: List[Tuple[str, str]],
        *, runtime_msgs: RuntimeMessages
) -> Tuple[
    List[Tuple[str, List[dt.datetime]]],
    List[Tuple[str, str]]
]:
    """
    Convert times.

    :param db: the Database adapter for getting user timezones
    :param user_id: the id of the user asking for a time conversion
    :param guild: the guild the conversion is occurring in
    :param time_strs: a list of tuples of (time, timezone) where ``time`` is a
        string that may be a time and ``timezone`` is an optional timezone
        name
    :returns: A tuple of (conversions, failed, exceptions).
        ``failed`` is a list of tuples of (quantity, unit) that could not be converted.
        ``conversions`` is a list of tuples of (tz_name, converted_times).
        ``tz_name`` is the name of the timezone the following times are in.
        ``converted_times`` is a list of datetimes localized to every timezone
            occupied by users in the guild.
    """

    # Filter out repeat timezones and timezones of users outside this guild
    all_timezones = await db.get_all_timezones()
    logger.debug(f"All timezones: {all_timezones}")
    user_timezones: Set[TimezoneType] = (
        {tz for user_id, tz in all_timezones if guild.get_member(user_id)}
    )
    logger.debug(f"Filtered timezones: {user_timezones}")

    # Attempt to parse the strings as times and populate success and failure
    # lists accordingly
    parsed_times: List[dt.datetime] = []
    failed: List[Tuple[str, str]] = []  # Strings that should pass on to unit conversion
    user_tz = None
    for tstr, timezone_out_str in time_strs:
        # Keyword times
        if tstr.lower() == 'now':
            local_dt = utc_now()
            parsed_times.append(local_dt)
            continue

        if tstr.lower() == 'noon':
            tstr = "12:00"
        elif tstr.lower() == 'midnight':
            tstr = "00:00"

        try:
            parsed_time, timezone_in_str = parse_time(tstr)
        except ValueError as e:
            logger.info(
                f"Failed to parse time string (string={tstr!r}, reason={e})"
            )
            # Failed to parse as a time, so pass it on to unit conversion
            failed.append((tstr, timezone_out_str))
            continue
        except:
            logger.warning(
                f"Unhandled exception while parsing time string "
                f"(string={tstr!r})", exc_info=True
            )
            continue

        if timezone_in_str is not None:
            # User supplied a source timezone
            timezone_in = _get_timezone(timezone_in_str, runtime_msgs)
            if timezone_in is None:
                continue
        else:
            # Use the user's timezone
            if user_tz is None:
                # Only get this once
                user_tz = await db.get_timezone(user_id)
                if user_tz is None:
                    runtime_msgs.add_type_once(UserTimezoneUnset())
            timezone_in = user_tz

        local_dt = localize_time_to_datetime(parsed_time, timezone_in)
        parsed_times.append(local_dt)

    if not parsed_times:
        return [], failed

    # Iterate over each timezone and convert all times to that timezone
    conversions = []
    for tz in user_timezones:
        tz_name: str = tz.zone
        times = [time.astimezone(tz) for time in parsed_times]
        conversions.append((tz_name, times))
    conversions.sort(key=lambda conv: conv[1][0].utcoffset())

    return conversions, failed
