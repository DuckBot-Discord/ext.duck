from discord.utils import MISSING
from discord.ext import commands

from proc_base import BaseWebserver


class WebserverCog(commands.Cog, BaseWebserver):
    """A webserver cog that implements cog_load and cog_unload to set up the webserver.

    .. code-block:: python3

        from aiohttp import web
        from discord.ext.duck import webserver

        class MyWSCog(webserver.WebserverCog, port=8080):
            @webserver.route('GET', '/stats')
            async def stats(self, request: web.Request) :
                return web.json_response({'stats': {'servers': 1e9}})

        # then, somewhere:
        await bot.add_cog(MyWSCog())
    """

    __runner_port__: int
    __runner_host__: str

    def __init_subclass__(cls, *, auto_start: bool = True, host: str = "localhost", port: int = MISSING) -> None:
        if auto_start is True and port is MISSING:
            message = (
                f"A port must be provided when auto_start=True. For example:\n"
                f"\nclass {cls.__name__}(WebserverCog, port=8080):\n    ...\n"
                f"\nclass {cls.__name__}(WebserverCog, auto_start=False):"
                '\n    """You are responsible for calling (async) self.start(port=...) when using this."""\n\n'
            )
            raise RuntimeError(message)
        cls.__runner_port__ = port
        cls.__runner_host__ = host
        return super().__init_subclass__()

    async def cog_load(self) -> None:
        try:
            await self.start(host=self.__runner_host__, port=self.__runner_port__)
        finally:
            return await super().cog_load()

    async def cog_unload(self) -> None:
        try:
            await self.close()
        finally:
            return await super().cog_unload()
