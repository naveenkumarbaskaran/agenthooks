from __future__ import annotations

from typing import Protocol, runtime_checkable

from agenthooks.core.context import HookContext
from agenthooks.core.registry import ImplRegistration


@runtime_checkable
class BaseExecutor(Protocol):
    async def run(self, hookpoint_name: str, impls: list[ImplRegistration], ctx: HookContext) -> HookContext: ...
