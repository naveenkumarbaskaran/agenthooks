"""AuditTrail — permanent append-only hook execution log.

Written as newline-delimited JSON (JSONL). Every hook execution event
(ok, timeout, error, blocked, degraded, security) is recorded — this
cannot be disabled, it is a security invariant.

The file is opened in append mode on each write so it survives process
restarts and is safe for concurrent writers within a single process
(protected by asyncio.Lock). For multi-process deployments, point each
process at its own shard or use the OTel exporter instead.

Semantic conventions follow the agenthooks attribute schema:
    hook.name         — hookpoint name
    hook.impl         — implementation function name
    hook.tenant_id    — tenant from HookContext.tenant_id
    hook.status       — ok | timeout | error | blocked | degraded | security
    hook.duration_ms  — wall-clock time in milliseconds (rounded to 2dp)
    hook.error        — exception message (only on error/blocked)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from agenthooks.core.context import HookContext

_DEFAULT_PATH = os.path.expanduser("~/.agenthooks/audit.jsonl")

# Valid status values — mirrors OTel span status codes extended for hooks
AUDIT_STATUS = frozenset({"ok", "timeout", "error", "blocked", "degraded", "security", "skip"})


class AuditTrail:
    """Append-only JSONL audit log for hook executions.

    Usage::

        audit = AuditTrail()                        # writes to ~/.agenthooks/audit.jsonl
        audit = AuditTrail(path="/var/log/hooks.jsonl")
        await audit.record(hookpoint="before_call", impl_name="acme_inject",
                           ctx=ctx, status="ok", duration_ms=12.3)
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def record(
        self,
        *,
        hookpoint: str,
        impl_name: str,
        ctx: HookContext,
        status: str,
        duration_ms: float,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one audit entry. Never raises — audit failures are logged
        to stderr but must not crash the hook pipeline."""
        if status not in AUDIT_STATUS:
            status = "error"

        # Redacted fields must not appear in audit log values
        redacted = set(ctx.metadata.get("__redacted__", []))

        entry: dict[str, Any] = {
            "ts": time.time(),
            # OTel-style attribute names
            "hook.name": hookpoint,
            "hook.impl": impl_name,
            "hook.status": status,
            "hook.duration_ms": round(duration_ms, 2),
            # Tracing correlation
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "session_id": ctx.session_id,
            "hook.tenant_id": ctx.tenant_id,
            "turn": ctx.turn,
        }

        if error:
            entry["hook.error"] = error

        # Surface safe metadata keys (skip redacted, skip internal __ keys)
        safe_meta = {
            k: "[REDACTED]" if k in redacted else v
            for k, v in ctx.metadata.items()
            if not k.startswith("__")
        }
        if safe_meta:
            entry["hook.metadata"] = safe_meta

        if extra:
            entry.update(extra)

        line = json.dumps(entry, default=str)
        try:
            async with self._lock:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._write_line, line
                )
        except OSError as exc:
            import sys
            print(f"[agenthooks.audit] WARNING: could not write audit entry: {exc}", file=sys.stderr)

    def _write_line(self, line: str) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# Module-level default instance — wired into the executor automatically.
# Override by passing your own AuditTrail to HookAgent or hookpoint().
_default_audit: AuditTrail | None = None


def get_default_audit() -> AuditTrail:
    global _default_audit
    if _default_audit is None:
        _default_audit = AuditTrail()
    return _default_audit


def set_default_audit(audit: AuditTrail) -> None:
    """Replace the module-level audit trail (e.g. in tests)."""
    global _default_audit
    _default_audit = audit
