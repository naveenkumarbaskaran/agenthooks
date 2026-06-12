from __future__ import annotations


class AgenthooksError(Exception):
    """Base for all agenthooks errors."""


class HookBlocked(AgenthooksError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
    def __str__(self) -> str:
        return f"HookBlocked: {self.reason}"


class HookSkip(AgenthooksError):
    """Skip remaining impls on this hookpoint."""


class HookConflict(AgenthooksError):
    def __init__(self, hookpoint: str, impl_name: str) -> None:
        super().__init__(
            f"Hookpoint '{hookpoint}' is mode='single' but a second implementation "
            f"'{impl_name}' was registered. Only one implementation is allowed."
        )
        self.hookpoint = hookpoint
        self.impl_name = impl_name


class HookContractError(AgenthooksError):
    def __init__(self, hookpoint: str, required: str, got: str) -> None:
        super().__init__(
            f"Hook contract mismatch on '{hookpoint}': "
            f"hookpoint requires '{required}', impl declared '{got}'"
        )
        self.hookpoint = hookpoint
        self.required = required
        self.got = got


class HookTimeout(AgenthooksError):
    def __init__(self, hookpoint: str, impl_name: str, timeout_ms: int) -> None:
        super().__init__(
            f"Hook '{impl_name}' on '{hookpoint}' timed out after {timeout_ms}ms"
        )
        self.hookpoint = hookpoint
        self.impl_name = impl_name
        self.timeout_ms = timeout_ms


class HookSecurityError(AgenthooksError):
    def __init__(self, field: str) -> None:
        super().__init__(
            f"Field '{field}' is sealed — hooks cannot write it. "
            f"This field is part of the security boundary."
        )
        self.field = field


class HookRecursionError(AgenthooksError):
    def __init__(self, hookpoint: str) -> None:
        super().__init__(
            f"Recursive hook call detected on '{hookpoint}'. "
            f"Hooks cannot trigger the same hookpoint they are running under."
        )
        self.hookpoint = hookpoint
