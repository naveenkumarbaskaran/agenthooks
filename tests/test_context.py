import time

import pytest

from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import HookBlocked, HookSecurityError, HookSkip


def make_ctx(**kwargs) -> HookContext:
    defaults = dict(session_id="s1", tenant_id="acme", trace_id="t1", span_id="sp1", turn=0, timestamp=time.time())
    return HookContext(**{**defaults, **kwargs})

def test_context_creates_with_required_fields():
    ctx = make_ctx()
    assert ctx.session_id == "s1"
    assert ctx.tenant_id == "acme"
    assert ctx.metadata == {}

def test_enrich_returns_new_context():
    ctx = make_ctx()
    ctx2 = ctx.enrich("plant", "1000")
    assert ctx2.metadata["plant"] == "1000"
    assert ctx.metadata == {}

def test_enrich_accumulates():
    ctx = make_ctx()
    ctx2 = ctx.enrich("plant", "1000").enrich("fiscal_year", "2026")
    assert ctx2.metadata["plant"] == "1000"
    assert ctx2.metadata["fiscal_year"] == "2026"

def test_replace_mutable_field():
    ctx = make_ctx(query="original")
    ctx2 = ctx.replace("query", "sanitised")
    assert ctx2.query == "sanitised"
    assert ctx.query == "original"

def test_replace_sealed_field_raises():
    ctx = make_ctx()
    with pytest.raises(HookSecurityError, match="tenant_id"):
        ctx.replace("tenant_id", "evil")

def test_sealed_fields_are_session_id_tenant_id_trace_id_span_id_turn_timestamp():
    ctx = make_ctx()
    for field in ("session_id", "tenant_id", "trace_id", "span_id", "turn", "timestamp"):
        with pytest.raises(HookSecurityError):
            ctx.replace(field, "tampered")

def test_redact_marks_fields():
    ctx = make_ctx()
    ctx2 = ctx.redact("api_key", "password")
    assert "api_key" in ctx2.metadata["__redacted__"]
    assert "password" in ctx2.metadata["__redacted__"]

def test_block_raises_hook_blocked():
    ctx = make_ctx()
    with pytest.raises(HookBlocked, match="Needs approval"):
        ctx.block("Needs approval")

def test_skip_raises_hook_skip():
    ctx = make_ctx()
    with pytest.raises(HookSkip):
        ctx.skip()

def test_new_classmethod_generates_ids():
    ctx = HookContext.new(session_id="s1", tenant_id="acme")
    assert ctx.trace_id
    assert ctx.span_id
    assert ctx.turn == 0
    assert ctx.timestamp > 0

def test_context_is_immutable_pydantic_model():
    ctx = make_ctx()
    with pytest.raises(Exception):
        ctx.session_id = "tampered"  # type: ignore
