import datetime as dt
from typing import Optional, Union
import unittest

import discord
import discord.ext.commands as commands
import pytest
import pytz

from ._helpers import *
from sandpiper.common.time import utc_now
from sandpiper.conversion.cog import Conversion, conversion_pattern
from sandpiper.conversion.unit_conversion import imperial_shorthand_pattern
from sandpiper.user_data import UserData
from sandpiper.user_data.enums import PrivacyType


@pytest.fixture()
def bot(bot) -> commands.Bot:
    bot.add_cog(Conversion(bot))
    bot.add_cog(UserData(bot))
    return bot


class TestImperialShorthandRegex:

    @staticmethod
    def _assert(
            test_str: str, foot: Optional[Union[int, float]],
            inch: Optional[Union[int, float]]
    ):
        __tracebackhide__ = True
        match = imperial_shorthand_pattern.match(test_str)

        if foot is None and inch is None:
            assert match is None
        else:
            match_foot = match['foot']
            match_inch = match['inch']
            # Coerce the matched strings into their expected types
            if foot is not None and match_foot is not None:
                match_foot = type(foot)(match_foot)
            if inch is not None and match_inch is not None:
                match_inch = type(inch)(match_inch)

            assert match_foot == foot
            assert match_inch == inch

    def test_int_feet(self):
        self._assert("1'", 1, None)
        self._assert("23'", 23, None)
        self._assert("-4'", None, None)
        self._assert(" 5'", None, None)

    def test_int_inches(self):
        self._assert("1\"", None, 1)
        self._assert("23\"", None, 23)
        self._assert("-4\"", None, None)
        self._assert(" 5\"", None, None)

    def test_int_both(self):
        self._assert("1'2\"", 1, 2)
        self._assert("3' 4\"", 3, 4)
        self._assert("56' 78\"", 56, 78)
        self._assert("0' 1\"", 0, 1)
        self._assert("1' 0\"", 1, 0)

    def test_decimal_feet(self):
        # Decimal feet are not allowed (yet?)
        self._assert("1.2'", None, None)
        self._assert("0.3'", None, None)
        self._assert(".4'", None, None)

    def test_decimal_inches(self):
        self._assert("1.2\"", None, 1.2)
        self._assert("0.3\"", None, 0.3)
        self._assert(".4\"", None, 0.4)

    def test_decimal_both(self):
        self._assert("1' 2.3\"", 1, 2.3)
        self._assert(".4' 5.6\"", None, None)
        self._assert("1' 2.3.4\"", None, None)

    def test_other_garbage(self):
        self._assert("", None, None)
        self._assert("5", None, None)
        self._assert("30.00 °F", None, None)


class TestConversionStringRegex(unittest.TestCase):

    @staticmethod
    def _assert(
            in_: str, quantity: Optional[str], out_unit: Optional[str]
    ):
        __tracebackhide__ = True
        match = conversion_pattern.match(in_)

        if quantity is None:
            if out_unit is not None:
                raise ValueError("Cannot test for only out_unit")
            assert match is None, "Pattern matched when it shouldn't have"
            return

        assert match['quantity'] == quantity, (
            f"Matched quantity {match['quantity']} does not equal input "
            f"{quantity}"
        )
        assert match['out_unit'] == out_unit, (
            f"Matched out unit {match['out_unit']} does not equal input "
            f"{out_unit}"
        )

    def test_simple(self):
        self._assert('{5pm}', '5pm', None)
        self._assert('{ 5 ft }', '5 ft', None)

    def test_specifier_with_out_unit(self):
        self._assert('{5ft>m}', '5ft', 'm')
        self._assert('{5ft > m}', '5ft', 'm')
        self._assert('{5 ft > m}', '5 ft', 'm')
        self._assert('{5 km  >  mi}', '5 km', 'mi')
        self._assert('{ 5pm  > new york}', '5pm', 'new york')
        self._assert('{ 5pm  > new york   }', '5pm', 'new york')

    def test_specifier_no_out_unit(self):
        self._assert('{5pm>}', None, None)
        self._assert('{5pm >}', None, None)
        self._assert('{5pm> }', None, None)
        self._assert('{5pm > }', None, None)
        self._assert('{8:00 > }', None, None)


class TestUnitConversion:

    def add_cogs(self, bot: commands.Bot):
        bot.add_cog(Conversion(bot))

    async def assert_error(self, msg: str, *substrings: str):
        __tracebackhide__ = True
        embed = await self.dispatch_msg_get_embeds(msg, only_one=True)
        super().assert_error(embed, *substrings)

    async def test_two_way(self):
        await self.assert_in_reply(
            "guys it's {30f} outside today, I'm so cold...",
            '30.00 °F', '-1.11 °C'
        )
        await self.assert_in_reply(
            "guys it's {-1.11c} outside today, I'm so cold...",
            '30.00 °F', '-1.11 °C'
        )
        await self.assert_in_reply(
            "I've been working out a lot lately and I've already lost {2 kg}!!",
            '2.00 kg', '4.41 lb'
        )
        await self.assert_in_reply(
            "I've been working out a lot lately and I've already lost {4.41 lb}!!",
            '2.00 kg', '4.41 lb'
        )
        await self.assert_in_reply(
            "Is that a {33ft} boat, TJ?",
            '33.00 ft', '10.06 m'
        )
        await self.assert_in_reply(
            "Lou lives about {15km} from me and TJ's staying at a hotel "
            "{2.5km} away, so he and I are gonna meet up and drive over to "
            "Lou.",
            '9.32 mi', '15.00 km',
            '1.55 mi', '2.50 km'
        )

    async def test_one_way(self):
        await self.assert_in_reply(
            "I was only {4 yards} away in geoguessr!!",
            '4.00 yd', '3.66 m'
        )
        await self.assert_in_reply(
            "I weigh around {9.3 stone}. whatever that means...",
            '9.30 stone', '59.06 kg'
        )
        await self.assert_in_reply(
            "any scientists in the chat?? {0 K}",
            '0.00 K', '-273.15 °C'
        )

    async def test_imperial_shorthand(self):
        await self.assert_in_reply(
            "I think Jason is like {6' 2\"} tall",
            '6.17 ft', '1.88 m'
        )
        await self.assert_in_reply(
            "I'm only {5'11\"} though!",
            '5.92 ft', '1.80 m'
        )

    async def test_explicit(self):
        await self.assert_in_reply(
            "{-5 f > kelvin} it's too late for apologies, imperial system",
            '-5.00 °F', '252.59 K'
        )
        await self.assert_in_reply(
            "how much is {9.3 stone > lbs}",
            '9.30 stone', '130.20 lb'
        )
        await self.assert_in_reply(
            "bc this is totally useful.. {5 mi > ft}"
            '5 mi', '26400.00 ft'
        )
        await self.assert_in_reply(
            "can't believe {3.000 hogshead > gallon} is even real"
            '3 hogshead', '189.00 gal'
        )
        await self.assert_in_reply(
            "ma'am you forgot your spaces {5ft>yd}",
            '5.00 ft', '1.67 yd'
        )

    async def test_unit_math(self):
        await self.assert_in_reply(
            "I'm measuring wood planks, I need {2.3 ft + 5 in}",
            '2.72 ft', '0.83 m'
        )
        await self.assert_in_reply(
            "oops, I need that in inches {2.3 ft + 5 in > in}",
            '2.72 ft', '32.60 in'
        )
        await self.assert_in_reply(
            "my two favorite songs are a total of {5min+27s + 4min+34s > s}",
            '10.02 min', '601.00 s'
        )

    async def test_dimensionless_math(self):
        await self.assert_in_reply(
            "what's {2 + 7}?",
            '2 + 7', '9'
        )
        await self.assert_in_reply(
            "how about {2.5 + 7.8}?",
            '2.5 + 7.8', '10.3'
        )
        await self.assert_in_reply(
            "and {2 * 7}?",
            '2 * 7', '14'
        )

    async def test_unknown_unit(self):
        await self.assert_error(
            "that's like {12.5 donuts} wide!",
            'Unknown unit "donuts"'
        )
        await self.assert_error(
            "how far away is that in blehs? {6 km > bleh}",
            'Unknown unit "bleh"'
        )

    async def test_unmapped_unit(self):
        await self.assert_error(
            "{5 hogshead} is a real unit, but not really useful enough to be "
            "mapped. fun name though",
            '{5 hogshead > otherunit}'
        )

    async def test_bad_conversion_string(self):
        await self.assert_no_reply("oops I dropped my unit {5 ft >}",)
        await self.assert_no_reply("oh crap not again {5 ft > }",)
        await self.assert_no_reply("okay this is just disgusting {5 >}",)
        await self.assert_no_reply("dude! {5 > }",)


class TestTimeConversion:

    T_TimezoneUser = tuple[discord.User, dt.datetime]

    @pytest.fixture(autouse=True)
    def june_1st_2020_932_am(
            self, patch_localzone_utc, patch_datetime_now
    ) -> dt.datetime:
        yield patch_datetime_now(dt.datetime(2020, 6, 1, 9, 32))

    @pytest.fixture()
    def make_user_with_timezone(self, make_user, database):
        async def f(timezone: str) -> tuple[discord.User, dt.datetime]:
            user = make_user()
            tz = pytz.timezone(timezone)
            now = utc_now().astimezone(tz)
            await database.set_timezone(user.id, tz)
            await database.set_privacy_timezone(user.id, PrivacyType.PUBLIC)
            return user, now
        yield f

    @pytest.fixture()
    async def american_user(self, make_user_with_timezone) -> T_TimezoneUser:
        yield await make_user_with_timezone('America/New_York')

    @pytest.fixture()
    async def british_user(self, make_user_with_timezone) -> T_TimezoneUser:
        yield await make_user_with_timezone('Europe/London')

    @pytest.fixture()
    async def dutch_user(self, make_user_with_timezone) -> T_TimezoneUser:
        yield await make_user_with_timezone('Europe/Amsterdam')

    @staticmethod
    def _assert(contents: list[str], *patterns: str):
        assert len(contents) == 1
        assert_regex(contents[0], *patterns)

    # region Get user's timezone

    async def test_basic_hour_period(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = dutch_user[0]
        contents = await dispatch_msg_get_contents(
            "do you guys wanna play at {9pm}?"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+9:00 PM',
            r'Europe/London.+8:00 PM',
            r'America/New_York.+3:00 PM'
        )

    async def test_basic_no_colon_period(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = american_user[0]
        contents = await dispatch_msg_get_contents(
            "I get off work at {330pm}"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+9:30 PM',
            r'Europe/London.+8:30 PM',
            r'America/New_York.+3:30 PM'
        )

    async def test_basic_no_colon(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = american_user[0]
        contents = await dispatch_msg_get_contents(
            "In 24-hour time that's {1530}"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+9:30 PM',
            r'Europe/London.+8:30 PM',
            r'America/New_York.+3:30 PM'
        )

    async def test_basic_hour_only(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = british_user[0]
        contents = await dispatch_msg_get_contents(
            "yeah I've gotta wake up at {5} for work tomorrow, so it's an "
            "early bedtime for me"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+6:00 AM',
            r'Europe/London.+5:00 AM',
            r'America/New_York.+12:00 AM'
        )

    async def test_basic_multiple(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = american_user[0]
        contents = await dispatch_msg_get_contents(
            "I wish I could, but I'm busy from {14} to {17:45}"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+8:00 PM.+11:45 PM',
            r'Europe/London.+7:00 PM.+10:45 PM',
            r'America/New_York.+2:00 PM.+5:45 PM'
        )

    async def test_basic_noon(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = dutch_user[0]
        contents = await dispatch_msg_get_contents(
            "It's nearly {noon}. Time for lunch!"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+12:00 PM',
            r'Europe/London.+11:00 AM',
            r'America/New_York.+6:00 AM'
        )

    async def test_basic_midnight(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = american_user[0]
        contents = await dispatch_msg_get_contents(
            "Dude, it's {midnight} :gobed:!"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+6:00 AM',
            r'Europe/London.+5:00 AM',
            r'America/New_York.+12:00 AM'
        )

    async def test_basic_now_british(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = british_user[0]
        contents = await dispatch_msg_get_contents(
            "I'm free {now}, anyone want to do something?"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+' + dutch_user[1].strftime('%I:%M %p').lstrip('0'),
            r'Europe/London.+' + british_user[1].strftime('%I:%M %p').lstrip('0'),
            r'America/New_York.+' + american_user[1].strftime('%I:%M %p').lstrip('0')
        )

    async def test_basic_now_american(
            self, message, american_user, british_user, dutch_user,
            dispatch_msg_get_contents
    ):
        message.author = american_user[0]
        contents = await dispatch_msg_get_contents(
            "I'm free {now}, anyone want to do something?"
        )
        self._assert(
            contents,
            r'Europe/Amsterdam.+' + dutch_user[1].strftime('%I:%M %p').lstrip('0'),
            r'Europe/London.+' + british_user[1].strftime('%I:%M %p').lstrip('0'),
            r'America/New_York.+' + american_user[1].strftime('%I:%M %p').lstrip('0')
        )

    # endregion

    # region Specified input timezone

    async def test_in_basic(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "Jaakko's getting on at {8 pm helsinki}",
            r'Europe/Amsterdam.+7:00 PM',
            r'Europe/London.+6:00 PM',
            r'America/New_York.+1:00 PM'
        )

        self.msg.author.id = self.british_user
        await self.assert_regex_reply(
            "aka {8pm helsinki}",
            r'Europe/Amsterdam.+7:00 PM',
            r'Europe/London.+6:00 PM',
            r'America/New_York.+1:00 PM'
        )

        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            "aka {20:00 helsinki}",
            r'Europe/Amsterdam.+7:00 PM',
            r'Europe/London.+6:00 PM',
            r'America/New_York.+1:00 PM'
        )

    async def test_in_multiple(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "my flight took off at {7pm new york} and landed at {8 AM london}",
            r'Europe/Amsterdam.+1:00 AM.+9:00 AM',
            r'Europe/London.+12:00 AM.+8:00 AM',
            r'America/New_York.+7:00 PM.+3:00 AM'
        )

    async def test_in_keyword(self):
        self.msg.author.id = self.british_user
        await self.assert_regex_reply(
            "he's getting lunch around {noon los angeles}",
            r'Europe/Amsterdam.+9:00 PM',
            r'Europe/London.+8:00 PM',
            r'America/New_York.+3:00 PM'
        )

        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "My flight's landing at {midnight brussels}",
            r'Europe/Amsterdam.+12:00 AM',
            r'Europe/London.+11:00 PM',
            r'America/New_York.+6:00 PM'
        )

    async def test_in_now(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "{now amsterdam} is redundant but it shouldn't fail",
            r'Europe/Amsterdam.+11:32 AM',
            r'Europe/London.+10:32 AM',
            r'America/New_York.+5:32 AM'
        )

    async def test_in_ambiguous_with_unit(self):
        self.msg.author.id = self.american_user
        await self.assert_error(
            "{20 helsinki} (8:00 pm Helsinki time) isn't allowed because it's "
            "ambiguous with a unit 'helsinki' with magnitude 20. You must add "
            "AM/PM or use a colon.",

            'Unknown unit "helsinki"',
        )

    async def test_in_unknown_timezone(self):
        self.msg.author.id = self.american_user
        await self.assert_error(
            "this don't exist {8:00 ZBNMBSAEFHJBGEWB}",
            'Timezone "ZBNMBSAEFHJBGEWB" not found'
        )

    # endregion

    # region Specified output timezone

    async def test_out_basic(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "alex, I'm gonna restart the server at {11 > amsterdam}",
            r'Europe/Amsterdam.+5:00 PM',
        )

        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "or I can wait until {8pm > amsterdam}",
            r'Europe/Amsterdam.+2:00 AM',
        )

    async def test_out_multiple(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "hey bruce I wanna show you something, I'm free between "
            "{11am > london} and {3 PM > Europe/London}",
            r'Europe/London.+4:00 PM.+8:00 PM',
        )

        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            "the game's releasing for americans at {1 PM > new york} and "
            "{1500 > london} for europeans"
            r'America/New_York.+7:00 AM',
            r'Europe/London.+2:00 PM',
        )

    async def test_out_keyword(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "the solar eclipse will be happening here while the hawaiians "
            "are sleeping! {noon > honolulu}",
            r'Pacific/Honolulu.+6:00 AM'
        )

        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "and while I'm sleeping, they'll be eating dinner "
            "{midnight > honolulu}",
            r'Pacific/Honolulu.+6:00 PM'
        )

    async def test_out_now(self):
        self.msg.author.id = self.american_user
        await self.assert_regex_reply(
            "what time is it in dubai? {now > dubai}",
            r'Asia/Dubai.+1:32 PM',
        )

    async def test_out_unknown_timezone(self):
        self.msg.author.id = self.american_user
        await self.assert_error(
            "no timezone {8:00 > ZBNMBSAEFHJBGEWB}",
            'Timezone "ZBNMBSAEFHJBGEWB" not found',
        )

    async def test_out_empty(self):
        self.msg.author.id = self.american_user
        await self.assert_no_reply("no timezone {8:00 > }")

    # endregion

    # region Specified input and output timezone

    async def test_in_out_basic(self):
        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            "I've run out of interesting message ideas "
            "{5:00 pm honolulu > los angeles}",

            r'America/Los_Angeles.+8:00 PM',
        )

    async def test_in_out_multiple(self):
        self.msg.author.id = self.british_user
        await self.assert_regex_reply(
            "you probably get the idea by now "
            "{5:00 pm honolulu > los angeles} and also "
            "{10:00 amsterdam > london} annnd back to "
            "{1am new york > los angeles}",

            r'America/Los_Angeles.+8:00 PM.+10:00 PM',
            r'Europe/London.+9:00 AM',
        )

    async def test_in_out_keyword(self):
        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            ":) {midnight los angeles > honolulu}",
            r'Pacific/Honolulu.+9:00 PM',
        )

        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            ":D {noon london > new york}",
            r'America/New_York.+7:00 AM',
        )

    async def test_in_out_now(self):
        self.msg.author.id = self.dutch_user
        await self.assert_regex_reply(
            ":O {now new york > amsterdam}",
            r'Europe/Amsterdam.+11:32 AM',
        )

    async def test_in_out_unknown_timezone(self):
        self.msg.author.id = self.dutch_user
        await self.assert_error(
            ":( {10 amsterdam > london}",
            'Unknown unit "amsterdam"',
        )

    # endregion

    # region Other

    async def test_flags(self):
        self.msg.author.id = self.american_user
        await self.assert_in_reply(
            "you can see the country flags too! {12am}",
            '🇺🇸', '🇬🇧', '🇳🇱'
        )

    # endregion
