"""Tool registry with permission scoping: an agent can only call tools its contract declares."""

from collections.abc import Awaitable, Callable
from typing import Any


class ToolPermissionError(Exception):
    pass


ToolFn = Callable[..., Awaitable[Any]]


class ToolRegistry:
    """The full set of tools known to the runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def scoped_to(self, allowed_tools: tuple[str, ...]) -> "ScopedToolRegistry":
        return ScopedToolRegistry(self._tools, allowed_tools)


class ScopedToolRegistry:
    """What an agent actually sees: only the tools its contract declared."""

    def __init__(self, tools: dict[str, ToolFn], allowed_tools: tuple[str, ...]) -> None:
        self._tools = tools
        self._allowed = set(allowed_tools)

    async def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self._allowed:
            raise ToolPermissionError(f"tool {name!r} is not in this agent's declared permissions")
        if name not in self._tools:
            raise KeyError(f"tool {name!r} is not registered")
        return await self._tools[name](*args, **kwargs)
