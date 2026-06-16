
from agenthooks.core.registry import HookRegistry
from agenthooks.store.memory import InMemoryStore


def test_saves_and_retrieves():
    store = InMemoryStore()
    registry = HookRegistry()
    store.add_registry("agent1", registry)
    registries = store.get_registries("agent1")
    assert len(registries) == 1
    assert registries[0] is registry

def test_returns_empty_for_unknown():
    store = InMemoryStore()
    assert store.get_registries("unknown_agent") == []

def test_supports_multiple_registries_per_agent():
    store = InMemoryStore()
    r1 = HookRegistry()
    r2 = HookRegistry()
    store.add_registry("agent1", r1)
    store.add_registry("agent1", r2)
    registries = store.get_registries("agent1")
    assert len(registries) == 2
    assert r1 in registries
    assert r2 in registries
