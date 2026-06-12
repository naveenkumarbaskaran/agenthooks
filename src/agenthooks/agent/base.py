from __future__ import annotations
from agenthooks.core.hookpoint import HookPointDescriptor
from agenthooks.core.registry import HookRegistry

class HookAgent:
    def __init__(self, registries: list[HookRegistry] | None = None) -> None:
        self._registries: list[HookRegistry] = list(registries or [])
        self._bind_registries()

    def _bind_registries(self) -> None:
        for name in dir(type(self)):
            val = getattr(type(self), name, None)
            if isinstance(val, HookPointDescriptor):
                instance_hp = HookPointDescriptor(
                    name=val.name, mode=val.mode, parallel=val.parallel,
                    registries=list(self._registries),
                )
                object.__setattr__(self, name, instance_hp)

    def add_registry(self, registry: HookRegistry) -> None:
        self._registries.append(registry)
        self._bind_registries()
