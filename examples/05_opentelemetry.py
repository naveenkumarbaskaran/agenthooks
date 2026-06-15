"""05_opentelemetry.py — Production OTel wiring.

agenthooks emits spans, metrics, and trace-correlated logs using the
OpenTelemetry API. When the OTel SDK is configured, every hook execution
appears as a child span under your application's active trace — visible
in Jaeger, Tempo, Zipkin, Datadog APM, Honeycomb, or any OTLP-compatible
backend.

This example shows how to wire the SDK. The agent code is identical to
every other example — observability is automatic.

Install extras:
    pip install agenthooks[otel]
    # or: pip install opentelemetry-sdk opentelemetry-exporter-otlp

Run against a local collector:
    docker run -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one
    python examples/05_opentelemetry.py
    # open http://localhost:16686 and search for service "my-agent"
"""
import asyncio
import logging


def setup_otel():
    """Configure OTel SDK with OTLP gRPC export. Adjust endpoint to match
    your collector (Jaeger, Tempo, OTel Collector, Datadog Agent, etc.)."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        resource = Resource.create({SERVICE_NAME: "my-agent"})
        provider = TracerProvider(resource=resource)

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4317"))
            )
        except ImportError:
            # Fallback: console exporter so you can see spans without a collector
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        print("[otel] TracerProvider configured — spans will be exported")
        return trace.get_tracer("my-agent")

    except ImportError:
        print("[otel] opentelemetry-sdk not installed — using noop tracer")
        return None


def setup_metrics():
    """Configure OTel Metrics SDK."""
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter, PeriodicExportingMetricReader,
        )
        reader = PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=5000)
        metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
        print("[otel] MeterProvider configured — metrics will export every 5s")
    except ImportError:
        print("[otel] opentelemetry-sdk not installed — using in-process metrics")


from agenthooks import (
    HookAgent, hookpoint, HookRegistry, HookContext,
    configure_logging, inject, block_if, rate_limit,
)


class ProductionAgent(HookAgent):
    """A production agent. Every hook execution is automatically traced,
    metered, and audit-logged with no extra code in the agent."""

    before_call = hookpoint("before_call")
    after_call = hookpoint("after_call")

    async def run(self, query: str, tenant_id: str) -> dict:
        ctx = HookContext.new(session_id="sess-prod-1", tenant_id=tenant_id, query=query)

        async with self.before_call.run(ctx) as ctx:
            # Core agent logic runs here — hooks have already enriched ctx
            response = f"Answer for {ctx.tenant_id}: {ctx.query}"

        ctx = ctx.replace("llm_response", response)
        async with self.after_call.run(ctx) as ctx:
            pass

        return {
            "response": response,
            "context": {k: v for k, v in ctx.metadata.items() if not k.startswith("__")},
        }


registry = HookRegistry()


@registry.implement("before_call", order=10)
@rate_limit(per="tenant", limit=1000, window_s=60)
@inject(
    request_id=lambda ctx: f"{ctx.session_id}:{ctx.turn}",
    environment="production",
)
async def standard_enrichment(ctx: HookContext) -> HookContext:
    return ctx


@registry.implement("before_call", filter={"tenant": "ENTERPRISE"}, order=20)
@block_if(lambda ctx: not ctx.query, reason="Empty query not allowed")
@inject(tier="enterprise", sla="99.9")
async def enterprise_enrichment(ctx: HookContext) -> HookContext:
    return ctx


@registry.implement("after_call")
async def response_audit(ctx: HookContext) -> HookContext:
    # In production, ship to your SIEM or compliance system here.
    # The AuditTrail has already written the JSONL entry automatically.
    return ctx


async def main():
    tracer = setup_otel()
    setup_metrics()
    configure_logging(level=logging.INFO)

    agent = ProductionAgent(registries=[registry])

    if tracer:
        # Wrap the agent call in an application-level span.
        # Hook spans appear as children automatically.
        with tracer.start_as_current_span("agent.run") as span:
            span.set_attribute("tenant_id", "ENTERPRISE")
            result = await agent.run("What is our Q3 forecast?", "ENTERPRISE")
    else:
        result = await agent.run("What is our Q3 forecast?", "ENTERPRISE")

    print("\nResult:", result)


if __name__ == "__main__":
    asyncio.run(main())
