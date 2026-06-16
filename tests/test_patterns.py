import pytest

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked
from agenthooks.patterns import block_if, inject, rate_limit, redact, require_tenant, retry


def make_ctx(tenant_id="acme") -> HookContext:
    return HookContext.new(session_id="s1", tenant_id=tenant_id)


# ── inject ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inject_static_value():
    @inject(plant="1000", fiscal_year="2026")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = await my_hook(make_ctx())
    assert ctx.metadata["plant"] == "1000"
    assert ctx.metadata["fiscal_year"] == "2026"


@pytest.mark.asyncio
async def test_inject_callable():
    @inject(plant=lambda ctx: f"plant_{ctx.tenant_id}")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = await my_hook(make_ctx(tenant_id="acme"))
    assert ctx.metadata["plant"] == "plant_acme"


@pytest.mark.asyncio
async def test_inject_multiple_callables():
    @inject(
        plant=lambda ctx: ctx.tenant_id.upper(),
        flag=lambda ctx: len(ctx.tenant_id),
    )
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = await my_hook(make_ctx(tenant_id="test"))
    assert ctx.metadata["plant"] == "TEST"
    assert ctx.metadata["flag"] == 4


# ── block_if ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_block_if_blocks_when_condition_true():
    @block_if(lambda ctx: ctx.tenant_id == "blocked", reason="Tenant is blocked")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    with pytest.raises(HookBlocked, match="Tenant is blocked"):
        await my_hook(make_ctx(tenant_id="blocked"))


@pytest.mark.asyncio
async def test_block_if_passes_when_condition_false():
    @block_if(lambda ctx: ctx.tenant_id == "blocked", reason="Tenant is blocked")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx.enrich("ran", True)

    ctx = await my_hook(make_ctx(tenant_id="allowed"))
    assert ctx.metadata["ran"] is True


# ── redact ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redact_marks_fields():
    @redact("api_key", "password")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = await my_hook(make_ctx())
    assert "api_key" in ctx.metadata["__redacted__"]
    assert "password" in ctx.metadata["__redacted__"]


@pytest.mark.asyncio
async def test_redact_values_still_accessible():
    ctx = make_ctx()
    ctx = ctx.enrich("api_key", "secret-abc")

    @redact("api_key")
    async def my_hook(c: HookContext) -> HookContext:
        # Hook body can still read the value
        assert c.metadata["api_key"] == "secret-abc"
        return c

    await my_hook(ctx)


# ── rate_limit ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit():
    @rate_limit(per="tenant", limit=3, window_s=60)
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx.enrich("ran", True)

    ctx = make_ctx(tenant_id="limited_tenant_a")
    for _ in range(3):
        result = await my_hook(ctx)
    assert result.metadata["ran"] is True


@pytest.mark.asyncio
async def test_rate_limit_blocks_when_exceeded():
    @rate_limit(per="tenant", limit=2, window_s=60, on_exceeded="block")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx(tenant_id="limited_tenant_b")
    await my_hook(ctx)
    await my_hook(ctx)
    with pytest.raises(HookBlocked, match="Rate limit exceeded"):
        await my_hook(ctx)


@pytest.mark.asyncio
async def test_rate_limit_degrades_silently():
    @rate_limit(per="tenant", limit=1, window_s=60, on_exceeded="degrade")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx.enrich("ran", True)

    ctx = make_ctx(tenant_id="limited_tenant_c")
    await my_hook(ctx)
    # Second call — over limit, degrades (returns ctx without raising)
    result = await my_hook(ctx)
    assert result is not None


# ── require_tenant ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_tenant_allows_matching():
    @require_tenant("ACME", "SIEMENS")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx.enrich("ok", True)

    ctx = await my_hook(make_ctx(tenant_id="ACME"))
    assert ctx.metadata["ok"] is True


@pytest.mark.asyncio
async def test_require_tenant_blocks_non_matching():
    @require_tenant("ACME", "SIEMENS")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx

    with pytest.raises(HookBlocked, match="restricted to tenants"):
        await my_hook(make_ctx(tenant_id="EVIL_CORP"))


# ── retry ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    calls = []

    @retry(max_attempts=3, backoff_ms=1)
    async def flaky(ctx: HookContext) -> HookContext:
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("transient")
        return ctx.enrich("calls", len(calls))

    ctx = await flaky(make_ctx())
    assert len(calls) == 2
    assert ctx.metadata["calls"] == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    @retry(max_attempts=2, backoff_ms=1)
    async def always_fails(ctx: HookContext) -> HookContext:
        raise OSError("always down")

    with pytest.raises(IOError, match="always down"):
        await always_fails(make_ctx())


@pytest.mark.asyncio
async def test_retry_does_not_retry_hook_blocked():
    calls = []

    @retry(max_attempts=3, backoff_ms=1)
    async def blocker(ctx: HookContext) -> HookContext:
        calls.append(1)
        raise HookBlocked("intentional")

    with pytest.raises(HookBlocked):
        await blocker(make_ctx())
    assert len(calls) == 1  # no retries on HookBlocked


# ── Decorator composition ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_composed_decorators():
    @inject(plant="1000")
    @block_if(lambda ctx: ctx.tenant_id == "evil", reason="Not allowed")
    @redact("api_key")
    async def pipeline_hook(ctx: HookContext) -> HookContext:
        return ctx

    ctx = make_ctx(tenant_id="acme")
    result = await pipeline_hook(ctx)
    assert result.metadata["plant"] == "1000"
    assert "api_key" in result.metadata["__redacted__"]
