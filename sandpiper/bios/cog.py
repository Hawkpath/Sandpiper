import logging
from typing import Any, Optional

import discord
import discord.ext.commands as commands
from discord.ext.commands import BadArgument

from .misc import fuzzy_match_timezone
from ..common.discord import *
from ..common.embeds import Embeds
from ..common.misc import join
from ..user_info.cog import UserData, DatabaseUnavailable
from ..user_info.database import Database, DatabaseError
from ..user_info.enums import PrivacyType

__all__ = ['Bios']

logger = logging.getLogger('sandpiper.bios')

privacy_emojis = {
    PrivacyType.PRIVATE: '⛔',
    PrivacyType.PUBLIC: '✅'
}


def user_info_str(field_name: str, value: Any, privacy: PrivacyType):
    privacy_emoji = privacy_emojis[privacy]
    privacy = privacy.name.capitalize()
    return f'{privacy_emoji} `{privacy:7}` | **{field_name}** • {value}'


def user_names_str(ctx: commands.Context, db: Database, user_id: int,
                   preferred_name: str = None, username: str = None):
    """
    Create a string with a user's names (preferred name, Discord username,
    guild display names). You can supply ``preferred_name`` or ``username``
    to optimize the number of operations this function has to perform. There
    is no display_name parameter because this function still needs to find
    the user's display name in ALL guilds, so supplying just the one is useless.
    """

    # Get pronouns
    privacy_pronouns = db.get_privacy_pronouns(user_id)
    if privacy_pronouns == PrivacyType.PUBLIC:
        pronouns = db.get_pronouns(user_id)
    else:
        pronouns = None

    # Get preferred name
    if preferred_name is None:
        privacy_preferred_name = db.get_privacy_preferred_name(user_id)
        if privacy_preferred_name == PrivacyType.PUBLIC:
            preferred_name = db.get_preferred_name(user_id)
            if preferred_name is None:
                preferred_name = '`No preferred name`'
        else:
            preferred_name = '`No preferred name`'

    # Get discord username and discriminator
    if username is None:
        user: discord.User = ctx.bot.get_user(user_id)
        if user is not None:
            username = f'{user.name}#{user.discriminator}'
        else:
            username = '`User not found`'

    # Find the user's nicknames on servers they share with the executor
    # of the who is command
    members = find_user_in_mutual_guilds(ctx.bot, ctx.author.id, user_id)
    display_names = ', '.join(m.display_name for m in members)

    return join(
        join(preferred_name, pronouns and f'({pronouns})', sep=' '),
        username, display_names,
        sep=' • '
    )


class Bios(commands.Cog):

    _show_aliases = ('get',)
    _set_aliases = ()
    _delete_aliases = ('clear',)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_database(self) -> Database:
        user_data: Optional[UserData] = self.bot.get_cog('UserData')
        if user_data is None:
            raise RuntimeError('UserData cog is not loaded.')
        return user_data.get_database()

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context,
                               error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, DatabaseUnavailable):
                await Embeds.error(ctx, str(DatabaseUnavailable))
            elif isinstance(error.original, DatabaseError):
                await Embeds.error(ctx, 'Error during database operation.')
            else:
                logger.error(
                    f'Unexpected error (content={ctx.message.content!r} '
                    f'message={ctx.message})', exc_info=error.original)
                await Embeds.error(ctx, 'Unexpected error')
        else:
            await Embeds.error(ctx, str(error))

    @commands.group()
    async def bio(self, ctx: commands.Context):
        """Commands for managing all of your personal info."""
        pass

    @bio.command(name='delete', aliases=_delete_aliases)
    @commands.dm_only()
    async def bio_delete(self, ctx: commands.Context):
        """Delete all of your personal info."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.delete_user(user_id)
        await Embeds.success(ctx, 'Deleted all of your personal info!')

    @bio.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def bio_show(self, ctx: commands.Context):
        """Display your personal info."""

        user_id: int = ctx.author.id
        db = self._get_database()

        preferred_name = db.get_preferred_name(user_id)
        pronouns = db.get_pronouns(user_id)
        birthday = db.get_birthday(user_id)
        age = db.get_age(user_id)
        age = age if age is not None else 'N/A'
        timezone = db.get_timezone(user_id)

        p_preferred_name = db.get_privacy_preferred_name(user_id)
        p_pronouns = db.get_privacy_pronouns(user_id)
        p_birthday = db.get_privacy_birthday(user_id)
        p_age = db.get_privacy_age(user_id)
        p_timezone = db.get_privacy_timezone(user_id)

        await Embeds.info(ctx, message=(
            user_info_str('Name', preferred_name, p_preferred_name),
            user_info_str('Pronouns', pronouns, p_pronouns),
            user_info_str('Birthday', birthday, p_birthday),
            user_info_str('Age', age, p_age),
            user_info_str('Timezone', timezone, p_timezone)
        ))

    # Privacy setters

    @commands.group(name='privacy', invoke_without_command=False)
    async def privacy(self, ctx: commands.Context):
        """Commands for managing the privacy of your personal info."""
        pass

    @privacy.group(name='set', aliases=_set_aliases,
                   invoke_without_command=False)
    async def privacy_set(self, ctx: commands.Context):
        """Commands for setting the privacy of your personal info."""
        pass

    @privacy_set.command(name='all')
    async def privacy_set_all(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of all of your personal info at once."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_preferred_name(user_id, new_privacy)
        db.set_privacy_pronouns(user_id, new_privacy)
        db.set_privacy_birthday(user_id, new_privacy)
        db.set_privacy_age(user_id, new_privacy)
        db.set_privacy_timezone(user_id, new_privacy)
        await Embeds.success(ctx, 'All privacies set!')

    @privacy_set.command(name='name')
    async def privacy_set_name(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of your preferred name."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_preferred_name(user_id, new_privacy)
        await Embeds.success(ctx, 'Name privacy set!')

    @privacy_set.command(name='pronouns')
    async def privacy_set_pronouns(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of your pronouns."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_pronouns(user_id, new_privacy)
        await Embeds.success(ctx, 'Pronouns privacy set!')

    @privacy_set.command(name='birthday')
    async def privacy_set_birthday(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of your birthday."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_birthday(user_id, new_privacy)
        await Embeds.success(ctx, 'Birthday privacy set!')

    @privacy_set.command(name='age')
    async def privacy_set_age(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of your age."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_age(user_id, new_privacy)
        await Embeds.success(ctx, 'Age privacy set!')

    @privacy_set.command(name='timezone')
    async def privacy_set_timezone(
            self, ctx: commands.Context, new_privacy: privacy_handler):
        """Set the privacy of your timezone."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_privacy_timezone(user_id, new_privacy)
        await Embeds.success(ctx, 'Timezone privacy set!')

    # Name

    @commands.group(name='name', invoke_without_command=False)
    async def name(self, ctx: commands.Context):
        """Commands for managing your preferred name."""
        pass

    @name.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def name_show(self, ctx: commands.Context):
        """Display your preferred name."""
        user_id: int = ctx.author.id
        db = self._get_database()
        preferred_name = db.get_preferred_name(user_id)
        privacy = db.get_privacy_preferred_name(user_id)
        await Embeds.info(ctx, user_info_str('Name', preferred_name, privacy))

    @name.command(name='set', aliases=_set_aliases)
    @commands.dm_only()
    async def name_set(self, ctx: commands.Context, new_name: str):
        """Set your preferred name."""
        user_id: int = ctx.author.id
        db = self._get_database()
        if len(new_name) > 64:
            raise BadArgument(f'Name must be 64 characters or less '
                              f'(yours: {len(new_name)}).')
        db.set_preferred_name(user_id, new_name)
        await Embeds.success(ctx, 'Name set!')

    # Pronouns

    @commands.group(name='pronouns', invoke_without_command=False)
    async def pronouns(self, ctx: commands.Context):
        """Commands for managing your pronouns."""
        pass

    @pronouns.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def pronouns_show(self, ctx: commands.Context):
        """Display your pronouns."""
        user_id: int = ctx.author.id
        db = self._get_database()
        pronouns = db.get_pronouns(user_id)
        privacy = db.get_privacy_pronouns(user_id)
        await Embeds.info(ctx, user_info_str('Pronouns', pronouns, privacy))

    @pronouns.command(name='set', aliases=_set_aliases)
    @commands.dm_only()
    async def pronouns_set(self, ctx: commands.Context, new_pronouns: str):
        """Set your pronouns."""
        user_id: int = ctx.author.id
        db = self._get_database()
        if len(new_pronouns) > 64:
            raise BadArgument(f'Pronouns must be 64 characters or less '
                              f'(yours: {len(new_pronouns)}).')
        db.set_pronouns(user_id, new_pronouns)
        await Embeds.success(ctx, 'Pronouns set!')

    # Birthday

    @commands.group(name='birthday', invoke_without_command=False)
    async def birthday(self, ctx: commands.Context):
        """Commands for managing your birthday."""
        pass

    @birthday.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def birthday_show(self, ctx: commands.Context):
        """Display your birthday."""
        user_id: int = ctx.author.id
        db = self._get_database()
        birthday = db.get_birthday(user_id)
        privacy = db.get_privacy_birthday(user_id)
        await Embeds.info(ctx, user_info_str('Birthday', birthday, privacy))

    @birthday.command(name='set', aliases=_set_aliases)
    @commands.dm_only()
    async def birthday_set(self, ctx: commands.Context,
                           new_birthday: date_handler):
        """Set your birthday."""
        user_id: int = ctx.author.id
        db = self._get_database()
        db.set_birthday(user_id, new_birthday)
        await Embeds.success(ctx, 'Birthday set!')

    # Age

    @commands.group(name='age', invoke_without_command=False)
    async def age(self, ctx: commands.Context):
        """Commands for managing your age."""
        pass

    @age.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def age_show(self, ctx: commands.Context):
        """Display your age (calculated automatically using your birthday)."""
        user_id: int = ctx.author.id
        db = self._get_database()
        age = db.get_age(user_id)
        privacy = db.get_privacy_age(user_id)
        await Embeds.info(ctx, user_info_str('Age', age, privacy))

    # noinspection PyUnusedLocal
    @age.command(name='set', aliases=_set_aliases)
    @commands.dm_only()
    async def age_set(self, ctx: commands.Context):
        """
        Age is automatically calculated using your birthday. This command
        exists only to let you know that you don't have to set it.
        """
        await Embeds.error(ctx, 'Age is automatically calculated using your '
                                'birthday. You don\'t need to set it!')

    # Timezone

    @commands.group(name='timezone', invoke_without_command=False)
    async def timezone(self, ctx: commands.Context):
        """Commands for managing your timezone."""
        pass

    @timezone.command(name='show', aliases=_show_aliases)
    @commands.dm_only()
    async def timezone_show(self, ctx: commands.Context):
        """Display your timezone."""
        user_id: int = ctx.author.id
        db = self._get_database()
        timezone = db.get_timezone(user_id)
        privacy = db.get_privacy_timezone(user_id)
        await Embeds.info(ctx, user_info_str('Timezone', timezone, privacy))

    @timezone.command(name='set', aliases=_set_aliases)
    @commands.dm_only()
    async def timezone_set(self, ctx: commands.Context, *, new_timezone: str):
        """
        Set your timezone. Typing the name of the nearest major city should be
        good enough, but you can also try your state/country if that doesn't
        work.

        As a last resort, use this website to find your full timezone name:
        http://kevalbhatt.github.io/timezone-picker/
        """

        user_id: int = ctx.author.id
        db = self._get_database()

        tz_matches = fuzzy_match_timezone(
            new_timezone, best_match_threshold=50, lower_score_cutoff=50,
            limit=5
        )
        if not tz_matches.matches:
            # No matches
            raise BadArgument(
                'Timezone provided doesn\'t have any close matches. Try '
                'typing the name of a major city near you or your '
                'state/country name.\n\n'
                'If you\'re stuck, try using this '
                '[timezone picker](http://kevalbhatt.github.io/timezone-picker/).'
            )
        if tz_matches.best_match:
            # Display best match with other possible matches
            db.set_timezone(user_id, tz_matches.best_match)
            await Embeds.success(ctx, message=(
                f'Timezone set to **{tz_matches.best_match}**!',
                tz_matches.matches[1:] and '\nOther possible matches:',
                '\n'.join([f'- {name}' for name, _ in tz_matches.matches[1:]])
            ))
        else:
            # No best match; display other possible matches
            await Embeds.error(ctx, message=(
                'Couldn\'t find a good match for the timezone you entered.',
                '\nPossible matches:',
                '\n'.join([f'- {name}' for name, _ in tz_matches.matches])
            ))

    # Extra commands

    @commands.command(name='whois')
    async def whois(self, ctx: commands.Context, name: str):
        """
        Search for a user by one of their names. Outputs a list of matching
        users, showing their preferred name, Discord username, and nicknames
        in servers you share with them.
        """
        if len(name) < 2:
            raise BadArgument('Name must be at least 2 characters.')

        db = self._get_database()

        user_strs = []
        seen_users = set()

        for user_id, preferred_name in db.find_users_by_name(name):
            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            names = user_names_str(ctx, db, user_id,
                                   preferred_name=preferred_name)
            user_strs.append(names)

        for user_id, __ in find_users_by_display_name(
                ctx.bot, ctx.author.id, name):
            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            names = user_names_str(ctx, db, user_id)
            user_strs.append(names)

        for user_id, username in find_users_by_username(ctx.bot, name):
            if user_id in seen_users:
                continue
            seen_users.add(user_id)
            names = user_names_str(ctx, db, user_id, username=username)
            user_strs.append(names)

        if user_strs:
            await Embeds.info(ctx, message=user_strs)
        else:
            await Embeds.error(ctx, 'No users found with this name.')
