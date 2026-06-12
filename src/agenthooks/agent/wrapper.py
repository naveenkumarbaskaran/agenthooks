from __future__ import annotations
from typing import Any, Callable
from agenthooks.core.registry import HookRegistry

class HookWrapper:
    def __init__(self, agent: Callable, registries: list[HookRegistry] | None = None) -> None:
        self._agent = agent
        self._registries: list[HookRegistry] = list(registries or [])

    def add_registry(self, registry: HookRegistry) -> None:
        self._registries.append(registry)

    async def invoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        result = self._agent(inputs)
        if hasattr(result, "__await__"):
            return await result
        return result
