# Hook Execution Flow

This document traces a single hook pipeline execution from start to finish.

---

## Setup Phase (startup, once)

```
Agent author writes:

    class MyAgent(HookAgent):
        before_call = hookpoint("before_call", mode="multi")

    This creates a HookPointDescriptor on the class.
    It has no registries yet.


Customer writes:

    registry = HookRegistry()

    @registry.implement("before_call",
        filter={"tenant": "ACME"},
        order=10,
        timeout_ms=200,
        fallback=True,
    )
    async def inject_context(ctx: HookContext) -> HookContext:
        return ctx.enrich("plant", "1000")

    This stores an ImplRegistration in registry._impls["before_call"].


At deploy time:

    agent = MyAgent(registries=[registry])

    HookAgent.__init__ calls _bind_registries():
        For each HookPointDescriptor on the class,
        creates a per-instance copy with the attached registries.
        Stores it as an instance attribute (shadows the class attribute).
```

---

## Request Phase (per call)

```
1. Agent calls hookpoint.run(ctx):

    ctx = HookContext.new(session_id="s1", tenant_id="ACME", query="...")
    async with self.before_call.run(ctx) as ctx:
        ...


2. HookPointDescriptor._get_impls(ctx):

    For each registry in self._registries:
        registry.get_impls("before_call", ctx)
            └─ filter: {"tenant": "ACME"} matches ctx.tenant_id="ACME" ✓
            └─ returns [ImplRegistration(fn=inject_context, order=10, ...)]

    All results merged and sorted by order.
    Result: [inject_context_reg]


3. SequentialExecutor (default, no parallel flag):

    for reg in [inject_context_reg]:
        _run_one("before_call", reg, ctx)


4. _run_one():

    impl_name = "inject_context"
    t0 = time.monotonic()

    with hook_span("before_call", "inject_context", ctx) as span:
    │   span.set_attribute("hook.name", "before_call")
    │   span.set_attribute("hook.impl", "inject_context")
    │   span.set_attribute("hook.tenant_id", "ACME")
    │   span.set_attribute("hook.session_id", "s1")
    │   span.set_attribute("hook.turn", 0)
    │
    ├─ await asyncio.wait_for(inject_context(ctx), timeout=0.2)
    │       inject_context returns ctx.enrich("plant", "1000")
    │       → new HookContext with metadata={"plant": "1000"}
    │
    ├─ duration_ms = (time.monotonic() - t0) * 1000   # e.g. 3.2ms
    │
    ├─ span.set_attribute("hook.status", "ok")
    ├─ span.set_attribute("hook.duration_ms", 3.2)
    │
    ├─ record_metric("before_call", "inject_context", "ok", 3.2)
    │       agenthooks.hook.executions +1  {hook.name=before_call, hook.impl=inject_context, hook.status=ok}
    │       agenthooks.hook.duration_ms record(3.2)  {hook.name=before_call, hook.impl=inject_context}
    │
    └─ audit.record(hookpoint="before_call", impl_name="inject_context",
                    ctx=ctx, status="ok", duration_ms=3.2)
           Writes to ~/.agenthooks/audit.jsonl:
           {"ts": 1750000000.0, "hook.name": "before_call",
            "hook.impl": "inject_context", "hook.status": "ok",
            "hook.duration_ms": 3.2, "hook.tenant_id": "ACME",
            "trace_id": "...", "session_id": "s1", "turn": 0}

    Returns (enriched_ctx, "ok")


5. SequentialExecutor returns enriched_ctx:
    ctx.metadata == {"plant": "1000"}


6. HookPointDescriptor.run() yields enriched_ctx.

7. Agent body executes with enriched context:

    async with self.before_call.run(ctx) as ctx:
        print(ctx.metadata["plant"])  # "1000"
```

---

## Failure Paths

### Timeout

```
    asyncio.wait_for(...) raises asyncio.TimeoutError after timeout_ms

    _run_one catches TimeoutError:
        record_metric(..., "timeout", duration_ms)
        span.set_attribute("hook.status", "timeout")
        audit.record(..., status="timeout", error="timed out after 200ms")
        logger.warning("hook timeout: ...")
        if fallback=True:
            return (original_ctx, "timeout")   ← ctx unchanged, pipeline continues
        else:
            raise HookTimeout(...)             ← propagates to agent
```

### Error

```
    impl raises Exception("CRM unavailable")

    _run_one catches Exception:
        record_metric(..., "error", duration_ms)
        span.set_attribute("hook.status", "error")
        span.record_exception(exc)
        audit.record(..., status="error", error="CRM unavailable")
        logger.error("hook error: ...")
        if fallback=True:
            return (original_ctx, "error")     ← ctx unchanged, pipeline continues
        else:
            raise                              ← propagates to agent
```

### Blocked

```
    impl calls ctx.block("Requires VP approval")
    → raises HookBlocked("Requires VP approval")

    _run_one catches HookBlocked:
        record_metric(..., "blocked", duration_ms)
        span.set_attribute("hook.status", "blocked")
        span.set_attribute("hook.error", "Requires VP approval")
        audit.record(..., status="blocked", error="Requires VP approval")
        raise HookBlocked  ← always propagates — controlled stop

    HookBlocked propagates through SequentialExecutor → HookPointDescriptor → agent body.
    Agent catches it and returns a user-facing message.
```

### Skip

```
    impl calls ctx.skip()
    → raises HookSkip

    _run_one catches HookSkip:
        record_metric(..., "skip", duration_ms)
        span.set_attribute("hook.status", "skip")
        raise HookSkip

    SequentialExecutor catches HookSkip:
        break  ← remaining impls in this pipeline are not called
        return current ctx
```

---

## Parallel Execution Path

When `parallel=True` on any impl, or on the `hookpoint()` declaration:

```
    ParallelExecutor.run():

    tasks = [_run_one(reg, ctx) for reg in impls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    All impls receive the SAME input ctx (no chaining between them).

    Merge: take metadata from all "ok" results, last-write-wins on key conflicts.
    Return merged ctx.

    Use case: independent enrichment sources that don't need to see each other's output.
    e.g. fetch user profile AND fetch org config AND fetch compliance flags — all in parallel.
```
