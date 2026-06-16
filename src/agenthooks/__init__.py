from agenthooks.agent.base import HookAgent
from agenthooks.agent.wrapper import HookWrapper
from agenthooks.audit import AuditTrail, get_default_audit, set_default_audit
from agenthooks.core.context import HookContext
from agenthooks.core.exceptions import (
    AgenthooksError,
    HookBlocked,
    HookConflict,
    HookContractError,
    HookRecursionError,
    HookSecurityError,
    HookSkip,
    HookTimeout,
)
from agenthooks.core.hookpoint import HookPointDescriptor, hookpoint
from agenthooks.core.registry import HookRegistry, ImplRegistration
from agenthooks.observability import (
    configure_logging,
    get_instruments,
    get_meter,
    get_tracer,
    record_metric,
)
from agenthooks.patterns import block_if, inject, rate_limit, redact, require_tenant, retry
from agenthooks.security.guards import injection_scan
from agenthooks.store.memory import InMemoryStore

__version__ = "0.1.1"
__all__ = [
    # Core
    "HookContext", "HookAgent", "HookWrapper", "HookRegistry", "ImplRegistration",
    "InMemoryStore", "hookpoint", "HookPointDescriptor",
    # Exceptions
    "AgenthooksError", "HookBlocked", "HookSkip", "HookConflict",
    "HookContractError", "HookTimeout", "HookSecurityError", "HookRecursionError",
    # Audit
    "AuditTrail", "get_default_audit", "set_default_audit",
    # Observability
    "configure_logging", "get_tracer", "get_meter", "get_instruments", "record_metric",
    # Patterns
    "inject", "block_if", "redact", "rate_limit", "require_tenant", "retry",
    # Security
    "injection_scan",
]
