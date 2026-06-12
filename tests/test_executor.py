import time
import pytest
import asyncio
from agenthooks.executor.sequential import SequentialExecutor
from agenthooks.executor.parallel import ParallelExecutor
from agenthooks.core.registry import HookRegistry
from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked

def make_ctx(**kwargs) -> HookContext:
    defaults = dict(session_id="s1", tenant_id="acme", trace_id="t1", span_id="sp1", turn=0, timestamp=time.time())
    return HookContext(**{**defaults, **kwargs})

def make_impl(registry, name, order, enrich_key, enrich_val):
    async def impl(ctx: HookContext) -> HookContext:
        return ctx.enrich(enrich_key, enrich_val)
    impl.__name__ = name
    return registry.implement("test_hp", order=order)(impl)

@pytest.mark.asyncio
async def test_sequential_runs_in_order():
    registry = HookRegistry()
    results = []

    @registry.implement("test_hp", order=10)
    async def first(ctx: HookContext) -> HookContext:
        results.append("first")
        return ctx.enrich("first", True)

    @registry.implement("test_hp", order=20)
    async def second(ctx: HookContext) -> HookContext:
        results.append("second")
        return ctx.enrich("second", True)

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = SequentialExecutor()
    result = await executor.run("test_hp", impls, ctx)
    assert results == ["first", "second"]
    assert result.metadata["first"] is True
    assert result.metadata["second"] is True

@pytest.mark.asyncio
async def test_sequential_passes_ctx_through_chain():
    registry = HookRegistry()

    @registry.implement("test_hp", order=10)
    async def add_plant(ctx: HookContext) -> HookContext:
        return ctx.enrich("plant", "1000")

    @registry.implement("test_hp", order=20)
    async def use_plant(ctx: HookContext) -> HookContext:
        plant = ctx.metadata.get("plant")
        return ctx.enrich("plant_used", plant)

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = SequentialExecutor()
    result = await executor.run("test_hp", impls, ctx)
    assert result.metadata["plant_used"] == "1000"

@pytest.mark.asyncio
async def test_sequential_blocked_propagates():
    registry = HookRegistry()

    @registry.implement("test_hp")
    async def blocking(ctx: HookContext) -> HookContext:
        raise HookBlocked("no access")

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = SequentialExecutor()
    with pytest.raises(HookBlocked, match="no access"):
        await executor.run("test_hp", impls, ctx)

@pytest.mark.asyncio
async def test_sequential_timeout_degrades():
    registry = HookRegistry()

    @registry.implement("test_hp", timeout_ms=50, fallback=True)
    async def slow(ctx: HookContext) -> HookContext:
        await asyncio.sleep(2.0)
        return ctx.enrich("slow_data", True)

    @registry.implement("test_hp", order=200)
    async def reliable(ctx: HookContext) -> HookContext:
        return ctx.enrich("reliable", True)

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = SequentialExecutor()
    result = await executor.run("test_hp", impls, ctx)
    assert result.metadata.get("slow_data") is None
    assert result.metadata["reliable"] is True

@pytest.mark.asyncio
async def test_parallel_merges_metadata():
    registry = HookRegistry()

    @registry.implement("test_hp", parallel=True)
    async def impl_a(ctx: HookContext) -> HookContext:
        return ctx.enrich("a", 1)

    @registry.implement("test_hp", parallel=True)
    async def impl_b(ctx: HookContext) -> HookContext:
        return ctx.enrich("b", 2)

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = ParallelExecutor()
    result = await executor.run("test_hp", impls, ctx)
    assert result.metadata["a"] == 1
    assert result.metadata["b"] == 2

@pytest.mark.asyncio
async def test_parallel_one_fails_others_still_run():
    registry = HookRegistry()

    @registry.implement("test_hp", parallel=True, fallback=True)
    async def failing(ctx: HookContext) -> HookContext:
        raise ValueError("boom")

    @registry.implement("test_hp", parallel=True)
    async def succeeding(ctx: HookContext) -> HookContext:
        return ctx.enrich("success", True)

    ctx = make_ctx()
    impls = registry.get_impls("test_hp", ctx)
    executor = ParallelExecutor()
    result = await executor.run("test_hp", impls, ctx)
    assert result.metadata.get("success") is True
