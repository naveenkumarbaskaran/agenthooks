# Security Model

## Threat Model

agenthooks sits between an agent's business logic and customer-supplied hook code. The threat model assumes:

- **The agent author is trusted.** They declare hook points and ship the agent binary.
- **Hook implementations are partially trusted.** They are customer code — they may contain bugs, slow external calls, or deliberate misbehaviour (e.g. prompt injection via enriched fields).
- **The context is the attack surface.** Hooks can enrich `metadata` and replace mutable fields like `query`. A malicious hook could inject content designed to manipulate the LLM.

---

## Controls

### Sealed Fields

Six fields on `HookContext` are read-only for hook implementations:

```python
_SEALED_FIELDS = frozenset({
    "session_id", "tenant_id", "trace_id", "span_id", "turn", "timestamp"
})
```

Any call to `ctx.replace("tenant_id", ...)` raises `HookSecurityError` immediately. This prevents hooks from:
- Impersonating another tenant
- Forging trace/audit identifiers
- Manipulating the turn counter

### Prompt Injection Scanning

`injection_scan(query)` runs against any hook-modified `ctx.query` before it reaches the LLM. It detects patterns including:

| Pattern | Example |
|---|---|
| Role override | `ignore previous instructions` |
| Script injection | `<script>`, `javascript:` |
| Role injection markers | `[[system]]`, `[[user]]` |
| Instruction replacement | `new instructions:` |
| Context discard | `disregard all previous` |

Returns a description string on detection, `None` if clean. The executor calls this automatically when `ctx.query` is modified.

### Tenant Isolation

Filter conditions are evaluated by the executor — not by hook code. A hook registered with `filter={"tenant": "ACME"}` will never be called for a context where `tenant_id != "ACME"`. There is no way for hook code to opt out of this filtering.

Multiple customer registries can coexist on the same agent. Each registry's hooks are isolated by filter. Hooks in one registry cannot read or modify the registry of another.

### Redaction

`ctx.redact("api_key", "password")` adds field names to `ctx.metadata["__redacted__"]`. The executor and audit trail check this list and surface those fields as `[REDACTED]` in:

- Audit JSONL entries
- OTel span attributes
- Structured log output

The actual values remain accessible within hook code (hooks may need to use them). Redaction is a logging/observability boundary, not a data-access boundary.

### Audit Trail Invariant

The audit trail cannot be disabled. `get_default_audit()` always returns a live `AuditTrail` instance. There is no `audit=False` configuration flag.

Every hook execution event — including timeouts, errors, blocked calls, and skips — writes a JSONL entry with:
- `ts` — Unix epoch timestamp
- `hook.name` / `hook.impl` / `hook.status` — what ran and how it ended
- `trace_id` / `session_id` — correlation with OTel traces and session logs
- `hook.tenant_id` — the tenant whose context was active
- `hook.metadata` — enrichments (with redacted fields replaced)

### Timeout Enforcement

Every hook implementation runs under `asyncio.wait_for(fn(ctx), timeout=timeout_ms/1000)`. A hook that hangs cannot stall the agent indefinitely. The default budget is 500ms per implementation.

When `fallback=True` (default), a timeout degrades the hook and continues the pipeline. When `fallback=False`, a `HookTimeout` is raised and propagates to the agent.

### Recursion Guard

`HookRecursionError` is defined for the case where a hook implementation triggers the same hook point it is running under. The executor tracks active hook names per execution context and raises on re-entry.

---

## Security Checklist for Hook Authors

- Do not construct values from user input that will be injected into `ctx.query` without sanitisation.
- Use `ctx.redact("field_name")` for any field that contains credentials, PII, or tokens.
- Use `@block_if(...)` at the decorator layer rather than raising exceptions from business logic — it produces cleaner audit entries.
- Use `timeout_ms` to set an appropriate budget for external calls. Do not make unbounded network requests inside a hook.
- Never attempt to read `ctx.metadata["__redacted__"]` to discover what fields are sensitive — treat it as an opaque internal list.
