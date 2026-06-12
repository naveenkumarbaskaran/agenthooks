import pytest
from agenthooks.core.exceptions import (
    HookBlocked, HookSkip, HookConflict,
    HookContractError, HookTimeout,
    HookSecurityError, HookRecursionError,
)

def test_hook_blocked_carries_reason():
    exc = HookBlocked("Needs approval")
    assert exc.reason == "Needs approval"
    assert str(exc) == "HookBlocked: Needs approval"

def test_hook_blocked_is_exception():
    with pytest.raises(HookBlocked, match="Needs approval"):
        raise HookBlocked("Needs approval")

def test_hook_skip_is_exception():
    with pytest.raises(HookSkip):
        raise HookSkip()

def test_hook_conflict_carries_hookpoint():
    exc = HookConflict("before_teco", "second_impl")
    assert exc.hookpoint == "before_teco"
    assert exc.impl_name == "second_impl"

def test_hook_contract_error_carries_versions():
    exc = HookContractError("before_teco", required=">=1.0,<2.0", got="0.9")
    assert exc.hookpoint == "before_teco"
    assert "0.9" in str(exc)

def test_hook_timeout_carries_info():
    exc = HookTimeout("before_teco", "my_impl", timeout_ms=500)
    assert exc.timeout_ms == 500

def test_hook_security_error_carries_field():
    exc = HookSecurityError("tenant_id")
    assert "tenant_id" in str(exc)

def test_hook_recursion_error():
    exc = HookRecursionError("before_teco")
    assert "before_teco" in str(exc)
