# agenthooks — Design Spec

**Date:** 2026-06-12  
**Status:** Approved  
**Author:** Naveen Kumar Baskaran (EAM SCM Vayu)  
**Inspired by:** SAP BAdI / Enhancement Spot pattern + Joule Agent Hook Architecture  
**Companion library:** `agentlens` (runtime profiler)

---

## Problem

When you deliver an AI agent to a customer, they want to extend it:
- Inject tenant/user context before each LLM call
- Enforce approval workflows before write operations
- Log every action to their own audit system
- Rate limit per user
- Block certain tool calls based on their own policies

Right now, every developer writes this logic **inside** the agent code — tangled with business logic, not reusable, framework-locked. When the customer wants to customise a delivered agent, they need to fork it.

**`agenthooks` solves this by being the BAdI system for AI agents.**

---

## Mental Model — BAdI for AI Agents

```
SAP Classic              →    agenthooks
────────────────────────────────────────────────────
BAdI definition          →    hookpoint("name", schema=..., mode=...)
BAdI implementation      →    @registry.implement("name")
Enhancement spot         →    named hookpoint declared in agent
Filter condition         →    filter={"tenant": "ACME"}
Single-use BAdI          →    mode="single"
Multi-use BAdI           →    mode="multi"
Sort sequence            →    order=N
Fallthrough on error     →    fallback=True (degraded mode)
Multiple active impls    →    multiple @registry.implement on same point
CL_EXITHANDLER           →    HookRegistry.resolve(hookpoint, filter)
```

---

## Design Goals

1. **Non-breaking** — hook failure never crashes the agent (degraded mode always)
2. **Framework-agnostic** — works with LangGraph, raw Anthropic SDK, CrewAI, any Python agent
3. **Zero core dependencies** — `pip install agenthooks` installs nothing else
4. **Type-safe** — schema validated at registration time, not at runtime
5. **BAdI-faithful** — single/multi mode, filter conditions, sort order, multiple impls
6. **Production-grade** — OTel built in, timeouts, circuit breaker, persistent registry

---

## Hook Lifecycle

```
SESSION BEGINS          →    on_session_start
                              ↓
TURN RECEIVED           →    on_before_call(query, ctx)
                              ↓
  TOOL FIRES            →    on_tool_start(tool, inputs, ctx)
  TOOL RETURNS          →    on_tool_end(tool, result, ctx)
                              ↓
TURN COMPLETES          →    on_after_call(response, ctx)
                              ↓
ANY FAILURE             →    on_error(error, ctx)
                              ↓
SESSION ENDS            →    on_session_end(trace, ctx)
```

---

## Public API

### Layer 1 — Agent Builder (defines hook points)

```python
from agenthooks import HookAgent, hookpoint, HookContext
from pydantic import BaseModel

# Define a typed context for a specific hook point
class TecoContext(HookContext):
    order_id: str
    plant: str | None = None
    approved_by: str | None = None

class MaintenanceAgent(HookAgent):

    # Declare enhancement spots — like BAdI definition
    # mode="single"  → only ONE implementation allowed (HookConflict if >1)
    # mode="multi"   → ALL implementations run (default, sequential pipeline)
    # parallel=True  → all impls fire concurrently, results merged
    before_teco  = hookpoint("before_teco",  schema=TecoContext,  mode="single")
    after_teco   = hookpoint("after_teco",   schema=TecoContext,  mode="multi")
    before_call  = hookpoint("before_call",  schema=HookContext,  mode="multi")
    on_tool_use  = hookpoint("on_tool_use",  schema=HookContext,  mode="multi",  parallel=True)
    on_error     = hookpoint("on_error",     schema=HookContext,  mode="multi")

    async def execute_teco(self, order_id: str):
        ctx = TecoContext(order_id=order_id)

        # Hook fires here — all registered impls run sequentially
        async with self.before_teco.run(ctx) as ctx:
            result = await self.sap.set_teco(ctx.order_id)

        async with self.after_teco.run(ctx):
            return result
```

### Layer 2 — Customer / Partner (registers implementations)

```python
from agenthooks import HookRegistry, HookBlocked, HookContext

registry = HookRegistry()

@registry.implement(
    "before_teco",
    filter={"tenant": "ACME_CORP"},    # fires only for ACME tenant
    timeout_ms=300,                    # max time — never blocks agent
    fallback=True,                     # degraded mode on failure
    order=10,                          # sort sequence (lower = first)
    contract_version="1.0",            # validated at registration, not runtime
)
async def acme_approval_check(ctx: TecoContext) -> TecoContext:
    if not acme_erp.is_approved(ctx.order_id):
        raise HookBlocked("Requires manager approval in ACME ERP")
    ctx.approved_by = acme_erp.get_approver(ctx.order_id)
    return ctx  # enriched context flows to next impl

@registry.implement(
    "before_teco",
    filter={"tenant": "ACME_CORP"},
    order=20,                          # runs AFTER approval check
    fallback=True,
)
async def acme_audit_log(ctx: TecoContext) -> TecoContext:
    await audit.log("TECO_ATTEMPT", ctx.model_dump())
    return ctx

# Attach to agent
agent = MaintenanceAgent(registries=[registry])
```

### Layer 3 — External Wrap (for agents you don't own)

```python
from agenthooks import HookWrapper

# Don't own the agent? Wrap it.
raw_agent = build_langgraph_agent()

wrapped = HookWrapper(raw_agent)
wrapped.add_registry(registry)

# Identical interface to original
result = await wrapped.invoke({"query": "TECO order 4002130"})
```

---

## Context Object

```python
from agenthooks import HookContext

class HookContext(BaseModel):
    # Always present
    session_id: str
    tenant_id: str | None = None
    trace_id: str                    # W3C trace context propagation
    span_id: str
    turn: int = 0
    timestamp: float

    # Open enrichment dict — each impl adds to this
    metadata: dict = {}

    # Immutable enrichment — returns new context (never mutates in place)
    def enrich(self, key: str, value) -> "HookContext":
        return self.model_copy(update={"metadata": {**self.metadata, key: value}})

    # Controlled stop — clean error, not a crash
    def block(self, reason: str) -> None:
        raise HookBlocked(reason)
```

Custom contexts extend this:

```python
class TecoContext(HookContext):
    order_id: str
    plant: str | None = None
    approved_by: str | None = None
```

---

## Execution Model

### Sequential (default, `mode="multi"`)

```
before_teco fires:

  impl #1 (order=10, tenant=ACME)  →  ctx_1 = acme_approval(ctx_0)
       ↓ ctx_1
  impl #2 (order=20, tenant=ACME)  →  ctx_2 = acme_audit(ctx_1)
       ↓ ctx_2
  impl #3 (order=10, tenant=SIEMENS, filter miss — skipped)
       ↓ ctx_2
  agent continues with ctx_2
```

### Parallel (`mode="multi"`, `parallel=True`)

```
on_tool_use fires:

  impl #1 ─┐
  impl #2 ─┼─ all run concurrently ─→ merged_ctx = merge(ctx_1, ctx_2, ctx_3)
  impl #3 ─┘
  agent continues with merged_ctx
```

### Single (`mode="single"`)

```
before_teco fires:

  Only one impl registered:  ctx_1 = acme_approval(ctx_0)
  Two impls registered:      raises HookConflict at registration time
```

---

## Error Handling

Three modes per hook implementation:

```python
@registry.implement("before_teco",
    on_error="degrade",   # DEFAULT — log + continue with last good ctx
)

@registry.implement("before_teco",
    on_error="block",     # raise HookBlocked → agent returns clean error message
)

@registry.implement("before_teco",
    on_error="retry",     # retry 3x with exponential backoff, then degrade
    retry_max=3,
    retry_backoff_ms=100,
)
```

`HookBlocked` is a **controlled stop** — the agent catches it and returns a clean message. It is not an exception from the agent's perspective.

All other errors → degrade silently → log → OTel counter incremented.

---

## Timeout Budgets

Pre-hooks and post-hooks have explicit time budgets. If a hook exceeds its budget, the agent continues in degraded mode — never blocked.

```python
# Pre-hook: 100–500ms recommended
@registry.implement("before_call", timeout_ms=300)

# Post-hook: up to 2000ms (response already streaming, delta patches if arrives in time)
@registry.implement("after_call", timeout_ms=1500)

# Global defaults configurable at registry level
registry = HookRegistry(default_timeout_ms=500)
```

---

## Filter Conditions

Hooks fire only when all filter conditions match the current context:

```python
@registry.implement("before_teco",
    filter={
        "tenant": "ACME_CORP",        # ctx.tenant_id == "ACME_CORP"
        "plant": "1000",              # ctx.metadata["plant"] == "1000"
    }
)
```

Filters are evaluated **before** the impl is called — zero overhead for non-matching tenants.

---

## Hook Contract Versioning

Schema contracts are validated at **registration time**, not at runtime:

```python
@registry.implement(
    "before_teco",
    contract_version="1.0",    # must be compatible with hookpoint's declared version
)
async def my_impl(ctx: TecoContext) -> TecoContext: ...

# Hookpoint declares accepted contract versions
before_teco = hookpoint(
    "before_teco",
    schema=TecoContext,
    contract_version=">=1.0,<2.0",    # semver range
)
```

Incompatible contract → `HookContractError` at `registry.implement()` call — never at runtime.

---

## Observability (OTel — built in, no config needed)

Every hook execution emits:

```python
# Spans
span.set_attribute("agenthooks.hookpoint",         "before_teco")
span.set_attribute("agenthooks.impl",              "acme_approval_check")
span.set_attribute("agenthooks.mode",              "single|multi|parallel")
span.set_attribute("agenthooks.status",            "ok|timeout|error|degraded|blocked")
span.set_attribute("agenthooks.tenant",            "ACME_CORP")
span.set_attribute("agenthooks.contract_version",  "1.0")
span.set_attribute("agenthooks.order",             10)

# Metrics
agenthooks.hook.duration_ms          # histogram
agenthooks.hook.errors_total         # counter (by hookpoint, status)
agenthooks.hook.degraded_total       # counter (degraded mode executions)
agenthooks.hook.blocked_total        # counter (HookBlocked raised)
agenthooks.impl.registered_total     # gauge (active implementations)
```

---

## Repo Structure

```
agenthooks/
├── pyproject.toml               # Python >=3.11, hatchling, zero core deps
├── src/agenthooks/
│   ├── __init__.py              # Public API exports only
│   ├── _manager.py              # HookManager facade
│   ├── core/
│   │   ├── hookpoint.py         # hookpoint() descriptor
│   │   ├── context.py           # HookContext (Pydantic base)
│   │   ├── registry.py          # HookRegistry + @implement decorator
│   │   ├── contract.py          # Version validation, schema compat
│   │   └── exceptions.py        # HookBlocked, HookConflict, HookContractError, HookTimeout
│   ├── executor/
│   │   ├── _base.py             # BaseExecutor (Protocol)
│   │   ├── sequential.py        # SequentialExecutor (default)
│   │   ├── parallel.py          # ParallelExecutor (parallel=True)
│   │   └── pipeline.py          # Full pipeline (filter → sort → execute → merge)
│   ├── store/
│   │   ├── _base.py             # HookStore Protocol
│   │   ├── memory.py            # InMemoryStore (default, zero deps)
│   │   └── sqlite.py            # SqliteStore (optional extra)
│   ├── agent/
│   │   ├── base.py              # HookAgent base class
│   │   └── wrapper.py           # HookWrapper (external agent wrap)
│   ├── telemetry/
│   │   └── otel.py              # OTel spans + metrics (optional extra)
│   └── integrations/
│       ├── langchain.py         # LangChain callback bridge (optional)
│       ├── langgraph.py         # LangGraph node wrapper (optional)
│       ├── anthropic.py         # Anthropic SDK wrapper (optional)
│       └── openai.py            # OpenAI Agents SDK wrapper (optional)
├── tests/
│   ├── conftest.py
│   ├── test_hookpoint.py
│   ├── test_registry.py
│   ├── test_executor.py
│   ├── test_contract.py
│   └── test_wrapper.py
├── examples/
│   ├── 01_basic_hooks.py
│   ├── 02_badi_style.py
│   ├── 03_langchain_integration.py
│   ├── 04_sap_tenant_filter.py
│   └── 05_error_recovery.py
└── README.md
```

---

## pyproject.toml (key parts)

```toml
[project]
name = "agenthooks"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []                    # Zero core deps

[project.optional-dependencies]
pydantic = ["pydantic>=2.0"]         # HookContext schema validation
otel = ["opentelemetry-api>=1.20"]   # Observability
sqlite = ["aiosqlite>=0.20"]         # Persistent store
langchain = ["langchain-core>=0.3"]  # LangChain integration
anthropic = ["anthropic>=0.40"]      # Anthropic integration
openai = ["openai>=1.0"]             # OpenAI integration
all = ["agenthooks[pydantic,otel,sqlite,langchain,anthropic,openai]"]

[project.scripts]
agenthooks = "agenthooks.cli:app"    # CLI entry point

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## v1 Scope

**In v1:**
- `hookpoint()` descriptor — single/multi/parallel modes
- `HookRegistry` + `@implement` — filter, order, timeout, fallback, contract_version
- `HookContext` base (Pydantic optional)
- `SequentialExecutor` + `ParallelExecutor`
- `HookAgent` base class + `HookWrapper` for external agents
- `InMemoryStore` (default)
- `HookBlocked`, `HookConflict`, `HookContractError`, `HookTimeout` exceptions
- OTel spans + metrics (optional extra)
- 5 working examples
- Full test suite (pytest)

**Out of v1 (v2):**
- `SqliteStore` persistent registry
- CLI (`agenthooks register`, `list`, `test`, `logs`)
- Streaming response delta patching
- Circuit breaker
- HTTP hook invocation (remote hooks via URL)
- Credential vault for hook auth

---

## What Makes This Different

| Library | What it does | Gap |
|---|---|---|
| LangChain callbacks | Observability callbacks for LangChain only | Framework-locked, no filtering, no contracts |
| OpenAI tracing | Traces for OpenAI SDK only | Vendor-locked, no customer extensibility |
| tokmon | Token cost tracking | Not extensibility — monitoring only |
| agentlens | Tool schema profiling/optimisation | Not extensibility — optimisation only |
| **agenthooks** | BAdI-style customer extensibility for any agent | **This gap** |
