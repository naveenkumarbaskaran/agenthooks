from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from agenthooks.core.context import HookContext
from agenthooks.core.contract import check_compatibility
from agenthooks.core.exceptions import HookConflict, HookContractError

HookFn = Callable[[HookContext], Coroutine[Any, Any, HookContext]]

@dataclasses.dataclass
class ImplRegistration:
    fn: HookFn
    hookpoint: str
    mode: str = "multi"
    filter: dict = dataclasses.field(default_factory=dict)
    order: int = 100
    timeout_ms: int = 500
    fallback: bool = True
    on_error: str = "degrade"
    retry_max: int = 3
    retry_backoff_ms: int = 100
    contract_version: str | None = None
    parallel: bool = False


class HookRegistry:
    def __init__(self, default_timeout_ms: int = 500) -> None:
        self._default_timeout_ms = default_timeout_ms
        self._impls: dict[str, list[ImplRegistration]] = defaultdict(list)
        self._modes: dict[str, str] = {}

    def implement(
        self,
        hookpoint: str,
        *,
        mode: str = "multi",
        filter: dict | None = None,  # noqa: A002
        order: int = 100,
        timeout_ms: int | None = None,
        fallback: bool = True,
        on_error: str = "degrade",
        retry_max: int = 3,
        retry_backoff_ms: int = 100,
        contract_version: str | None = None,
        hookpoint_contract: str | None = None,
        parallel: bool = False,
    ) -> Callable[[HookFn], HookFn]:
        def decorator(fn: HookFn) -> HookFn:
            if hookpoint_contract is not None:
                if not check_compatibility(required=hookpoint_contract, got=contract_version):
                    raise HookContractError(hookpoint=hookpoint, required=hookpoint_contract, got=contract_version or "None")
            existing_mode = self._modes.get(hookpoint)
            if existing_mode == "single" and self._impls[hookpoint]:
                raise HookConflict(hookpoint, fn.__name__)
            if mode == "single" and self._impls[hookpoint]:
                raise HookConflict(hookpoint, fn.__name__)
            self._modes[hookpoint] = mode
            reg = ImplRegistration(
                fn=fn, hookpoint=hookpoint, mode=mode, filter=filter or {},
                order=order, timeout_ms=timeout_ms if timeout_ms is not None else self._default_timeout_ms,
                fallback=fallback, on_error=on_error, retry_max=retry_max,
                retry_backoff_ms=retry_backoff_ms, contract_version=contract_version, parallel=parallel,
            )
            self._impls[hookpoint].append(reg)
            return fn
        return decorator

    def get_impls(self, hookpoint: str, ctx: HookContext) -> list[ImplRegistration]:
        all_impls = self._impls.get(hookpoint, [])
        matched = [r for r in all_impls if self._matches_filter(r.filter, ctx)]
        return sorted(matched, key=lambda r: r.order)

    def _matches_filter(self, f: dict, ctx: HookContext) -> bool:
        for key, expected in f.items():
            if key == "tenant":
                actual = ctx.tenant_id
            elif key == "tool_name":
                actual = ctx.tool_name
            else:
                actual = ctx.metadata.get(key)
            if actual != expected:
                return False
        return True
