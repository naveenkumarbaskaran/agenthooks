from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from agenthooks.audit import get_default_audit
from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked, HookSkip, HookTimeout
from agenthooks.observability import hook_span, record_metric

if TYPE_CHECKING:
    from agenthooks.core.registry import HookRegistry, ImplRegistration

logger = logging.getLogger("agenthooks.hookpoint")


class HookPointDescriptor:
    def __init__(self, name: str, mode: str = "multi", parallel: bool = False, registries: list[HookRegistry] | None = None) -> None:
        self.name = name
        self.mode = mode
        self.parallel = parallel
        self._registries: list[HookRegistry] = registries or []

    def add_registry(self, registry: HookRegistry) -> None:
        self._registries.append(registry)

    def _get_impls(self, ctx: HookContext) -> list[ImplRegistration]:
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


async def _run_one(hookpoint_name: str, reg: ImplRegistration, ctx: HookContext) -> tuple[HookContext, str]:
    impl_name = reg.fn.__name__
    t0 = time.monotonic()

    with hook_span(hookpoint_name, impl_name, ctx) as span:
        try:
            result = await asyncio.wait_for(reg.fn(ctx), timeout=reg.timeout_ms / 1000)
            duration_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "hook ok: hookpoint=%s impl=%s elapsed=%.1fms",
                hookpoint_name, impl_name, duration_ms,
            )
            record_metric(hookpoint_name, impl_name, "ok", duration_ms)
            span.set_attribute("hook.status", "ok")
            span.set_attribute("hook.duration_ms", round(duration_ms, 2))
            asyncio.ensure_future(
                get_default_audit().record(
                    hookpoint=hookpoint_name, impl_name=impl_name, ctx=ctx,
                    status="ok", duration_ms=duration_ms,
                )
            )
            return result, "ok"

        except TimeoutError:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "hook timeout: hookpoint=%s impl=%s timeout_ms=%d — degraded",
                hookpoint_name, impl_name, reg.timeout_ms,
            )
            record_metric(hookpoint_name, impl_name, "timeout", duration_ms)
            span.set_attribute("hook.status", "timeout")
            span.set_attribute("hook.duration_ms", round(duration_ms, 2))
            asyncio.ensure_future(
                get_default_audit().record(
                    hookpoint=hookpoint_name, impl_name=impl_name, ctx=ctx,
                    status="timeout", duration_ms=duration_ms,
                    error=f"timed out after {reg.timeout_ms}ms",
                )
            )
            if not reg.fallback:
                raise HookTimeout(hookpoint_name, impl_name, reg.timeout_ms)
            return ctx, "timeout"

        except HookBlocked as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            record_metric(hookpoint_name, impl_name, "blocked", duration_ms)
            span.set_attribute("hook.status", "blocked")
            span.set_attribute("hook.error", exc.reason)
            asyncio.ensure_future(
                get_default_audit().record(
                    hookpoint=hookpoint_name, impl_name=impl_name, ctx=ctx,
                    status="blocked", duration_ms=duration_ms, error=exc.reason,
                )
            )
            raise

        except HookSkip:
            duration_ms = (time.monotonic() - t0) * 1000
            record_metric(hookpoint_name, impl_name, "skip", duration_ms)
            span.set_attribute("hook.status", "skip")
            raise

        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "hook error: hookpoint=%s impl=%s error=%s — degraded",
                hookpoint_name, impl_name, exc,
            )
            record_metric(hookpoint_name, impl_name, "error", duration_ms)
            span.set_attribute("hook.status", "error")
            span.record_exception(exc)
            asyncio.ensure_future(
                get_default_audit().record(
                    hookpoint=hookpoint_name, impl_name=impl_name, ctx=ctx,
                    status="error", duration_ms=duration_ms, error=str(exc),
                )
            )
            if not reg.fallback:
                raise
            return ctx, "error"


async def _run_sequential(hookpoint_name: str, impls: list[ImplRegistration], ctx: HookContext) -> HookContext:
    for reg in impls:
        try:
            ctx, _ = await _run_one(hookpoint_name, reg, ctx)
        except HookSkip:
            break
    return ctx


async def _run_parallel(hookpoint_name: str, impls: list[ImplRegistration], ctx: HookContext) -> HookContext:
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


def hookpoint(name: str, *, mode: str = "multi", parallel: bool = False, schema: type | None = None, contract_version: str | None = None, registries: list[HookRegistry] | None = None) -> HookPointDescriptor:
    return HookPointDescriptor(name=name, mode=mode, parallel=parallel, registries=registries or [])
