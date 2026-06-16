"""agenthooks observability — OpenTelemetry-grade instrumentation.

Architecture
------------
This module is the single integration point for all telemetry. It has
three layers that can be used independently or together:

1. **Tracing** — a span is created for every hook execution, parented
   to the active OTel span if one exists (so hook spans appear nested
   inside agent spans in Jaeger/Zipkin/Tempo). When the OTel SDK is not
   installed the NoopTracer produces zero-allocation stubs.

2. **Metrics** — OTel Metrics API counters and histograms. When the SDK
   is not installed a minimal in-process fallback accumulates counts so
   you can read them in tests/health-checks without the full SDK.

3. **Structured logging** — every log record carries trace_id and
   span_id so log aggregators (Loki, CloudWatch, Datadog Logs) can
   correlate logs with traces automatically.

Semantic conventions
--------------------
Attribute names follow the OpenTelemetry Semantic Conventions for
internal framework spans (lowercase dot-separated):

    hook.name         str   hookpoint name            e.g. "before_call"
    hook.impl         str   implementation fn name    e.g. "acme_inject"
    hook.tenant_id    str   ctx.tenant_id
    hook.session_id   str   ctx.session_id
    hook.trace_id     str   ctx.trace_id (hook-level)
    hook.status       str   ok|timeout|error|blocked|degraded|security|skip
    hook.duration_ms  f64   wall-clock ms
    hook.error        str   exception str (on failure)
    hook.mode         str   sequential|parallel

Metrics
-------
    agenthooks.hook.executions      Counter     {hook.name, hook.impl, hook.status}
    agenthooks.hook.duration_ms     Histogram   {hook.name, hook.impl}
    agenthooks.hook.errors          Counter     {hook.name, hook.impl}
    agenthooks.hook.timeouts        Counter     {hook.name}
    agenthooks.hook.blocked         Counter     {hook.name, hook.impl}

Usage
-----
Zero-config (automatic):
    The executor uses get_tracer() / get_meter() from this module.
    If opentelemetry-api is installed those objects are live. Otherwise
    they are no-ops — zero overhead.

Explicit SDK setup (application code):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    # agenthooks picks it up automatically — no further config needed.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agenthooks.core.context import HookContext

# ── Logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger("agenthooks")


class _TraceAwareFormatter(logging.Formatter):
    """Injects trace_id/span_id into every log record if available."""

    def format(self, record: logging.LogRecord) -> str:
        # Pull from OTel context if SDK present
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)
        if trace_id is None:
            try:
                from opentelemetry import trace as otel_trace
                span = otel_trace.get_current_span()
                ctx = span.get_span_context()
                if ctx.is_valid:
                    trace_id = format(ctx.trace_id, "032x")
                    span_id = format(ctx.span_id, "016x")
            except ImportError:
                pass
        if trace_id:
            record.trace_id = trace_id
            record.span_id = span_id or "0" * 16
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        return super().format(record)


def configure_logging(
    level: int = logging.INFO,
    fmt: str = "%(asctime)s %(levelname)s [%(name)s] trace_id=%(trace_id)s span_id=%(span_id)s %(message)s",
) -> None:
    """Configure agenthooks logger with trace-correlated structured output.
    Call once at application startup, or configure your own handler — this
    is purely a convenience helper."""
    handler = logging.StreamHandler()
    handler.setFormatter(_TraceAwareFormatter(fmt))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


# ── Tracing ──────────────────────────────────────────────────────────────────

_INSTRUMENTATION_NAME = "agenthooks"
_INSTRUMENTATION_VERSION = "0.1.0"

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import SpanKind, StatusCode

    def get_tracer():
        return _otel_trace.get_tracer(_INSTRUMENTATION_NAME, _INSTRUMENTATION_VERSION)

    _OTEL_TRACING = True

except ImportError:
    _OTEL_TRACING = False
    SpanKind = None  # type: ignore[misc]
    StatusCode = None  # type: ignore[misc]

    def get_tracer():  # type: ignore[misc]
        return _NoopTracer()


class _NoopSpan:
    """Zero-allocation noop span used when OTel SDK is absent."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def set_attribute(self, *_): pass
    def set_status(self, *_): pass
    def record_exception(self, *_): pass
    def add_event(self, *_): pass
    def end(self): pass
    is_recording = False


class _NoopTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoopSpan()

    def start_span(self, name, **kwargs):
        return _NoopSpan()


@contextmanager
def hook_span(
    hookpoint_name: str,
    impl_name: str,
    ctx: HookContext,
    mode: str = "sequential",
) -> Generator[Any, None, None]:
    """Context manager that wraps one hook impl execution in an OTel span.

    Sets standard hook.* attributes and records exceptions on failure.
    When OTel SDK is absent this is a zero-cost no-op.
    """
    tracer = get_tracer()

    span_kwargs: dict[str, Any] = {}
    if _OTEL_TRACING:
        span_kwargs["kind"] = SpanKind.INTERNAL  # type: ignore[attr-defined]

    span_name = f"hook {hookpoint_name}/{impl_name}"
    with tracer.start_as_current_span(span_name, **span_kwargs) as span:
        span.set_attribute("hook.name", hookpoint_name)
        span.set_attribute("hook.impl", impl_name)
        span.set_attribute("hook.mode", mode)
        span.set_attribute("hook.tenant_id", ctx.tenant_id or "")
        span.set_attribute("hook.session_id", ctx.session_id)
        span.set_attribute("hook.trace_id", ctx.trace_id)
        span.set_attribute("hook.turn", ctx.turn)
        yield span


# ── Metrics ──────────────────────────────────────────────────────────────────

try:
    from opentelemetry import metrics as _otel_metrics

    def get_meter():
        return _otel_metrics.get_meter(_INSTRUMENTATION_NAME, _INSTRUMENTATION_VERSION)

    _OTEL_METRICS = True

except ImportError:
    _OTEL_METRICS = False

    def get_meter():  # type: ignore[misc]
        return _InProcessMeter()


class _InProcessCounter:
    """Minimal in-process counter for use without the OTel SDK."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._counts: dict[tuple, int] = {}

    def add(self, amount: int = 1, attributes: dict | None = None) -> None:
        key = tuple(sorted((attributes or {}).items()))
        self._counts[key] = self._counts.get(key, 0) + amount

    def get(self, attributes: dict | None = None) -> int:
        key = tuple(sorted((attributes or {}).items()))
        return self._counts.get(key, 0)

    def total(self) -> int:
        return sum(self._counts.values())


class _InProcessHistogram:
    """Minimal in-process histogram bucket for use without the OTel SDK."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._observations: list[float] = []

    def record(self, value: float, attributes: dict | None = None) -> None:
        self._observations.append(value)

    @property
    def count(self) -> int:
        return len(self._observations)

    @property
    def sum(self) -> float:
        return sum(self._observations)

    @property
    def mean(self) -> float:
        return self.sum / self.count if self.count else 0.0

    @property
    def p95(self) -> float:
        if not self._observations:
            return 0.0
        s = sorted(self._observations)
        idx = max(0, int(len(s) * 0.95) - 1)
        return s[idx]


class _InProcessMeter:
    """In-process meter — accumulates metrics accessible via .get_counter() etc.
    Useful in tests and single-process deployments without the OTel SDK."""

    def __init__(self) -> None:
        self._counters: dict[str, _InProcessCounter] = {}
        self._histograms: dict[str, _InProcessHistogram] = {}

    def create_counter(self, name: str, **_kwargs) -> _InProcessCounter:
        if name not in self._counters:
            self._counters[name] = _InProcessCounter(name)
        return self._counters[name]

    def create_histogram(self, name: str, **_kwargs) -> _InProcessHistogram:
        if name not in self._histograms:
            self._histograms[name] = _InProcessHistogram(name)
        return self._histograms[name]

    def get_counter(self, name: str) -> _InProcessCounter | None:
        return self._counters.get(name)

    def get_histogram(self, name: str) -> _InProcessHistogram | None:
        return self._histograms.get(name)


# ── Instrument Registry (singleton metrics) ──────────────────────────────────

class _Instruments:
    """Lazily initialised metric instruments. One instance per process."""

    def __init__(self) -> None:
        self._meter: Any = None
        self._executions: Any = None
        self._duration: Any = None
        self._errors: Any = None
        self._timeouts: Any = None
        self._blocked: Any = None

    def _init(self) -> None:
        if self._meter is not None:
            return
        self._meter = get_meter()
        self._executions = self._meter.create_counter(
            "agenthooks.hook.executions",
            description="Total hook impl executions by status",
        )
        self._duration = self._meter.create_histogram(
            "agenthooks.hook.duration_ms",
            unit="ms",
            description="Hook impl wall-clock latency",
        )
        self._errors = self._meter.create_counter(
            "agenthooks.hook.errors",
            description="Hook impl error count",
        )
        self._timeouts = self._meter.create_counter(
            "agenthooks.hook.timeouts",
            description="Hook impl timeout count",
        )
        self._blocked = self._meter.create_counter(
            "agenthooks.hook.blocked",
            description="Hook pipeline blocked count",
        )

    def record(
        self,
        hookpoint_name: str,
        impl_name: str,
        status: str,
        duration_ms: float,
    ) -> None:
        self._init()
        attrs = {"hook.name": hookpoint_name, "hook.impl": impl_name, "hook.status": status}
        self._executions.add(1, attrs)
        self._duration.record(duration_ms, {"hook.name": hookpoint_name, "hook.impl": impl_name})
        if status == "error":
            self._errors.add(1, {"hook.name": hookpoint_name, "hook.impl": impl_name})
        elif status == "timeout":
            self._timeouts.add(1, {"hook.name": hookpoint_name})
        elif status == "blocked":
            self._blocked.add(1, {"hook.name": hookpoint_name, "hook.impl": impl_name})

    @property
    def meter(self):
        self._init()
        return self._meter


_instruments = _Instruments()


def record_metric(
    hookpoint_name: str,
    impl_name: str,
    status: str,
    duration_ms: float,
) -> None:
    """Record hook execution metrics. Called automatically by the executor."""
    _instruments.record(hookpoint_name, impl_name, status, duration_ms)


def get_instruments() -> _Instruments:
    """Access the singleton instruments object — useful in tests to assert counts."""
    _instruments._init()
    return _instruments
