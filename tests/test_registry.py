import time

import pytest

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookConflict, HookContractError
from agenthooks.core.registry import HookRegistry


def make_ctx(**kwargs) -> HookContext:
    defaults = dict(session_id="s1", tenant_id="acme", trace_id="t1", span_id="sp1", turn=0, timestamp=time.time())
    return HookContext(**{**defaults, **kwargs})

def test_register_via_decorator():
    registry = HookRegistry()

    @registry.implement("before_call")
    async def my_impl(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx()
    impls = registry.get_impls("before_call", ctx)
    assert len(impls) == 1
    assert impls[0].fn is my_impl

def test_filter_by_tenant():
    registry = HookRegistry()

    @registry.implement("before_call", filter={"tenant": "ACME"})
    async def acme_impl(ctx: HookContext) -> HookContext:
        return ctx

    @registry.implement("before_call", filter={"tenant": "SIEMENS"})
    async def siemens_impl(ctx: HookContext) -> HookContext:
        return ctx

    acme_ctx = make_ctx(tenant_id="ACME")
    siemens_ctx = make_ctx(tenant_id="SIEMENS")

    assert len(registry.get_impls("before_call", acme_ctx)) == 1
    assert registry.get_impls("before_call", acme_ctx)[0].fn is acme_impl
    assert len(registry.get_impls("before_call", siemens_ctx)) == 1
    assert registry.get_impls("before_call", siemens_ctx)[0].fn is siemens_impl

def test_filter_by_metadata():
    registry = HookRegistry()

    @registry.implement("before_call", filter={"env": "prod"})
    async def prod_impl(ctx: HookContext) -> HookContext:
        return ctx

    prod_ctx = make_ctx().enrich("env", "prod")
    dev_ctx = make_ctx().enrich("env", "dev")

    assert len(registry.get_impls("before_call", prod_ctx)) == 1
    assert len(registry.get_impls("before_call", dev_ctx)) == 0

def test_order_sorts_impls():
    registry = HookRegistry()

    @registry.implement("before_call", order=30)
    async def third(ctx: HookContext) -> HookContext:
        return ctx

    @registry.implement("before_call", order=10)
    async def first(ctx: HookContext) -> HookContext:
        return ctx

    @registry.implement("before_call", order=20)
    async def second(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx()
    impls = registry.get_impls("before_call", ctx)
    assert [r.fn.__name__ for r in impls] == ["first", "second", "third"]

def test_single_mode_conflict_raises():
    registry = HookRegistry()

    @registry.implement("before_teco", mode="single")
    async def first_impl(ctx: HookContext) -> HookContext:
        return ctx

    with pytest.raises(HookConflict):
        @registry.implement("before_teco", mode="single")
        async def second_impl(ctx: HookContext) -> HookContext:
            return ctx

def test_multi_mode_allows_multiple():
    registry = HookRegistry()

    @registry.implement("before_call", mode="multi")
    async def impl1(ctx: HookContext) -> HookContext:
        return ctx

    @registry.implement("before_call", mode="multi")
    async def impl2(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx()
    assert len(registry.get_impls("before_call", ctx)) == 2

def test_contract_mismatch_raises():
    registry = HookRegistry()

    with pytest.raises(HookContractError):
        @registry.implement("before_call", hookpoint_contract=">=1.0", contract_version="0.9")
        async def impl(ctx: HookContext) -> HookContext:
            return ctx

def test_impl_stores_metadata():
    registry = HookRegistry()

    @registry.implement("before_call", order=42, timeout_ms=1000, fallback=False)
    async def my_impl(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx()
    impls = registry.get_impls("before_call", ctx)
    assert impls[0].order == 42
    assert impls[0].timeout_ms == 1000
    assert impls[0].fallback is False
