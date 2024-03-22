import inspect
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    TypeVar,
)

from aiohttp import web


__all__: Tuple[str, ...] = ("BaseWebserver", "route")

FuncT = TypeVar("FuncT", bound="Callable[..., Any]")


class Route(NamedTuple):
    name: str
    method: str
    func: Callable[..., Any]


def route(method: Literal["get", "post", "put", "patch", "delete"], request_path: str) -> Callable[[FuncT], FuncT]:
    def decorator(func: FuncT) -> FuncT:
        actual = func
        if isinstance(actual, staticmethod):
            actual = actual.__func__
        if not inspect.iscoroutinefunction(actual):
            raise TypeError("Route function must be a coroutine.")

        actual.__ipc_route_path__ = request_path  # type: ignore
        actual.__ipc_method__ = method  # type: ignore
        return func

    return decorator


class BaseWebserver:
    @property
    def logger(self):
        return logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def __init__(self):
        self.routes: List[Route] = []

        self.app: web.Application = web.Application()
        self._runner = web.AppRunner(self.app)
        self._webserver: Optional[web.TCPSite] = None

        for attr in map(lambda x: getattr(self, x, None), dir(self)):
            if attr is None:
                continue
            if (name := getattr(attr, "__ipc_route_path__", None)) is not None:
                route: str = attr.__ipc_method__
                self.routes.append(Route(func=attr, name=name, method=route))

        self.app.add_routes([web.route(x.method, x.name, x.func) for x in self.routes])

    async def start(self, *, host: str = "localhost", port: int):
        self.logger.debug(f"Starting {type(self).__name__} runner.")
        await self._runner.setup()
        self.logger.debug(f"Starting {type(self).__name__} webserver.")
        self._webserver = web.TCPSite(self._runner, host=host, port=port)
        await self._webserver.start()
        self._webserver.start

    async def close(self):
        self.logger.debug(f"Cleaning up after {type(self).__name__}.")
        await self._runner.cleanup()
        if self._webserver:
            self.logger.debug(f"Closing {type(self).__name__} webserver.")
            await self._webserver.stop()
