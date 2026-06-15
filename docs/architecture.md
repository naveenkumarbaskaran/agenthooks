# Architecture

## Overview

agenthooks is a three-layer system. Each layer has one responsibility and communicates through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Agent Layer                                                        │
│  HookAgent · HookWrapper                                            │
│  Declares hook points. Attaches registries. Runs the pipeline.      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ hookpoint().run(ctx)
┌─────────────────────────────▼───────────────────────────────────────┐
│  Execution Layer                                                    │
│  HookPointDescriptor · SequentialExecutor · ParallelExecutor        │
│  Resolves implementations. Enforces timeout + fallback. Emits       │
│  OTel spans and metrics. Writes audit entries.                      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ ImplRegistration list
┌─────────────────────────────▼───────────────────────────────────────┐
│  Registry Layer                                                     │
│  HookRegistry · InMemoryStore                                       │
│  Stores implementations. Filters by context. Returns sorted list.  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Data Model

### HookContext

The single data object flowing through every hook pipeline. It is immutable — every method returns a new copy.

```
HookContext
├── Sealed (read-only for hooks)
│   ├── session_id     — unique session identifier
│   ├── tenant_id      — customer/tenant identifier
│   ├── trace_id       — OTel-compatible trace identifier
│   ├── span_id        — OTel-compatible span identifier
│   ├── turn           — turn counter within the session
│   └── timestamp      — Unix epoch at context creation
│
└── Mutable (hooks can replace these)
    ├── query          — the user's input
    ├── tool_name      — the tool being called
    ├── tool_inputs    — inputs to the tool
    ├── tool_result    — result from the tool
    ├── llm_response   — response from the LLM
    ├── error          — error if one occurred
    └── metadata       — enrichment bag (arbitrary key-value)
```

Sealed fields enforce the security boundary. A hook implementation that attempts to write `tenant_id` raises `HookSecurityError` immediately.

### ImplRegistration

Metadata stored alongside each hook function at registration time:

| Field | Default | Purpose |
|---|---|---|
| `hookpoint` | — | name of the hook point |
| `mode` | `multi` | `single` (only one allowed) or `multi` |
| `filter` | `{}` | context conditions that must match |
| `order` | `100` | execution order (ascending) |
| `timeout_ms` | `500` | hard wall-clock budget |
| `fallback` | `True` | degrade on timeout/error if True, raise if False |
| `on_error` | `degrade` | `degrade`, `block`, or `retry` |
| `contract_version` | `None` | semver for API compatibility checks |
| `parallel` | `False` | run concurrently with other impls |

---

## Execution Flow

```
hookpoint.run(ctx)
    │
    ├─ get_impls(hookpoint_name, ctx)
    │      └─ for each registry: filter by context conditions → sort by order
    │
    ├─ if parallel=True or any(impl.parallel):
    │      ParallelExecutor.run()
    │          └─ asyncio.gather(*[_run_one(impl, ctx) for impl in impls])
    │          └─ merge metadata from all "ok" results
    │
    └─ else:
           SequentialExecutor.run()
               └─ for impl in impls:
                      _run_one(impl, ctx)
                          ├─ hook_span(hookpoint, impl, ctx)   ← OTel span
                          ├─ asyncio.wait_for(impl.fn(ctx), timeout_ms/1000)
                          ├─ record_metric(status, duration_ms)
                          ├─ audit.record(...)
                          ├─ on TimeoutError → degrade (if fallback=True)
                          ├─ on HookBlocked  → propagate (always)
                          ├─ on HookSkip     → break loop
                          └─ on Exception    → degrade (if fallback=True)
```

---

## HookRegistry Filter Evaluation

Filters are evaluated by the executor — hook code cannot bypass them.

| Filter key | Maps to |
|---|---|
| `tenant` | `ctx.tenant_id` |
| `tool_name` | `ctx.tool_name` |
| any other key | `ctx.metadata[key]` |

All conditions in a filter dict must match (logical AND). An empty filter `{}` matches all contexts.

---

## Observability Architecture

```
_run_one()
    │
    ├─ hook_span(hookpoint, impl, ctx)
    │      └─ OTel Tracer.start_as_current_span()
    │             attributes: hook.name, hook.impl, hook.tenant_id,
    │                         hook.status, hook.duration_ms
    │             parent: active OTel span (from application tracer)
    │
    ├─ record_metric(hookpoint, impl, status, duration_ms)
    │      └─ _Instruments (singleton)
    │             agenthooks.hook.executions  → Counter
    │             agenthooks.hook.duration_ms → Histogram
    │             agenthooks.hook.errors      → Counter  (on error)
    │             agenthooks.hook.timeouts    → Counter  (on timeout)
    │             agenthooks.hook.blocked     → Counter  (on blocked)
    │
    └─ audit.record(hookpoint, impl, ctx, status, duration_ms)
           └─ AuditTrail → append JSONL line
                  fields: ts, hook.name, hook.impl, hook.status,
                          hook.duration_ms, trace_id, session_id,
                          hook.tenant_id, turn, hook.metadata (redacted)
```

When `opentelemetry-api` is not installed, `hook_span()` returns a `_NoopSpan` (zero allocation) and `get_meter()` returns `_InProcessMeter` (in-process counters, readable in tests).

---

## Design Invariants

1. **Hook failure never crashes the agent.** `fallback=True` (default) means every timeout and exception is caught, logged, metered, and audited — the pipeline continues.

2. **Sealed fields are enforced by the context, not by convention.** `ctx.replace("tenant_id", ...)` raises `HookSecurityError` at call time.

3. **Audit trail is always on.** `get_default_audit()` returns a module-level `AuditTrail` instance. There is no `audit=False` flag.

4. **Filter evaluation happens in the executor, not in hook code.** A hook function never sees a call for a tenant it was not registered for.

5. **OTel is opt-in, fallback is automatic.** If the SDK is absent, all tracer and meter calls are no-ops with zero overhead. The library never raises `ImportError` at runtime.
