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

---

## Context Object — Full Data Flow Control

This is what every hook implementation receives. Designed so developers can read, enrich, replace, block, or skip — with full control over what flows to the agent.

```python
class HookContext(BaseModel):
    # ── Sealed fields — hooks can READ, never WRITE ──
    session_id:  str   = Field(frozen=True)  # who is talking
    tenant_id:   str   = Field(frozen=True)  # which customer (never spoofable)
    trace_id:    str   = Field(frozen=True)  # W3C distributed trace ID
    span_id:     str   = Field(frozen=True)  # current OTel span
    turn:        int   = Field(frozen=True)  # which turn in the conversation
    timestamp:   float = Field(frozen=True)  # when this hook fired

    # ── Mutable fields — hooks can read AND modify these ──
    query:        str | None = None          # user's message (before_call)
    tool_name:    str | None = None          # tool about to fire (on_tool_start)
    tool_inputs:  dict       = {}            # tool input params (on_tool_start)
    tool_result:  dict | None = None         # tool output (on_tool_end)
    llm_response: str | None = None          # LLM reply text (after_call)
    error:        Exception | None = None    # error that occurred (on_error)

    # ── Enrichment bag — hooks add context here ──
    metadata: dict = {}                      # open dict, flows through all impls

    # ── Control methods ──

    def enrich(self, key: str, value) -> "HookContext":
        """Add data to metadata. Immutable — returns new context."""
        return self.model_copy(update={"metadata": {**self.metadata, key: value}})

    def replace(self, field: str, value) -> "HookContext":
        """Replace a mutable field. Sealed fields raise HookSecurityError."""
        if field in ("session_id", "tenant_id", "trace_id", "span_id", "turn", "timestamp"):
            raise HookSecurityError(f"Field '{field}' is sealed — hooks cannot write it")
        return self.model_copy(update={field: value})

    def redact(self, *fields: str) -> "HookContext":
        """Mark fields as redacted in logs and OTel — value replaced with [REDACTED]."""
        redacted = {**self.metadata, "__redacted__": list(fields)}
        return self.model_copy(update={"metadata": redacted})

    def block(self, reason: str) -> None:
        """Stop execution cleanly — agent gets a clean error message, not a crash."""
        raise HookBlocked(reason)

    def skip(self) -> None:
        """Skip remaining impls on this hookpoint — jump to next hookpoint."""
        raise HookSkip()
```

### What a developer can do at each hookpoint

```python
# ── before_call — query is available, tool hasn't fired yet ──
@registry.implement("before_call")
async def my_hook(ctx: HookContext) -> HookContext:
    # Inject context the agent will see
    ctx = ctx.enrich("plant", erp.get_plant(ctx.tenant_id))
    ctx = ctx.enrich("fiscal_year", "2026")

    # Sanitise the query before LLM sees it
    ctx = ctx.replace("query", security.clean(ctx.query))

    # Block based on business rules
    if quota.exceeded(ctx.tenant_id):
        ctx.block("Daily quota exceeded — try again tomorrow")

    return ctx

# ── on_tool_start — tool is about to fire, inputs visible ──
@registry.implement("on_tool_start",
    filter={"tool_name": "set_orders_to_teco"})
async def approval_gate(ctx: HookContext) -> HookContext:
    order_id = ctx.tool_inputs.get("order_id")

    # Approval gate — controlled stop
    if not approval.is_approved(order_id, ctx.tenant_id):
        ctx.block(f"Order {order_id} requires manager approval before TECO")

    # Enrich tool inputs — add data the tool will receive
    ctx = ctx.replace("tool_inputs", {
        **ctx.tool_inputs,
        "approved_by": approval.get_approver(order_id),
    })
    return ctx

# ── on_tool_end — tool has returned, result visible ──
@registry.implement("on_tool_end",
    filter={"tool_name": "get_maintenance_order"})
async def enrich_result(ctx: HookContext) -> HookContext:
    # Enrich tool result with additional data
    order_id = ctx.tool_result.get("order_id")
    ctx = ctx.replace("tool_result", {
        **ctx.tool_result,
        "sla_status": sla.check(order_id),
        "risk_score": risk.evaluate(ctx.tool_result),
    })
    return ctx

# ── after_call — LLM has responded, response visible ──
@registry.implement("after_call")
async def localise_response(ctx: HookContext) -> HookContext:
    locale = ctx.metadata.get("locale", "en")
    ctx = ctx.replace("llm_response", translate(ctx.llm_response, locale))
    return ctx

# ── on_error — something failed ──
@registry.implement("on_error")
async def alert_and_recover(ctx: HookContext) -> HookContext:
    pagerduty.alert(ctx.error, ctx.session_id, ctx.tenant_id)
    # Return ctx unchanged — agent handles the error its own way
    return ctx

# ── on_session_end — read-only audit ──
@registry.implement("on_session_end")
async def audit_session(ctx: HookContext) -> HookContext:
    await audit_db.write({
        "session_id":  ctx.session_id,
        "tenant_id":   ctx.tenant_id,
        "trace_id":    ctx.trace_id,
        "turns":       ctx.turn,
        "metadata":    ctx.metadata,
    })
    return ctx  # always return ctx unchanged for audit hooks
```

---

## Security Model

### Attack Vectors and Guards

| Attack | How it happens | Guard |
|---|---|---|
| **Tenant spoofing** | Hook writes `ctx.tenant_id` to impersonate another tenant | `tenant_id` is `frozen=True` — `HookSecurityError` if written |
| **Prompt injection via hook** | Hook injects `"Ignore previous instructions"` into `ctx.query` | Every hook-modified `query` is re-scanned by `InjectionGuard` before LLM sees it |
| **Tool input tampering** | Hook changes `tool_inputs` to call a destructive operation | Tool input schema re-validated AFTER hooks run, before tool fires |
| **Data exfiltration** | Hook reads `ctx.tool_result` and POSTs to external server | Hook URL allowlist at `HookRegistry` level; network egress control |
| **Secrets leakage** | Hook logs `ctx` which contains sensitive tool results | `ctx.redact("api_key", "password")` — redacted fields show as `[REDACTED]` |
| **DoS via slow hook** | Hook sleeps 60s, blocks all agent traffic | Hard `timeout_ms` per impl; circuit breaker after 5 consecutive failures |
| **Hook recursion** | Hook calls an agent which triggers the same hook | Max recursion depth = 1; `HookRecursionError` raised |
| **Contract downgrade** | Customer registers hook with old contract after agent ships new one | Semver range enforced at `registry.implement()` — never at runtime |
| **Parallel state leak** | Parallel hooks share mutable state, corrupt each other | Context is immutable copy per impl — parallel impls cannot see each other's writes |
| **Silent privilege escalation** | Hook changes `session_id` to hijack another session | `session_id` is `frozen=True` |
| **Mode conflict** | Two `mode="single"` impls registered — last one silently wins | `HookConflict` raised at registration time, not at runtime |

### Security Guards Built Into the Library

```python
# 1. Sealed fields — frozen at construction, raise HookSecurityError if written
class HookContext(BaseModel):
    session_id: str = Field(frozen=True)
    tenant_id:  str = Field(frozen=True)
    trace_id:   str = Field(frozen=True)

# 2. Injection re-scan on any hook-modified query
# If before_call hook modifies ctx.query, the executor automatically
# re-runs InjectionGuard on the new value before passing to LLM.
# Hooks cannot bypass this — it runs in the executor, not in hook code.

# 3. Tool input re-validation after hooks
# If on_tool_start hook modifies ctx.tool_inputs, the executor validates
# the modified inputs against the tool's declared JSON Schema before calling the tool.

# 4. Hook URL allowlist — remote hooks only from trusted origins
registry = HookRegistry(
    allowed_hook_origins=[
        "https://hooks.acme.com",
        "https://*.trusted-partner.com",
    ]
)
# Local (in-process) hooks bypass this — they're your own code.

# 5. Sensitive field redaction — redacted before logs and OTel
@registry.implement("before_call")
async def my_hook(ctx: HookContext) -> HookContext:
    ctx = ctx.redact("api_key", "password", "token")
    # These fields now appear as [REDACTED] in all traces and logs
    return ctx

# 6. Circuit breaker — auto-disables failing impls
# After 5 consecutive failures, impl is suspended for 60s.
# OTel counter incremented. Logged with impl name and hookpoint.
registry = HookRegistry(
    circuit_breaker=CircuitBreaker(
        failure_threshold=5,
        recovery_seconds=60,
    )
)

# 7. Recursion guard — hooks cannot trigger hooks
# HookExecutor tracks call depth via contextvars.
# Any impl that triggers agent.invoke() which fires the same hookpoint
# raises HookRecursionError immediately.

# 8. Audit trail — every hook execution is permanently recorded
# Even if OTel is not configured, agenthooks writes a local audit log:
# ~/.agenthooks/audit.jsonl (or configurable path)
# Contains: timestamp, hookpoint, impl, tenant_id, status, duration_ms
# Cannot be disabled — this is a security invariant.
```

### What Hooks Are NOT Allowed to Do

Enforced at the executor level — not just documented:

```python
HOOK_FORBIDDEN = [
    "write sealed fields (session_id, tenant_id, trace_id, span_id, turn, timestamp)",
    "call another hookpoint directly (recursion guard)",
    "access other tenants' contexts (isolation enforced by executor)",
    "modify contexts belonging to other sessions",
    "disable or unregister other hooks at runtime",
    "access the raw agent internals (only ctx is passed — agent object never exposed)",
]
```

---

## Extensibility Patterns — Developer Cookbook

These are the patterns developers will reach for most. Each is a first-class citizen in the examples folder.

### Pattern 1 — Tenant Context Injection
```python
# Most common. Every enterprise customer needs this.
@registry.implement("before_call", filter={"tenant": "ACME"})
async def inject_acme_context(ctx: HookContext) -> HookContext:
    profile = await erp.get_user_profile(ctx.tenant_id, ctx.session_id)
    return (ctx
        .enrich("plant",       profile.plant)
        .enrich("cost_center", profile.cost_center)
        .enrich("locale",      profile.locale))
```

### Pattern 2 — Approval Gate on Write Operations
```python
# Stop a destructive tool call until human approves.
@registry.implement("on_tool_start",
    filter={"tool_name": "set_orders_to_teco"},
    mode="single",
    on_error="block")
async def teco_approval(ctx: HookContext) -> HookContext:
    ticket = await approval_system.create_ticket(
        action="TECO",
        order_id=ctx.tool_inputs["order_id"],
        requested_by=ctx.tenant_id,
    )
    if not await approval_system.wait_for_approval(ticket.id, timeout_s=300):
        ctx.block(f"TECO approval denied or timed out (ticket: {ticket.id})")
    return ctx.enrich("approval_ticket", ticket.id)
```

### Pattern 3 — Result Enrichment
```python
# Add domain-specific data to tool results before LLM synthesises them.
@registry.implement("on_tool_end",
    filter={"tool_name": "get_maintenance_order"})
async def enrich_order(ctx: HookContext) -> HookContext:
    order_id = ctx.tool_result["OrderID"]
    return ctx.replace("tool_result", {
        **ctx.tool_result,
        "SLAStatus":  await sla.check(order_id),
        "RiskScore":  await risk.score(order_id),
        "NextAction": await workflow.next_action(order_id),
    })
```

### Pattern 4 — Input Sanitisation + Compliance
```python
# Scrub PII or non-compliant content before it reaches the LLM.
@registry.implement("before_call")
async def gdpr_sanitise(ctx: HookContext) -> HookContext:
    clean_query = pii_scanner.redact(ctx.query)
    if pii_scanner.detected(ctx.query):
        await compliance_log.record("PII_DETECTED", ctx.session_id, ctx.tenant_id)
    return ctx.replace("query", clean_query)
```

### Pattern 5 — Response Localisation
```python
@registry.implement("after_call")
async def localise(ctx: HookContext) -> HookContext:
    locale = ctx.metadata.get("locale", "en")
    if locale != "en":
        return ctx.replace("llm_response",
            await translation_service.translate(ctx.llm_response, locale))
    return ctx
```

### Pattern 6 — Rate Limiting Per Tenant
```python
@registry.implement("before_call", on_error="block")
async def rate_limit(ctx: HookContext) -> HookContext:
    allowed = await rate_limiter.check(ctx.tenant_id)
    if not allowed:
        ctx.block("Rate limit exceeded. Please try again in 60 seconds.")
    return ctx
```

### Pattern 7 — Full Audit Trail
```python
@registry.implement("on_session_end")
async def full_audit(ctx: HookContext) -> HookContext:
    await audit_db.write({
        "session_id":    ctx.session_id,
        "tenant_id":     ctx.tenant_id,
        "trace_id":      ctx.trace_id,
        "turns":         ctx.turn,
        "actions":       ctx.metadata.get("actions", []),
        "tools_called":  ctx.metadata.get("tools_called", []),
        "blocked":       ctx.metadata.get("blocked", False),
    })
    return ctx
```

---

## v1 Scope (updated)

**In v1:**
- `hookpoint()` descriptor — single/multi/parallel modes
- `HookRegistry` + `@implement` — filter, order, timeout, fallback, contract_version, on_error
- `HookContext` — sealed fields, enrich/replace/redact/block/skip methods
- `SequentialExecutor` + `ParallelExecutor`
- Security guards — injection re-scan, tool re-validation, recursion guard, circuit breaker
- Audit trail — local JSONL (always on)
- `HookAgent` base class + `HookWrapper` for external agents
- `InMemoryStore` (default, zero deps)
- `HookBlocked`, `HookSkip`, `HookConflict`, `HookContractError`, `HookTimeout`, `HookSecurityError`, `HookRecursionError`
- OTel spans + metrics (optional extra)
- 7 cookbook examples
- Full test suite (pytest)

**Out of v1 (v2):**
- `SqliteStore` persistent registry
- CLI (`agenthooks register`, `list`, `test`, `logs`)
- Streaming response delta patching
- HTTP hook invocation (remote hooks via URL)
- Credential vault for hook auth
- Hook URL allowlist enforcement (v2 — requires remote invocation)
