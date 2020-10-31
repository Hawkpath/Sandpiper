from typing import List
import unittest
import unittest.mock as mock

import discord
import discord.ext.commands as commands

__all__ = ['DiscordMockingTestCase']


class DiscordMockingTestCase(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # This is the meat of the operation; it allows for message properties
        # to be set where normally it is prohibited
        self.msg = mock.MagicMock(spec=discord.Message)
        self.msg.author.bot = False  # Otherwise the invocation will be skipped

        # Create a dummy bot that will never actually connect but will help
        # with invocation
        self.bot = commands.Bot(command_prefix='')
        self.setup_cogs(self.bot)

        # This function checks if message author is the self bot and skips
        # context creation (meaning we won't get command invocation), so
        # we will bypass it
        patcher = mock.patch.object(self.bot, '_skip_check', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

        # This connection (discord.state.ConnectionState) object has a `user`
        # field which is accessed by the client's `user` property. The
        # _skip_check function is called with `client.user.id` which doesn't
        # exist (since we aren't connecting) and raises an AttributeError, so
        # we need to patch it in.
        patcher = mock.patch.object(self.bot, '_connection')
        connection_mock = patcher.start()
        connection_mock.user.id = 0
        self.addCleanup(patcher.stop)

    def setup_cogs(self, bot: commands.Bot):
        pass

    async def invoke_cmd(self, message_content: str) -> mock.AsyncMock:
        """
        Use self._msg to invoke a command.

        :returns: an AsyncMock representing the `ctx.send` method. You can use
            the methods defined in Mock to check the calls to this method by
            the command invocation.
        """
        self.msg.content = message_content
        ctx = await self.bot.get_context(self.msg)
        ctx.send = mock.AsyncMock()
        # This is normally done with bot.invoke, but that silently suppresses
        # errors which is BAD!!! >:(
        await ctx.command.invoke(ctx)
        return ctx.send

    async def invoke_cmd_get_embeds(
            self, message_content: str) -> List[discord.Embed]:
        send = await self.invoke_cmd(message_content)
        return [
            embed for call in send.call_args_list
            if (embed := call.kwargs.get('embed'))
        ]

    async def dispatch_msg(self, message_content: str) -> mock.AsyncMock:
        self.msg.content = message_content
        self.msg.channel.send = mock.AsyncMock()

        for listener in self.bot.extra_events.get('on_message', []):
            await listener(self.msg)
        return self.msg.channel.send

    async def dispatch_msg_get_msgs(self, message_content: str) -> List[str]:
        send = await self.dispatch_msg(message_content)
        return [
            content for call in send.call_args_list
            if (content := call.args[0]) is not None
        ]

    def assert_success(self, embed: discord.Embed, description: str = None):
        self.assertIn('Success', embed.title)
        if description is not None:
            self.assertIn(description, embed.description)

    def assert_warning(self, embed: discord.Embed, description: str = None):
        self.assertIn('Warning', embed.title)
        if description is not None:
            self.assertIn(description, embed.description)

    def assert_error(self, embed: discord.Embed, description: str = None):
        self.assertIn('Error', embed.title)
        if description is not None:
            self.assertIn(description, embed.description)

    def assert_info(self, embed: discord.Embed, description: str = None):
        self.assertIn('Info', embed.title)
        if description is not None:
            self.assertIn(description, embed.description)
