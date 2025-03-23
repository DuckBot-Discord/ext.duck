# Webserver module.

This module wraps an aiohttp.web webserver to be used as a cog. The following classes and functions are implemented:

- `BaseWebserver` - Base class to handle the connection.
- `WebserverCog` - Class that wraps the base class as a cog, so it can be added to a discord.py Bot.
- `route` - Decorator to define a route. Uses aiohttp.web syntax.

## Example usage:

```py
from aiohttp import web
from discord.ext import commands
from discord.ext.duck import webserver

class MyWSCog(webserver.WebserverCog, port=8080):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    @webserver.route('GET', '/stats')
    async def stats(self, request: web.Request) :
        return web.json_response({'stats': {'servers': len(self.bot.guilds)}})

    @webserver.route('GET', "/users/{id}")
    async def get_user(self, request: web.Request):
        user_id = int(request.match_info["id"])
        user = await self.bot.fetch_user(user_id)

        if not user:
            return web.json_response({"detail": "User not found."}, status=404)

        return web.json_response({'id': user.id, 'name': user.name})

# then, somewhere:
async def setup(bot: commands.Bot)
    await bot.add_cog(MyWSCog(bot))
```
