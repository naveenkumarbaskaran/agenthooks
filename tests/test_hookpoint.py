import asyncio
import time

import pytest

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked
from agenthooks.core.hookpoint import hookpoint
from agenthooks.core.registry import HookRegistry


def make_ctx(**kwargs) -> HookContext:
    defaults = dict(session_id="s1", tenant_id="acme", trace_id="t1", span_id="sp1", turn=0, timestamp=time.time())
    return HookContext(**{**defaults, **kwargs})

@pytest.mark.asyncio
async def test_runs_registered_impl():
    registry = HookRegistry()

    @registry.implement("before_call")
    async def my_impl(ctx: HookContext) -> HookContext:
        return ctx.enrich("ran", True)

    hp = hookpoint("before_call", registries=[registry])
    ctx = make_ctx()
    async with hp.run(ctx) as result:
        assert result.metadata.get("ran") is True

@pytest.mark.asyncio
async def test_no_impls_passes_through():
    hp = hookpoint("before_call")
    ctx = make_ctx(query="hello")
    async with hp.run(ctx) as result:
        assert result.query == "hello"
        assert result is ctx

@pytest.mark.asyncio
async def test_blocked_propagates():
    registry = HookRegistry()

    @registry.implement("before_call")
    async def blocking_impl(ctx: HookContext) -> HookContext:
        raise HookBlocked("Not allowed")

    hp = hookpoint("before_call", registries=[registry])
    ctx = make_ctx()
    with pytest.raises(HookBlocked, match="Not allowed"):
        async with hp.run(ctx):
            pass

@pytest.mark.asyncio
async def test_timeout_degrades_not_crash():
    registry = HookRegistry()

    @registry.implement("before_call", timeout_ms=50, fallback=True)
    async def slow_impl(ctx: HookContext) -> HookContext:
        await asyncio.sleep(1.0)
        return ctx.enrich("slow", True)

    hp = hookpoint("before_call", registries=[registry])
    ctx = make_ctx()
    async with hp.run(ctx) as result:
        # Should not crash, slow_data not in metadata
        assert result.metadata.get("slow") is None

@pytest.mark.asyncio
async def test_sequential_pipeline():
    registry = HookRegistry()

    @registry.implement("before_call", order=10)
    async def first(ctx: HookContext) -> HookContext:
        return ctx.enrich("step", "first")

    @registry.implement("before_call", order=20)
    async def second(ctx: HookContext) -> HookContext:
        return ctx.enrich("step2", "second")

    hp = hookpoint("before_call", registries=[registry])
    ctx = make_ctx()
    async with hp.run(ctx) as result:
        assert result.metadata["step"] == "first"
        assert result.metadata["step2"] == "second"

def test_is_descriptor_on_class():
    from agenthooks import HookAgent

    class MyAgent(HookAgent):
        before_call = hookpoint("before_call")

    agent = MyAgent()
    # The instance should have an instance-level hookpoint
    assert hasattr(agent, "before_call")
