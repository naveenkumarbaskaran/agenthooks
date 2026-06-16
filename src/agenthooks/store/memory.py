from __future__ import annotations

from collections import defaultdict

from agenthooks.core.registry import HookRegistry


class InMemoryStore:
    def __init__(self) -> None:
        self._registries: dict[str, list[HookRegistry]] = defaultdict(list)

    def add_registry(self, agent_id: str, registry: HookRegistry) -> None:
        self._registries[agent_id].append(registry)

    def get_registries(self, agent_id: str) -> list[HookRegistry]:
        return list(self._registries.get(agent_id, []))

    def clear(self, agent_id: str | None = None) -> None:
        if agent_id:
            self._registries.pop(agent_id, None)
        else:
            self._registries.clear()
