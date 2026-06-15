"""Tests for the OTel observability layer.

These tests run WITHOUT the opentelemetry-sdk installed to verify the
zero-dep fallback path. They also verify that metric instruments accumulate
correctly via the in-process meter.
"""
import pytest
from agenthooks.core.context import HookContext
from agenthooks.core.registry import HookRegistry
from agenthooks.core.hookpoint import hookpoint
from agenthooks.observability import (
    get_tracer, get_meter, get_instruments, record_metric,
    hook_span, _OTEL_TRACING, _OTEL_METRICS, _InProcessMeter,
)


def make_ctx(tenant_id="acme") -> HookContext:
    return HookContext.new(session_id="s1", tenant_id=tenant_id)


# ── Tracer fallback ──────────────────────────────────────────────────────────

def test_get_tracer_returns_something():
    tracer = get_tracer()
    assert tracer is not None


def test_hook_span_context_manager_does_not_raise():
    ctx = make_ctx()
    with hook_span("before_call", "my_impl", ctx) as span:
        span.set_attribute("hook.status", "ok")


def test_hook_span_noop_when_no_sdk():
    if _OTEL_TRACING:
        pytest.skip("OTel SDK installed — testing live tracer")
    ctx = make_ctx()
    with hook_span("before_call", "my_impl", ctx) as span:
        # NoopSpan — none of these should raise
        span.set_attribute("hook.name", "before_call")
        span.set_attribute("hook.duration_ms", 12.3)
        span.record_exception(ValueError("test"))
        span.add_event("hook.degraded")


# ── Meter / metrics ──────────────────────────────────────────────────────────

def test_record_metric_does_not_raise():
    record_metric("before_call", "my_impl", "ok", 42.0)


def test_instruments_accumulate_executions():
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed — use SDK test utilities instead")

    before = (meter.get_counter("agenthooks.hook.executions") or type("_", (), {"total": lambda s: 0})()).total()
    record_metric("test_hookpoint", "test_impl", "ok", 10.0)
    after = meter.get_counter("agenthooks.hook.executions").total()
    assert after == before + 1


def test_instruments_accumulate_errors():
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed — use SDK test utilities instead")

    record_metric("test_hookpoint", "failing_impl", "error", 5.0)
    counter = meter.get_counter("agenthooks.hook.errors")
    assert counter is not None
    assert counter.total() >= 1


def test_instruments_accumulate_timeouts():
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed — use SDK test utilities instead")

    record_metric("test_hookpoint", "slow_impl", "timeout", 500.0)
    counter = meter.get_counter("agenthooks.hook.timeouts")
    assert counter is not None
    assert counter.total() >= 1


def test_instruments_histogram_records():
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed — use SDK test utilities instead")

    record_metric("test_hookpoint", "some_impl", "ok", 99.5)
    hist = meter.get_histogram("agenthooks.hook.duration_ms")
    assert hist is not None
    assert hist.count >= 1
    assert hist.sum >= 99.5


# ── Integration: metrics fire through hookpoint executor ────────────────────

@pytest.mark.asyncio
async def test_executor_records_metrics_on_ok():
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed")

    registry = HookRegistry()
    hp = hookpoint("metrics_test_ok", registries=[registry])

    @registry.implement("metrics_test_ok")
    async def enrich(ctx: HookContext) -> HookContext:
        return ctx.enrich("x", 1)

    before = (meter.get_counter("agenthooks.hook.executions") or type("_", (), {"total": lambda s: 0})()).total()
    async with hp.run(make_ctx()):
        pass
    after = meter.get_counter("agenthooks.hook.executions").total()
    assert after == before + 1


@pytest.mark.asyncio
async def test_executor_records_metrics_on_timeout():
    import asyncio
    instruments = get_instruments()
    meter = instruments.meter
    if not isinstance(meter, _InProcessMeter):
        pytest.skip("OTel SDK installed")

    registry = HookRegistry()
    hp = hookpoint("metrics_test_timeout", registries=[registry])

    @registry.implement("metrics_test_timeout", timeout_ms=50, fallback=True)
    async def slow(ctx: HookContext) -> HookContext:
        await asyncio.sleep(1.0)
        return ctx

    before = (meter.get_counter("agenthooks.hook.timeouts") or type("_", (), {"total": lambda s: 0})()).total()
    async with hp.run(make_ctx()):
        pass
    after = meter.get_counter("agenthooks.hook.timeouts").total()
    assert after == before + 1


# ── configure_logging ────────────────────────────────────────────────────────

def test_configure_logging_does_not_raise():
    import logging
    from agenthooks.observability import configure_logging
    configure_logging(level=logging.WARNING)
