from __future__ import annotations

import sys
import asyncio
import datetime
import os
import traceback
from logging import getLogger
from typing import Tuple, Optional, Dict, List, Generator, Any, TypedDict, NamedTuple, TypeVar

import aiohttp
import discord
from discord.ext import commands


__all__: Tuple[str, ...] = (
    "ErrorManager",
    "CommandErrorSettings",
)


class _TracebackOptional(TypedDict, total=False):
    author: int
    guild: Optional[int]
    channel: Optional[int]
    command: Optional[
        commands.Command[Any, Any, Any] | discord.app_commands.Command[Any, Any, Any] | discord.app_commands.ContextMenu
    ]
    item: Optional[discord.ui.Item[discord.ui.View]]


class TracebackData(_TracebackOptional):
    time: datetime.datetime
    exception: BaseException


class CommandErrorSettings(NamedTuple):
    hijack: bool
    ignored_errors: tuple[type[commands.CommandError], ...] = (
        commands.NotOwner,
        commands.CommandNotFound,
    )
    check_for_local_error_handlers: bool = True


log = getLogger(__name__)


class ErrorManager:
    """A simple exception handler that sends all exceptions to a error
    Webhook and then logs them to the console.

    This class handles cooldowns with a simple lock, so you don't have to worry about
    rate limiting your webhook and getting banned :).

    .. note::

        If some code is raising MANY errors VERY fast and you're not there to fix it,
        this will take care of things for you.

    Parameters
    ----------
    bot: commands.Bot
        The bot instance. Will be used to authenticate the webhook.
    webhook_url: str
        A valid webhook URL.
    session: aiohttp.ClientSession
        The aiohttp session to send the errors to.
    hijack_bot_on_error: bool = False
        Whether the default bot's on_error should be overwritten.
    on_command_error_settings: CommandErrorSettings = CommandErrorSettings(hijack=False)
        An instance of CommandErrorSettings, used to configure the behaviour of the
        hijacked on_command_error. By default, it will not hijack.
    cooldown: Cooldown = Cooldown()
        Wait time between webhook sends. Defaults to 5 seconds.
    mention_developers: bool = False
        Whether the bot developers should be mentioned in the message's content.
        Defaults to False, could be very spammy and unpleasant. Better not enable it!


    Attributes
    ----------
    bot: Bot
        The bot instance.
    cooldown: datetime.timedelta
        The cooldown between sending errors. This defaults to 5 seconds.
    errors: Dict[str, Dict[str, Any]]
        A mapping of tracebacks to their error information, this
        is all the errors that are waiting to be sent (if any).
    code_blocker: str
        The code blocker used to format Discord codeblocks.
        A standard .format(tb) call is used to format this.
    error_webhook: discord.Webhook
        The error webhook used to send errors.
    oce_settings: CommandErrorSettings

    """

    __slots__: Tuple[str, ...] = (
        "bot",
        "cooldown",
        "_lock",
        "_most_recent",
        "errors",
        "code_blocker",
        "error_webhook",
        "oce_settings",
    )

    def __init__(
        self,
        bot: commands.Bot,
        *,
        webhook_url: str,
        session: aiohttp.ClientSession,
        hijack_bot_on_error: bool = False,
        on_command_error_settings: CommandErrorSettings = CommandErrorSettings(hijack=False),
        cooldown: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> None:
        self.bot: commands.Bot = bot
        self.cooldown: datetime.timedelta = cooldown

        self._lock: asyncio.Lock = asyncio.Lock()
        self._most_recent: Optional[datetime.datetime] = None

        self.errors: Dict[str, List[TracebackData]] = {}
        self.code_blocker: str = "```py\n{}```"
        self.error_webhook: discord.Webhook = discord.Webhook.from_url(
            webhook_url, session=session, bot_token=bot.http.token
        )
        self.oce_settings = on_command_error_settings

        if hijack_bot_on_error:
            bot.on_error = self.bot_on_error

        if on_command_error_settings.hijack:
            bot.on_command_error = self.bot_command_error

    async def bot_command_error(self, ctx: commands.Context[commands.Bot], error: commands.CommandError) -> None:
        if self.oce_settings.check_for_local_error_handlers:
            if ctx.bot.extra_events.get("on_command_error", None):
                return

            command = ctx.command
            if command and command.has_error_handler():
                return

            cog = ctx.cog
            if cog and cog.has_error_handler():
                return

        if isinstance(error, self.oce_settings.ignored_errors):
            return
        elif isinstance(error, commands.CommandInvokeError):
            await self.add_error(error=error.original, ctx=ctx)
        else:
            await ctx.send(str(error))

    async def bot_on_error(self, *args: Any, **kwargs: Any):
        _, error, _ = sys.exc_info()
        if error:
            await self.add_error(error=error)

    def _yield_code_chunks(self, iterable: str, *, chunksize: int = 2000) -> Generator[str, None, None]:
        cbs = len(self.code_blocker) - 2  # code blocker size

        for i in range(0, len(iterable), chunksize - cbs):
            yield self.code_blocker.format(iterable[i : i + chunksize - cbs])

    async def release_error(self, traceback: str, packet: TracebackData) -> None:
        """|coro|

        Releases an error to the webhook and logs it to the console. It is not recommended
        to call this yourself, call :meth:`add_error` instead.

        Parameters
        ----------
        traceback: str
            The traceback of the error.
        packet: dict
            The additional information about the error.
        """
        log.error("Releasing error to log", exc_info=packet["exception"])

        if self.error_webhook.is_partial():
            self.error_webhook = await self.error_webhook.fetch()

        fmt = {
            "time": discord.utils.format_dt(packet["time"]),
        }
        if author := packet.get("author"):
            fmt["author"] = f"<@{author}>"

        # This is a bit of a hack,  but I do it here so guild_id
        # can be optional, and I wont get type errors.
        guild_id = packet.get("guild")
        guild = self.bot.get_guild(guild_id)  # pyright: ignore[reportGeneralTypeIssues]
        if guild:
            fmt["guild"] = f"{guild.name} ({guild.id})"
        else:
            log.warning("Ignoring error packet with unknown guild id %s", guild_id)

        if guild:
            channel_id = packet.get("channel")
            if channel_id and (channel := guild.get_channel(channel_id)):
                fmt["channel"] = f"{channel.name} - {channel.mention} - ({channel.id})"

            # Let's try and upgrade the author
            author_id = packet.get("author")
            if author_id:
                author = guild.get_member(author_id) or self.bot.get_user(author_id)
                if author:
                    fmt["author"] = f"{str(author)} - {author.mention} ({author.id})"

        if not fmt.get("author") and (author_id := packet.get("author")):
            fmt["author"] = f"<Unknown User> - <@{author_id}> ({author_id})"

        if command := packet.get("command"):
            fmt["command"] = command.qualified_name
            display = f'in command "{command.qualified_name}"'
        elif item := packet.get("item"):
            display = f"in Item {item} of view {item.view}"
        else:
            display = f"in no command ({type(self.bot).__name__})"

        embed = discord.Embed(title=f"An error has occurred in {display}", timestamp=packet["time"])
        embed.add_field(
            name="Metadata",
            value="\n".join([f"**{k.title()}**: {v}" for k, v in fmt.items()]),
        )

        kwargs: Dict[str, Any] = {}
        if self.bot.user:
            kwargs["username"] = self.bot.user.display_name
            kwargs["avatar_url"] = self.bot.user.display_avatar.url

            embed.set_author(name=str(self.bot.user), icon_url=self.bot.user.display_avatar.url)

        kwargs["content"] = "<@349373972103561218>"

        webhook = self.error_webhook
        if webhook.is_partial():
            self.error_webhook = webhook = await self.error_webhook.fetch()

        code_chunks = list(self._yield_code_chunks(traceback))

        embed.description = code_chunks.pop(0)
        await webhook.send(embed=embed, **kwargs)

        embeds: List[discord.Embed] = []
        for entry in code_chunks:
            embed = discord.Embed(description=entry)
            if self.bot.user:
                embed.set_author(name=str(self.bot.user), icon_url=self.bot.user.display_avatar.url)

            embeds.append(embed)

            if len(embeds) == 10:
                await webhook.send(embeds=embeds, **kwargs)
                embeds = []

        if embeds:
            await webhook.send(embeds=embeds, **kwargs)

    async def add_error(
        self,
        *,
        error: BaseException,
        ctx: Optional[commands.Context[commands.Bot] | discord.Interaction[commands.Bot]] = None,
        item: discord.ui.Item[discord.ui.View] | None = None,
    ) -> None:
        """|coro|

        Add an error to the error manager. This will handle all cool-downs and internal cache management
        for you. This is the recommended way to add errors.

        Parameters
        ----------
        error: Exception
            The error to add.
        ctx: Optional[commands.Context | discord.Interaction]
            The invocation context or interaction of the error, if any.
        """
        log.info('Adding error "%s" to log.', str(error))

        packet: TracebackData = {
            "time": ctx and ctx.message and ctx.message.created_at or discord.utils.utcnow(),
            "exception": error,
        }

        if isinstance(ctx, commands.Context):
            addons: _TracebackOptional = {
                "command": ctx.command,
                "author": ctx.author.id,
                "guild": (ctx.guild and ctx.guild.id) or None,
                "channel": ctx.channel.id,
            }
            packet.update(addons)
        elif isinstance(ctx, discord.Interaction):
            addons: _TracebackOptional = {
                "command": ctx.command,
                "author": ctx.user.id,
                "guild": (ctx.guild and ctx.guild.id) or None,
                "channel": ctx.channel_id,
            }

        traceback_string = "".join(traceback.format_exception(type(error), error, error.__traceback__)).replace(
            os.getcwd(), "CWD"
        )
        current = self.errors.get(traceback_string)

        if current:
            self.errors[traceback_string].append(packet)
        else:
            self.errors[traceback_string] = [packet]

        async with self._lock:
            # I want all other errors to be released after this one, which is why
            # lock is here. If you have code that calls MANY errors VERY fast,
            # this will rate limit the webhook. We don't want that.

            if not self._most_recent:
                self._most_recent = discord.utils.utcnow()
                await self.release_error(traceback_string, packet)
            else:
                time_between = packet["time"] - self._most_recent

                if time_between > self.cooldown:
                    self._most_recent = discord.utils.utcnow()
                    return await self.release_error(traceback_string, packet)
                else:  # We have to wait
                    log.debug(
                        "Waiting %s seconds to release error",
                        time_between.total_seconds(),
                    )
                    await asyncio.sleep(time_between.total_seconds())

                    self._most_recent = discord.utils.utcnow()
                    return await self.release_error(traceback_string, packet)
