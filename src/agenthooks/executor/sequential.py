from __future__ import annotations

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookSkip
from agenthooks.core.hookpoint import _run_one
from agenthooks.core.registry import ImplRegistration


class SequentialExecutor:
    async def run(self, hookpoint_name: str, impls: list[ImplRegistration], ctx: HookContext) -> HookContext:
        for reg in sorted(impls, key=lambda r: r.order):
            try:
                ctx, _ = await _run_one(hookpoint_name, reg, ctx)
            except HookSkip:
                break
        return ctx
