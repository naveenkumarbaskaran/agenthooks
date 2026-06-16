from __future__ import annotations

import time
import uuid
from typing import Any

from agenthooks.core.exceptions import HookBlocked, HookSecurityError, HookSkip

_SEALED_FIELDS = frozenset({"session_id", "tenant_id", "trace_id", "span_id", "turn", "timestamp"})

try:
    from pydantic import BaseModel, ConfigDict, Field

    class HookContext(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
        session_id: str
        tenant_id: str | None = None
        trace_id: str
        span_id: str
        turn: int = 0
        timestamp: float
        query: str | None = None
        tool_name: str | None = None
        tool_inputs: dict[str, Any] = Field(default_factory=dict)
        tool_result: dict[str, Any] | None = None
        llm_response: str | None = None
        error: BaseException | None = None
        metadata: dict[str, Any] = Field(default_factory=dict)

        @classmethod
        def new(cls, session_id: str, tenant_id: str | None = None, **kwargs: Any) -> HookContext:
            return cls(
                session_id=session_id,
                tenant_id=tenant_id,
                trace_id=kwargs.pop("trace_id", str(uuid.uuid4())),
                span_id=kwargs.pop("span_id", str(uuid.uuid4())),
                timestamp=kwargs.pop("timestamp", time.time()),
                **kwargs,
            )

        def enrich(self, key: str, value: Any) -> HookContext:
            return self.model_copy(update={"metadata": {**self.metadata, key: value}})

        def replace(self, field: str, value: Any) -> HookContext:
            if field in _SEALED_FIELDS:
                raise HookSecurityError(field)
            return self.model_copy(update={field: value})

        def redact(self, *fields: str) -> HookContext:
            existing = list(self.metadata.get("__redacted__", []))
            return self.model_copy(update={"metadata": {**self.metadata, "__redacted__": existing + list(fields)}})

        def block(self, reason: str) -> None:
            raise HookBlocked(reason)

        def skip(self) -> None:
            raise HookSkip()

except ImportError:
    import dataclasses

    @dataclasses.dataclass
    class HookContext:  # type: ignore[no-redef]
        session_id: str
        tenant_id: str | None = None
        trace_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
        span_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
        turn: int = 0
        timestamp: float = dataclasses.field(default_factory=time.time)
        query: str | None = None
        tool_name: str | None = None
        tool_inputs: dict[str, Any] = dataclasses.field(default_factory=dict)
        tool_result: dict[str, Any] | None = None
        llm_response: str | None = None
        error: BaseException | None = None
        metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

        @classmethod
        def new(cls, session_id: str, tenant_id: str | None = None, **kwargs) -> HookContext:
            return cls(session_id=session_id, tenant_id=tenant_id, **kwargs)

        def _copy(self, **updates) -> HookContext:
            import copy
            obj = copy.copy(self)
            for k, v in updates.items():
                object.__setattr__(obj, k, v)
            return obj

        def enrich(self, key: str, value) -> HookContext:
            return self._copy(metadata={**self.metadata, key: value})

        def replace(self, field: str, value) -> HookContext:
            if field in _SEALED_FIELDS:
                raise HookSecurityError(field)
            return self._copy(**{field: value})

        def redact(self, *fields: str) -> HookContext:
            existing = list(self.metadata.get("__redacted__", []))
            return self._copy(metadata={**self.metadata, "__redacted__": existing + list(fields)})

        def block(self, reason: str) -> None:
            raise HookBlocked(reason)

        def skip(self) -> None:
            raise HookSkip()

        def model_dump(self) -> dict[str, Any]:
            return dataclasses.asdict(self)
