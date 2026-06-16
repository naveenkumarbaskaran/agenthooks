"""Built-in pattern decorators — zero-boilerplate hooks for common enterprise needs.

Each decorator wraps a hook function to add a behaviour before delegating
to the wrapped function. Decorators compose (stack bottom-up).

All decorators emit OTel span events and log structured messages so their
activity appears in traces alongside the hook they decorate.

Usage::

    @inject(plant="1000", fiscal_year=lambda ctx: erp.get_fy(ctx.tenant_id))
    @block_if(lambda ctx: not authz.allowed(ctx.tenant_id), reason="Not authorised")
    @redact("api_key", "password")
    async def my_hook(ctx: HookContext) -> HookContext:
        return ctx
"""

from __future__ import annotations

import functools
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked

logger = logging.getLogger("agenthooks.patterns")


def inject(**fields: Any) -> Callable:
    """Enrich ctx.metadata with static values or callables resolved at runtime.

    Values may be:
    - A literal scalar  → injected as-is
    - A callable(ctx)   → called with the current context; return value is injected

    Example::

        @inject(plant="1000", cost_center=lambda ctx: erp.get_cc(ctx.tenant_id))
        async def my_hook(ctx): return ctx
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            for key, value in fields.items():
                resolved = value(ctx) if callable(value) else value
                ctx = ctx.enrich(key, resolved)
                logger.debug("inject: key=%s hookpoint=%s tenant=%s", key, getattr(ctx, "span_id", ""), ctx.tenant_id)
            return await fn(ctx)
        return wrapper
    return decorator


def block_if(condition: Callable[[HookContext], bool], *, reason: str = "Blocked") -> Callable:
    """Raise HookBlocked before the hook body if condition(ctx) is True.

    Example::

        @block_if(lambda ctx: quota.exceeded(ctx.tenant_id), reason="Quota exceeded")
        async def my_hook(ctx): return ctx
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            if condition(ctx):
                logger.info(
                    "block_if: blocked tenant=%s reason=%s impl=%s",
                    ctx.tenant_id, reason, fn.__name__,
                )
                raise HookBlocked(reason)
            return await fn(ctx)
        return wrapper
    return decorator


def redact(*fields: str) -> Callable:
    """Mark fields as redacted in audit logs and OTel before calling the hook body.

    The field values themselves are NOT removed from the context — hooks can
    still read them. They are only flagged so the audit trail and log formatters
    replace them with [REDACTED].

    Example::

        @redact("api_key", "password", "bearer_token")
        async def my_hook(ctx): return ctx
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            ctx = ctx.redact(*fields)
            return await fn(ctx)
        return wrapper
    return decorator


def rate_limit(
    *,
    per: str = "tenant",
    limit: int = 100,
    window_s: int = 60,
    on_exceeded: str = "block",
) -> Callable:
    """In-memory sliding-window rate limiter.

    per        — "tenant" uses ctx.tenant_id; "session" uses ctx.session_id
    limit      — max calls allowed in window_s seconds
    window_s   — rolling window in seconds
    on_exceeded — "block" raises HookBlocked; "degrade" returns ctx unchanged

    For production multi-process deployments, replace with a Redis-backed
    implementation. This in-memory version is per-process.

    Example::

        @rate_limit(per="tenant", limit=100, window_s=60, on_exceeded="block")
        async def my_hook(ctx): return ctx
    """
    # Each decorator invocation gets its own independent counter dict
    _windows: dict[str, list[float]] = defaultdict(list)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            key = ctx.tenant_id if per == "tenant" else ctx.session_id
            now = time.monotonic()
            # Evict timestamps outside the rolling window
            _windows[key] = [t for t in _windows[key] if now - t < window_s]
            if len(_windows[key]) >= limit:
                logger.warning(
                    "rate_limit: exceeded key=%s limit=%d window_s=%d impl=%s",
                    key, limit, window_s, fn.__name__,
                )
                if on_exceeded == "block":
                    raise HookBlocked(
                        f"Rate limit exceeded: {limit} calls per {window_s}s for {per}={key}"
                    )
                return ctx  # degrade — pass through silently
            _windows[key].append(now)
            return await fn(ctx)
        return wrapper
    return decorator


def require_tenant(*allowed: str) -> Callable:
    """Block execution if ctx.tenant_id is not in the allowed set.

    Example::

        @require_tenant("ACME", "SIEMENS")
        async def my_hook(ctx): return ctx
    """
    allowed_set = frozenset(allowed)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            if ctx.tenant_id not in allowed_set:
                raise HookBlocked(
                    f"Hook '{fn.__name__}' is restricted to tenants {sorted(allowed_set)}, "
                    f"got '{ctx.tenant_id}'"
                )
            return await fn(ctx)
        return wrapper
    return decorator


def retry(*, max_attempts: int = 3, backoff_ms: int = 100) -> Callable:
    """Retry the hook body on exception, with exponential backoff.

    Only retries on generic Exception — HookBlocked and HookSkip propagate
    immediately without retrying.

    Example::

        @retry(max_attempts=3, backoff_ms=100)
        async def my_hook(ctx): return await external_service.enrich(ctx)
    """
    import asyncio

    from agenthooks.core.exceptions import HookBlocked, HookSkip

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx: HookContext) -> HookContext:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(ctx)
                except (HookBlocked, HookSkip):
                    raise
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        delay = (backoff_ms * (2 ** (attempt - 1))) / 1000
                        logger.warning(
                            "retry: attempt=%d/%d impl=%s error=%s backoff=%.1fs",
                            attempt, max_attempts, fn.__name__, exc, delay,
                        )
                        await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
