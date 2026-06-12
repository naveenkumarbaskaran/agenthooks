from __future__ import annotations
import asyncio
from agenthooks.core.context import HookContext
from agenthooks.core.hookpoint import _run_one
from agenthooks.core.registry import ImplRegistration

class ParallelExecutor:
    async def run(self, hookpoint_name: str, impls: list[ImplRegistration], ctx: HookContext) -> HookContext:
        tasks = [_run_one(hookpoint_name, reg, ctx) for reg in impls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged_metadata = dict(ctx.metadata)
        for result in results:
            if isinstance(result, BaseException):
                continue
            result_ctx, status = result
            if status == "ok":
                merged_metadata.update(result_ctx.metadata)
        try:
            return ctx.model_copy(update={"metadata": merged_metadata})
        except AttributeError:
            return ctx._copy(metadata=merged_metadata)
