from __future__ import annotations
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator
from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked, HookSkip, HookTimeout

if TYPE_CHECKING:
    from agenthooks.core.registry import HookRegistry, ImplRegistration

logger = logging.getLogger("agenthooks.hookpoint")


class HookPointDescriptor:
    def __init__(self, name: str, mode: str = "multi", parallel: bool = False, registries: list["HookRegistry"] | None = None) -> None:
        self.name = name
        self.mode = mode
        self.parallel = parallel
        self._registries: list["HookRegistry"] = registries or []

    def add_registry(self, registry: "HookRegistry") -> None:
        self._registries.append(registry)

    def _get_impls(self, ctx: HookContext) -> list["ImplRegistration"]:
        impls = []
        for reg in self._registries:
            impls.extend(reg.get_impls(self.name, ctx))
        return sorted(impls, key=lambda r: r.order)

    @asynccontextmanager
    async def run(self, ctx: HookContext) -> AsyncIterator[HookContext]:
        impls = self._get_impls(ctx)
        if not impls:
            yield ctx
            return
        if self.parallel or any(r.parallel for r in impls):
            ctx = await _run_parallel(self.name, impls, ctx)
        else:
            ctx = await _run_sequential(self.name, impls, ctx)
        yield ctx


async def _run_one(hookpoint_name: str, reg: "ImplRegistration", ctx: HookContext) -> tuple[HookContext, str]:
    impl_name = reg.fn.__name__
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(reg.fn(ctx), timeout=reg.timeout_ms / 1000)
        logger.debug("hook ok: hookpoint=%s impl=%s elapsed=%.1fms", hookpoint_name, impl_name, (time.monotonic() - t0) * 1000)
        return result, "ok"
    except asyncio.TimeoutError:
        logger.warning("hook timeout: hookpoint=%s impl=%s timeout_ms=%d — degraded", hookpoint_name, impl_name, reg.timeout_ms)
        if not reg.fallback:
            raise HookTimeout(hookpoint_name, impl_name, reg.timeout_ms)
        return ctx, "timeout"
    except HookBlocked:
        raise
    except HookSkip:
        raise
    except Exception as exc:
        logger.error("hook error: hookpoint=%s impl=%s error=%s — degraded", hookpoint_name, impl_name, exc)
        if not reg.fallback:
            raise
        return ctx, "error"


async def _run_sequential(hookpoint_name: str, impls: list["ImplRegistration"], ctx: HookContext) -> HookContext:
    for reg in impls:
        try:
            ctx, _ = await _run_one(hookpoint_name, reg, ctx)
        except HookSkip:
            break
    return ctx


async def _run_parallel(hookpoint_name: str, impls: list["ImplRegistration"], ctx: HookContext) -> HookContext:
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


def hookpoint(name: str, *, mode: str = "multi", parallel: bool = False, schema: type | None = None, contract_version: str | None = None, registries: list["HookRegistry"] | None = None) -> "HookPointDescriptor":
    return HookPointDescriptor(name=name, mode=mode, parallel=parallel, registries=registries or [])
