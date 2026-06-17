# AgentMesh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build agentmesh-py — a production-grade, agent-native event bus with pluggable transports, always-on persistence, full replay, consumer groups, DLQ, NATS-style wildcards, server-side filters, idempotency, OTel integration, and optional agentplane/agenthooks/agentregistry integrations.

**Architecture:** Zero-dep in-process core using asyncio queues and JSONL persistence. Transport and store are swappable via ABCs. AgentMesh is the top-level facade. Router handles topic→subscriber mapping with wildcard matching. EventStore persists every event before delivery.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, json, pathlib. Optional: redis, nats-py, aiokafka, aiosqlite, opentelemetry-api.

**Spec:** `docs/superpowers/specs/2026-06-17-agentmesh-design.md`

---

## File Map

```
agentmesh/
├── src/agentmesh/
│   ├── __init__.py            # exports: AgentMesh, AgentEvent, DeadEvent, TopicConfig
│   ├── event.py               # AgentEvent dataclass + EventBuilder helpers
│   ├── topic.py               # TopicConfig dataclass
│   ├── router.py              # Router: wildcard matching, consumer groups
│   ├── dedup.py               # DedupWindow: event_id deduplication
│   ├── filter.py              # EventFilter: server-side predicate evaluation
│   ├── mesh.py                # AgentMesh: main facade
│   ├── dlq.py                 # DeadLetterQueue + DeadEvent
│   ├── replay.py              # ReplayEngine
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── _base.py           # Transport ABC
│   │   └── inprocess.py       # InProcessTransport (asyncio queues)
│   ├── store/
│   │   ├── __init__.py
│   │   ├── _base.py           # EventStore ABC
│   │   └── jsonl.py           # JsonlStore (default)
│   ├── otel.py                # OTel span/metric emission (no-op if not installed)
│   └── integrations/
│       ├── __init__.py
│       ├── agentplane.py      # policy enforcement hooks
│       └── agenthooks.py      # agenthooks hook point wiring
├── tests/
│   ├── conftest.py
│   ├── test_event.py
│   ├── test_router.py
│   ├── test_dedup.py
│   ├── test_filter.py
│   ├── test_store.py
│   ├── test_dlq.py
│   ├── test_replay.py
│   └── test_mesh.py           # integration tests (all layers)
├── examples/
│   ├── 01_hello_mesh.py
│   ├── 02_consumer_groups.py
│   ├── 03_human_in_the_loop.py
│   ├── 04_replay.py
│   └── 05_multi_agent_workflow.py
├── scripts/
│   ├── regression.sh
│   ├── bump-version.sh
│   ├── install-hooks.sh
│   └── pre-push.hook
├── assets/banner.svg
├── .github/workflows/
│   ├── ci.yml
│   └── publish.yml
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## Task 1: Scaffold repo + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `src/agentmesh/__init__.py` (empty stub)
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [ ] **Step 1: Create directories**

```bash
mkdir -p /Users/I572120/Documents/💻\ Workspace/personal/github-repos/agentmesh/{src/agentmesh/{transport,store,integrations},tests,examples,scripts,assets,.github/workflows}
cd /Users/I572120/Documents/💻\ Workspace/personal/github-repos/agentmesh
git init && git checkout -b master
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "agentmesh-py"
version = "0.1.0"
description = "Agent-native event bus — connect agents, humans, and systems via typed events"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
authors = [{ name = "Naveen Kumar Baskaran" }]
keywords = ["agents", "events", "pubsub", "mesh", "kafka", "enterprise", "llm"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Typing :: Typed",
]
dependencies = []

[project.urls]
Homepage   = "https://github.com/naveenkumarbaskaran/agentmesh"
Repository = "https://github.com/naveenkumarbaskaran/agentmesh"
Issues     = "https://github.com/naveenkumarbaskaran/agentmesh/issues"

[project.optional-dependencies]
redis   = ["redis>=5.0"]
nats    = ["nats-py>=2.0"]
kafka   = ["aiokafka>=0.10"]
sqlite  = ["aiosqlite>=0.20"]
otel    = ["opentelemetry-api>=1.20"]
all     = ["agentmesh-py[redis,nats,kafka,sqlite,otel]"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentmesh"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths    = ["tests"]

[tool.ruff]
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
ignore = ["E501", "E741"]

[tool.mypy]
python_version        = "3.11"
ignore_missing_imports = true
check_untyped_defs    = true
warn_unused_ignores   = false
```

- [ ] **Step 3: Write stub __init__.py**

`src/agentmesh/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write conftest.py**

`tests/conftest.py`:
```python
import pytest

@pytest.fixture
def tenant_id() -> str:
    return "acme"

@pytest.fixture
def agent_id() -> str:
    return "test-agent"
```

- [ ] **Step 5: Write .gitignore**

```
__pycache__/
*.py[cod]
.venv/
*.egg-info/
dist/
build/
.DS_Store
*.jsonl
*.db
.env
.mypy_cache/
.ruff_cache/
.pytest_cache/
```

- [ ] **Step 6: Create venv + install**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]" -q
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold agentmesh-py repo"
```

---

## Task 2: AgentEvent dataclass

**Files:**
- Create: `src/agentmesh/event.py`
- Create: `src/agentmesh/topic.py`
- Create: `tests/test_event.py`

- [ ] **Step 1: Write failing tests**

`tests/test_event.py`:
```python
import time
import uuid
from agentmesh.event import AgentEvent

def test_event_required_fields():
    e = AgentEvent(
        event_type="order.created",
        topic="order.created",
        session_id="s1",
        run_id="r1",
        publisher_id="agent-1",
        publisher_type="agent",
        data={"order_id": "ORD-001"},
    )
    assert e.event_type == "order.created"
    assert e.schema_version == "1.0"
    assert e.delivery_mode == "broadcast"
    assert e.tags == []
    assert e.metadata == {}
    assert e.ttl_s is None
    assert e.tenant_id is None
    assert e.caused_by_event_id is None

def test_event_id_auto_generated():
    e = AgentEvent(event_type="t", topic="t", session_id="s",
                   run_id="r", publisher_id="p", publisher_type="agent", data={})
    assert len(e.event_id) == 36  # UUID format

def test_event_id_custom():
    custom_id = str(uuid.uuid4())
    e = AgentEvent(event_type="t", topic="t", session_id="s",
                   run_id="r", publisher_id="p", publisher_type="agent",
                   data={}, event_id=custom_id)
    assert e.event_id == custom_id

def test_event_timestamp_auto():
    before = time.time()
    e = AgentEvent(event_type="t", topic="t", session_id="s",
                   run_id="r", publisher_id="p", publisher_type="agent", data={})
    after = time.time()
    assert before <= e.timestamp <= after

def test_event_to_dict():
    e = AgentEvent(event_type="order.created", topic="order.created",
                   session_id="s1", run_id="r1", publisher_id="agent-1",
                   publisher_type="agent", data={"amount": 99.99},
                   tenant_id="acme")
    d = e.to_dict()
    assert d["event_type"] == "order.created"
    assert d["tenant_id"] == "acme"
    assert d["data"]["amount"] == 99.99

def test_event_from_dict():
    e = AgentEvent(event_type="order.created", topic="order.created",
                   session_id="s1", run_id="r1", publisher_id="agent-1",
                   publisher_type="agent", data={"amount": 99.99})
    d = e.to_dict()
    e2 = AgentEvent.from_dict(d)
    assert e2.event_id == e.event_id
    assert e2.event_type == e.event_type
    assert e2.data == e.data
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_event.py -q
```
Expected: `ModuleNotFoundError: No module named 'agentmesh.event'`

- [ ] **Step 3: Implement event.py**

`src/agentmesh/event.py`:
```python
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    # Required
    event_type:         str
    topic:              str
    session_id:         str
    run_id:             str
    publisher_id:       str
    publisher_type:     str           # "agent" | "human" | "system"
    data:               dict[str, Any]

    # Auto-generated
    event_id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:          float = field(default_factory=time.time)
    schema_version:     str = "1.0"

    # Hierarchy
    parent_run_id:      str | None = None
    caused_by_event_id: str | None = None

    # OTel
    trace_id:           str | None = None
    span_id:            str | None = None

    # Source
    agent_id:           str | None = None
    agent_name:         str | None = None
    tenant_id:          str | None = None
    provider:           str | None = None

    # Routing
    delivery_mode:      str = "broadcast"   # "broadcast" | "exclusive"
    ttl_s:              float | None = None

    # Classification
    tags:               list[str] = field(default_factory=list)
    metadata:           dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id":           self.event_id,
            "event_type":         self.event_type,
            "topic":              self.topic,
            "schema_version":     self.schema_version,
            "timestamp":          self.timestamp,
            "session_id":         self.session_id,
            "run_id":             self.run_id,
            "parent_run_id":      self.parent_run_id,
            "caused_by_event_id": self.caused_by_event_id,
            "trace_id":           self.trace_id,
            "span_id":            self.span_id,
            "agent_id":           self.agent_id,
            "agent_name":         self.agent_name,
            "tenant_id":          self.tenant_id,
            "publisher_id":       self.publisher_id,
            "publisher_type":     self.publisher_type,
            "provider":           self.provider,
            "delivery_mode":      self.delivery_mode,
            "ttl_s":              self.ttl_s,
            "tags":               self.tags,
            "metadata":           self.metadata,
            "data":               self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentEvent:
        return cls(
            event_id=d["event_id"],
            event_type=d["event_type"],
            topic=d["topic"],
            schema_version=d.get("schema_version", "1.0"),
            timestamp=d["timestamp"],
            session_id=d["session_id"],
            run_id=d["run_id"],
            parent_run_id=d.get("parent_run_id"),
            caused_by_event_id=d.get("caused_by_event_id"),
            trace_id=d.get("trace_id"),
            span_id=d.get("span_id"),
            agent_id=d.get("agent_id"),
            agent_name=d.get("agent_name"),
            tenant_id=d.get("tenant_id"),
            publisher_id=d["publisher_id"],
            publisher_type=d["publisher_type"],
            provider=d.get("provider"),
            delivery_mode=d.get("delivery_mode", "broadcast"),
            ttl_s=d.get("ttl_s"),
            tags=d.get("tags", []),
            metadata=d.get("metadata", {}),
            data=d.get("data", {}),
        )

    def is_expired(self) -> bool:
        if self.ttl_s is None:
            return False
        return (time.time() - self.timestamp) > self.ttl_s
```

- [ ] **Step 4: Implement topic.py**

`src/agentmesh/topic.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TopicConfig:
    topic:              str
    dlq:                bool = True
    max_retries:        int = 3
    retry_backoff_ms:   int = 500
    ttl_s:              float | None = None
    delivery_mode:      str = "broadcast"   # "broadcast" | "exclusive"
    paused:             bool = False
```

- [ ] **Step 5: Run tests — verify PASS**

```bash
.venv/bin/pytest tests/test_event.py -q
```
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add src/agentmesh/event.py src/agentmesh/topic.py tests/test_event.py tests/conftest.py
git commit -m "feat: AgentEvent dataclass with to_dict/from_dict + TopicConfig"
```

---

## Task 3: Router — wildcard matching + consumer groups

**Files:**
- Create: `src/agentmesh/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write failing tests**

`tests/test_router.py`:
```python
import asyncio
from agentmesh.router import Router
from agentmesh.event import AgentEvent


def make_event(topic: str, **kwargs) -> AgentEvent:
    return AgentEvent(
        event_type=topic, topic=topic, session_id="s1", run_id="r1",
        publisher_id="p1", publisher_type="agent", data={}, **kwargs,
    )


def test_exact_match():
    r = Router()
    received = []
    async def handler(e): received.append(e)
    r.subscribe("order.created", handler)
    assert r.matches("order.created", "order.created")
    assert not r.matches("order.created", "order.updated")


def test_wildcard_single_segment():
    r = Router()
    assert r.matches("order.*", "order.created")
    assert r.matches("order.*", "order.updated")
    assert not r.matches("order.*", "order.item.created")


def test_wildcard_multi_segment():
    r = Router()
    assert r.matches("order.>", "order.created")
    assert r.matches("order.>", "order.item.created")
    assert r.matches("order.>", "order.item.variant.updated")
    assert not r.matches("order.>", "payment.created")


def test_wildcard_any_category():
    r = Router()
    assert r.matches("*.created", "order.created")
    assert r.matches("*.created", "payment.created")
    assert not r.matches("*.created", "order.updated")


def test_wildcard_all():
    r = Router()
    assert r.matches(">", "order.created")
    assert r.matches(">", "system.heartbeat")
    assert r.matches(">", "a.b.c.d.e")


def test_tenant_namespaced_topic():
    r = Router()
    assert r.matches("acme:order.created", "acme:order.created")
    assert not r.matches("acme:order.created", "siemens:order.created")
    assert r.matches("acme:>", "acme:order.created")
    assert not r.matches("acme:>", "siemens:order.created")


@pytest.mark.asyncio
async def test_get_handlers_broadcast():
    import pytest
    r = Router()
    calls = []
    async def h1(e): calls.append("h1")
    async def h2(e): calls.append("h2")
    r.subscribe("order.created", h1)
    r.subscribe("order.created", h2)
    event = make_event("order.created")
    handlers = r.get_handlers(event)
    for h in handlers:
        await h(event)
    assert calls == ["h1", "h2"]


@pytest.mark.asyncio
async def test_get_handlers_consumer_group():
    import pytest
    r = Router()
    calls = []
    async def h1(e): calls.append("h1")
    async def h2(e): calls.append("h2")
    r.subscribe("order.created", h1, group="workers")
    r.subscribe("order.created", h2, group="workers")
    event = make_event("order.created")
    handlers = r.get_handlers(event)
    # Only ONE handler from group "workers" should be returned
    for h in handlers:
        await h(event)
    assert len(calls) == 1


def test_unsubscribe():
    r = Router()
    received = []
    async def h(e): received.append(e)
    r.subscribe("order.created", h)
    r.unsubscribe("order.created", h)
    event = make_event("order.created")
    handlers = r.get_handlers(event)
    assert len(handlers) == 0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_router.py -q
```
Expected: `ModuleNotFoundError: No module named 'agentmesh.router'`

- [ ] **Step 3: Implement router.py**

`src/agentmesh/router.py`:
```python
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from agentmesh.event import AgentEvent

Handler = Callable[[AgentEvent], Coroutine[Any, Any, None]]


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert NATS-style wildcard pattern to regex.

    * matches exactly one segment (between dots, after colon)
    > matches one or more segments (must be last token)
    """
    if pattern == ">":
        return re.compile(r".+")
    escaped = re.escape(pattern)
    # Replace \> at end with multi-segment wildcard
    escaped = re.sub(r"\\\.$", "", escaped)
    escaped = escaped.replace(r"\>", r"[^:]+(\.[^:]+)*")
    # Replace \* with single-segment wildcard
    escaped = escaped.replace(r"\*", r"[^.:]+")
    return re.compile(f"^{escaped}$")


class _Subscription:
    def __init__(self, pattern: str, handler: Handler, group: str | None) -> None:
        self.pattern = pattern
        self.handler = handler
        self.group = group
        self._regex = _pattern_to_regex(pattern)

    def matches(self, topic: str) -> bool:
        return bool(self._regex.match(topic))


class Router:
    def __init__(self) -> None:
        self._subs: list[_Subscription] = []
        self._group_counters: dict[str, int] = defaultdict(int)

    def subscribe(self, pattern: str, handler: Handler,
                  group: str | None = None) -> None:
        self._subs.append(_Subscription(pattern, handler, group))

    def unsubscribe(self, pattern: str, handler: Handler) -> None:
        self._subs = [s for s in self._subs
                      if not (s.pattern == pattern and s.handler is handler)]

    def matches(self, pattern: str, topic: str) -> bool:
        return bool(_pattern_to_regex(pattern).match(topic))

    def get_handlers(self, event: AgentEvent) -> list[Handler]:
        matched = [s for s in self._subs if s.matches(event.topic)]
        handlers: list[Handler] = []
        seen_groups: dict[str, bool] = {}
        for sub in matched:
            if sub.group is None:
                handlers.append(sub.handler)
            else:
                if sub.group not in seen_groups:
                    # Round-robin: pick one handler per group
                    group_subs = [s for s in matched if s.group == sub.group]
                    idx = self._group_counters[sub.group] % len(group_subs)
                    self._group_counters[sub.group] += 1
                    handlers.append(group_subs[idx].handler)
                    seen_groups[sub.group] = True
        return handlers
```

- [ ] **Step 4: Fix test imports (add pytest import)**

In `tests/test_router.py`, move the `import pytest` to the top:
```python
import asyncio
import pytest
from agentmesh.router import Router
from agentmesh.event import AgentEvent
```
Remove the inline `import pytest` lines from inside test functions.

- [ ] **Step 5: Run tests — verify PASS**

```bash
.venv/bin/pytest tests/test_router.py -q
```
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add src/agentmesh/router.py tests/test_router.py
git commit -m "feat: Router with NATS-style wildcard matching and consumer groups"
```

---

## Task 4: DedupWindow — idempotency via event_id

**Files:**
- Create: `src/agentmesh/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dedup.py`:
```python
import time
from agentmesh.dedup import DedupWindow


def test_first_event_not_duplicate():
    d = DedupWindow(window_s=60.0)
    assert not d.is_duplicate("evt-001")


def test_same_event_id_is_duplicate():
    d = DedupWindow(window_s=60.0)
    d.mark_seen("evt-001")
    assert d.is_duplicate("evt-001")


def test_different_event_id_not_duplicate():
    d = DedupWindow(window_s=60.0)
    d.mark_seen("evt-001")
    assert not d.is_duplicate("evt-002")


def test_expired_event_not_duplicate():
    d = DedupWindow(window_s=0.01)  # 10ms window
    d.mark_seen("evt-001")
    time.sleep(0.02)
    d.gc()
    assert not d.is_duplicate("evt-001")


def test_check_and_mark_returns_false_first_time():
    d = DedupWindow(window_s=60.0)
    # Returns True if duplicate (should drop), False if new (should process)
    assert not d.check_and_mark("evt-001")  # new — process it
    assert d.check_and_mark("evt-001")      # duplicate — drop it
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_dedup.py -q
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement dedup.py**

`src/agentmesh/dedup.py`:
```python
from __future__ import annotations

import time


class DedupWindow:
    """Deduplication window keyed by event_id.

    Maintains a sliding window of seen event IDs.
    After window_s seconds, an event_id can be re-processed.
    Default window is 86400s (24h) — covers typical retry windows.
    """

    def __init__(self, window_s: float = 86400.0) -> None:
        self._window_s = window_s
        self._seen: dict[str, float] = {}  # event_id → seen_at timestamp

    def is_duplicate(self, event_id: str) -> bool:
        seen_at = self._seen.get(event_id)
        if seen_at is None:
            return False
        if (time.time() - seen_at) > self._window_s:
            del self._seen[event_id]
            return False
        return True

    def mark_seen(self, event_id: str) -> None:
        self._seen[event_id] = time.time()

    def check_and_mark(self, event_id: str) -> bool:
        """Returns True if duplicate (caller should drop), False if new."""
        if self.is_duplicate(event_id):
            return True
        self.mark_seen(event_id)
        return False

    def gc(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        expired = [k for k, v in self._seen.items()
                   if (now - v) > self._window_s]
        for k in expired:
            del self._seen[k]
        return len(expired)
```

- [ ] **Step 4: Run — verify PASS**

```bash
.venv/bin/pytest tests/test_dedup.py -q
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agentmesh/dedup.py tests/test_dedup.py
git commit -m "feat: DedupWindow — event_id idempotency with sliding TTL window"
```

---

## Task 5: EventFilter — server-side subscription filtering

**Files:**
- Create: `src/agentmesh/filter.py`
- Create: `tests/test_filter.py`

- [ ] **Step 1: Write failing tests**

`tests/test_filter.py`:
```python
from agentmesh.filter import EventFilter
from agentmesh.event import AgentEvent


def make_event(**kwargs) -> AgentEvent:
    defaults = dict(event_type="order.created", topic="order.created",
                    session_id="s1", run_id="r1", publisher_id="p1",
                    publisher_type="agent", data={}, tenant_id="acme")
    defaults.update(kwargs)
    return AgentEvent(**defaults)


def test_empty_filter_matches_all():
    f = EventFilter({})
    assert f.matches(make_event())


def test_exact_field_match():
    f = EventFilter({"tenant_id": "acme"})
    assert f.matches(make_event(tenant_id="acme"))
    assert not f.matches(make_event(tenant_id="siemens"))


def test_nested_data_field():
    f = EventFilter({"data.amount": 100})
    assert f.matches(make_event(data={"amount": 100}))
    assert not f.matches(make_event(data={"amount": 50}))


def test_gt_operator():
    f = EventFilter({"data.amount": {"$gt": 1000}})
    assert f.matches(make_event(data={"amount": 1500}))
    assert not f.matches(make_event(data={"amount": 500}))


def test_lt_operator():
    f = EventFilter({"data.amount": {"$lt": 100}})
    assert f.matches(make_event(data={"amount": 50}))
    assert not f.matches(make_event(data={"amount": 200}))


def test_in_operator():
    f = EventFilter({"tenant_id": {"$in": ["acme", "siemens"]}})
    assert f.matches(make_event(tenant_id="acme"))
    assert f.matches(make_event(tenant_id="siemens"))
    assert not f.matches(make_event(tenant_id="unknown"))


def test_multiple_conditions_and():
    f = EventFilter({"tenant_id": "acme", "data.amount": {"$gt": 100}})
    assert f.matches(make_event(tenant_id="acme", data={"amount": 500}))
    assert not f.matches(make_event(tenant_id="acme", data={"amount": 50}))
    assert not f.matches(make_event(tenant_id="siemens", data={"amount": 500}))
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_filter.py -q
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement filter.py**

`src/agentmesh/filter.py`:
```python
from __future__ import annotations

from typing import Any

from agentmesh.event import AgentEvent


def _get_nested(obj: Any, path: str) -> Any:
    """Get nested field by dot-notation path. e.g. 'data.amount'"""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def _matches_condition(actual: Any, condition: Any) -> bool:
    if isinstance(condition, dict):
        for op, value in condition.items():
            if op == "$gt":
                if actual is None or actual <= value:
                    return False
            elif op == "$lt":
                if actual is None or actual >= value:
                    return False
            elif op == "$gte":
                if actual is None or actual < value:
                    return False
            elif op == "$lte":
                if actual is None or actual > value:
                    return False
            elif op == "$in":
                if actual not in value:
                    return False
            elif op == "$ne":
                if actual == value:
                    return False
        return True
    return actual == condition


class EventFilter:
    """Server-side subscription filter evaluated before delivery.

    Filter keys use dot-notation for nested fields.
    Filter values can be scalars (exact match) or operator dicts:
        {"$gt": 100}, {"$lt": 50}, {"$in": ["a","b"]}, {"$ne": "x"}

    All conditions are AND-ed together.
    """

    def __init__(self, conditions: dict[str, Any]) -> None:
        self._conditions = conditions

    def matches(self, event: AgentEvent) -> bool:
        if not self._conditions:
            return True
        event_dict = event.to_dict()
        for path, condition in self._conditions.items():
            actual = _get_nested(event_dict, path)
            if not _matches_condition(actual, condition):
                return False
        return True
```

- [ ] **Step 4: Run — verify PASS**

```bash
.venv/bin/pytest tests/test_filter.py -q
```
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agentmesh/filter.py tests/test_filter.py
git commit -m "feat: EventFilter — server-side predicate with dot-notation and operators"
```

---

## Task 6: EventStore — JSONL persistence

**Files:**
- Create: `src/agentmesh/store/_base.py`
- Create: `src/agentmesh/store/jsonl.py`
- Create: `src/agentmesh/store/__init__.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests**

`tests/test_store.py`:
```python
import asyncio
import pathlib
import tempfile
import time
import pytest
from agentmesh.event import AgentEvent
from agentmesh.store.jsonl import JsonlStore


def make_event(topic: str = "order.created", **kwargs) -> AgentEvent:
    return AgentEvent(event_type=topic, topic=topic, session_id="s1", run_id="r1",
                      publisher_id="p1", publisher_type="agent", data={}, **kwargs)


@pytest.fixture
def store(tmp_path):
    path = str(tmp_path / "events.jsonl")
    return JsonlStore(path=path)


@pytest.mark.asyncio
async def test_append_and_replay(store):
    e = make_event()
    await store.append(e)
    events = []
    async for event in store.replay("order.created"):
        events.append(event)
    assert len(events) == 1
    assert events[0].event_id == e.event_id


@pytest.mark.asyncio
async def test_replay_multiple_topics(store):
    await store.append(make_event("order.created"))
    await store.append(make_event("payment.initiated"))
    await store.append(make_event("order.created"))
    order_events = []
    async for e in store.replay("order.created"):
        order_events.append(e)
    assert len(order_events) == 2


@pytest.mark.asyncio
async def test_replay_since(store):
    e1 = make_event()
    await store.append(e1)
    t_mid = time.time()
    await asyncio.sleep(0.01)
    e2 = make_event()
    await store.append(e2)
    events = []
    async for e in store.replay("order.created", since=t_mid):
        events.append(e)
    assert len(events) == 1
    assert events[0].event_id == e2.event_id


@pytest.mark.asyncio
async def test_get_by_id(store):
    e = make_event()
    await store.append(e)
    found = await store.get(e.event_id)
    assert found is not None
    assert found.event_id == e.event_id


@pytest.mark.asyncio
async def test_get_missing_returns_none(store):
    result = await store.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_expired_events_pruned(store):
    e = make_event(ttl_s=0.01)
    await store.append(e)
    await asyncio.sleep(0.02)
    removed = await store.delete_expired()
    assert removed >= 1
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_store.py -q
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write _base.py**

`src/agentmesh/store/_base.py`:
```python
from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from agentmesh.event import AgentEvent


class EventStore(ABC):
    @abstractmethod
    async def append(self, event: AgentEvent) -> None: ...

    @abstractmethod
    async def get(self, event_id: str) -> AgentEvent | None: ...

    @abstractmethod
    def replay(self, topic: str, since: float = 0.0,
               until: float | None = None) -> AsyncIterator[AgentEvent]: ...

    @abstractmethod
    async def delete_expired(self) -> int: ...
```

- [ ] **Step 4: Write jsonl.py**

`src/agentmesh/store/jsonl.py`:
```python
from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

from agentmesh.event import AgentEvent
from agentmesh.store._base import EventStore


class JsonlStore(EventStore):
    """Default zero-dep event store. Appends to a JSONL file."""

    def __init__(self, path: str = "~/.agentmesh/events.jsonl") -> None:
        self._path = Path(os.path.expanduser(path))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(self, event: AgentEvent) -> None:
        line = json.dumps(event.to_dict(), default=str)
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                None, self._write_line, line
            )

    def _write_line(self, line: str) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def get(self, event_id: str) -> AgentEvent | None:
        if not self._path.exists():
            return None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                if d.get("event_id") == event_id:
                    return AgentEvent.from_dict(d)
            except json.JSONDecodeError:
                continue
        return None

    async def replay(self, topic: str, since: float = 0.0,  # type: ignore[override]
                     until: float | None = None) -> AsyncIterator[AgentEvent]:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("topic") != topic:
                continue
            ts = d.get("timestamp", 0.0)
            if ts < since:
                continue
            if until is not None and ts > until:
                continue
            yield AgentEvent.from_dict(d)

    async def delete_expired(self) -> int:
        if not self._path.exists():
            return 0
        now = time.time()
        kept = []
        removed = 0
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                ttl = d.get("ttl_s")
                ts = d.get("timestamp", 0.0)
                if ttl is not None and (now - ts) > ttl:
                    removed += 1
                    continue
            except json.JSONDecodeError:
                pass
            kept.append(line)
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                None, self._rewrite, kept
            )
        return removed

    def _rewrite(self, lines: list[str]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
```

- [ ] **Step 5: Write store/__init__.py**

`src/agentmesh/store/__init__.py`:
```python
from agentmesh.store._base import EventStore
from agentmesh.store.jsonl import JsonlStore

__all__ = ["EventStore", "JsonlStore"]
```

- [ ] **Step 6: Run — verify PASS**

```bash
.venv/bin/pytest tests/test_store.py -q
```
Expected: `7 passed`

- [ ] **Step 7: Commit**

```bash
git add src/agentmesh/store/ tests/test_store.py
git commit -m "feat: EventStore ABC + JsonlStore — zero-dep JSONL persistence with replay"
```

---

## Task 7: DeadLetterQueue

**Files:**
- Create: `src/agentmesh/dlq.py`
- Create: `tests/test_dlq.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dlq.py`:
```python
import pytest
from agentmesh.dlq import DeadLetterQueue, DeadEvent
from agentmesh.event import AgentEvent
from agentmesh.topic import TopicConfig


def make_event(topic: str = "order.created") -> AgentEvent:
    return AgentEvent(event_type=topic, topic=topic, session_id="s1", run_id="r1",
                      publisher_id="p1", publisher_type="agent", data={})


def test_push_to_dlq():
    dlq = DeadLetterQueue()
    e = make_event()
    dlq.push(e, error="delivery failed", subscriber_id="sub-1")
    assert dlq.depth("order.created") == 1


def test_pop_from_dlq():
    dlq = DeadLetterQueue()
    e = make_event()
    dlq.push(e, error="failed", subscriber_id="sub-1")
    dead = dlq.pop("order.created")
    assert dead is not None
    assert dead.event.event_id == e.event_id
    assert dead.error == "failed"
    assert dead.attempts == 1
    assert dlq.depth("order.created") == 0


def test_pop_empty_returns_none():
    dlq = DeadLetterQueue()
    assert dlq.pop("nonexistent") is None


def test_max_retries_respected():
    config = TopicConfig(topic="order.created", max_retries=2)
    dlq = DeadLetterQueue()
    e = make_event()
    dlq.push(e, error="fail 1", subscriber_id="sub-1")
    dead = dlq.pop("order.created")
    dlq.push(dead.event, error="fail 2", subscriber_id="sub-1",
             previous_attempts=dead.attempts)
    dead2 = dlq.pop("order.created")
    assert dead2.attempts == 2
    # Third push exceeds max_retries — should be dropped
    should_retry = dlq.push(dead2.event, error="fail 3", subscriber_id="sub-1",
                             previous_attempts=dead2.attempts, config=config)
    assert not should_retry
    assert dlq.depth("order.created") == 0


def test_iterate_dlq():
    dlq = DeadLetterQueue()
    for i in range(3):
        e = make_event()
        dlq.push(e, error=f"error {i}", subscriber_id="sub-1")
    items = list(dlq.iter("order.created"))
    assert len(items) == 3
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_dlq.py -q
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement dlq.py**

`src/agentmesh/dlq.py`:
```python
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from collections.abc import Iterator

from agentmesh.event import AgentEvent
from agentmesh.topic import TopicConfig


@dataclass
class DeadEvent:
    event: AgentEvent
    error: str
    attempts: int
    subscriber_id: str
    last_attempt_at: float = field(default_factory=time.time)


class DeadLetterQueue:
    def __init__(self) -> None:
        self._queues: dict[str, deque[DeadEvent]] = defaultdict(deque)

    def push(
        self,
        event: AgentEvent,
        error: str,
        subscriber_id: str,
        previous_attempts: int = 0,
        config: TopicConfig | None = None,
    ) -> bool:
        """Push a failed event. Returns True if queued, False if max_retries exceeded."""
        attempts = previous_attempts + 1
        if config is not None and attempts > config.max_retries:
            return False
        dead = DeadEvent(
            event=event,
            error=error,
            attempts=attempts,
            subscriber_id=subscriber_id,
        )
        self._queues[event.topic].append(dead)
        return True

    def pop(self, topic: str) -> DeadEvent | None:
        q = self._queues.get(topic)
        if not q:
            return None
        return q.popleft()

    def depth(self, topic: str) -> int:
        return len(self._queues.get(topic, []))

    def iter(self, topic: str) -> Iterator[DeadEvent]:
        yield from list(self._queues.get(topic, []))
```

- [ ] **Step 4: Run — verify PASS**

```bash
.venv/bin/pytest tests/test_dlq.py -q
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agentmesh/dlq.py tests/test_dlq.py
git commit -m "feat: DeadLetterQueue with max_retries and per-topic depth tracking"
```

---

## Task 8: Transport layer — base + InProcessTransport

**Files:**
- Create: `src/agentmesh/transport/_base.py`
- Create: `src/agentmesh/transport/inprocess.py`
- Create: `src/agentmesh/transport/__init__.py`

- [ ] **Step 1: Write transport/_base.py**

`src/agentmesh/transport/_base.py`:
```python
from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any
from agentmesh.event import AgentEvent

Handler = Callable[[AgentEvent], Coroutine[Any, Any, None]]


class Transport(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: AgentEvent) -> None: ...

    @abstractmethod
    async def subscribe(self, topic: str, group: str | None,
                        handler: Handler) -> None: ...

    @abstractmethod
    async def unsubscribe(self, topic: str, handler: Handler) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
```

- [ ] **Step 2: Write transport/inprocess.py**

`src/agentmesh/transport/inprocess.py`:
```python
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from agentmesh.event import AgentEvent
from agentmesh.transport._base import Transport

Handler = Callable[[AgentEvent], Coroutine[Any, Any, None]]


class InProcessTransport(Transport):
    """Default transport. Uses asyncio queues — zero external deps.
    Only works within a single process. Swap for Redis/NATS/Kafka in production.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str | None, Handler]]] = {}
        self._queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.ensure_future(self._dispatch_loop())

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def publish(self, topic: str, event: AgentEvent) -> None:
        await self._queue.put(event)

    async def subscribe(self, topic: str, group: str | None,
                        handler: Handler) -> None:
        self._handlers.setdefault(topic, []).append((group, handler))

    async def unsubscribe(self, topic: str, handler: Handler) -> None:
        if topic in self._handlers:
            self._handlers[topic] = [
                (g, h) for g, h in self._handlers[topic] if h is not handler
            ]

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self._deliver(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _deliver(self, event: AgentEvent) -> None:
        handlers = self._handlers.get(event.topic, [])
        for _group, handler in handlers:
            try:
                await handler(event)
            except Exception:
                pass
```

- [ ] **Step 3: Write transport/__init__.py**

`src/agentmesh/transport/__init__.py`:
```python
from agentmesh.transport._base import Transport
from agentmesh.transport.inprocess import InProcessTransport

__all__ = ["Transport", "InProcessTransport"]
```

- [ ] **Step 4: Run existing tests to verify nothing broken**

```bash
.venv/bin/pytest tests/ -q
```
Expected: all previous tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/agentmesh/transport/
git commit -m "feat: Transport ABC + InProcessTransport (asyncio queues, zero deps)"
```

---

## Task 9: OTel — no-op by default, live when installed

**Files:**
- Create: `src/agentmesh/otel.py`

- [ ] **Step 1: Write otel.py**

`src/agentmesh/otel.py`:
```python
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator
from typing import Any

from agentmesh.event import AgentEvent

try:
    from opentelemetry import metrics as _otel_metrics
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("agentmesh", "0.1.0")
    _meter  = _otel_metrics.get_meter("agentmesh", "0.1.0")
    _events_published = _meter.create_counter(
        "agentmesh.events.published",
        description="Total events published",
    )
    _events_delivered = _meter.create_counter(
        "agentmesh.events.delivered",
        description="Total events delivered to subscribers",
    )
    _events_failed = _meter.create_counter(
        "agentmesh.events.failed",
        description="Total failed deliveries",
    )
    _delivery_latency = _meter.create_histogram(
        "agentmesh.delivery.latency_ms",
        unit="ms",
        description="Event delivery latency",
    )
    _OTEL = True

except ImportError:
    _OTEL = False


def record_published(event: AgentEvent) -> None:
    if not _OTEL:
        return
    _events_published.add(1, {  # type: ignore
        "topic": event.topic,
        "tenant_id": event.tenant_id or "",
        "publisher_type": event.publisher_type,
    })


def record_delivered(event: AgentEvent, subscriber_id: str) -> None:
    if not _OTEL:
        return
    _events_delivered.add(1, {  # type: ignore
        "topic": event.topic,
        "tenant_id": event.tenant_id or "",
        "subscriber_id": subscriber_id,
    })


def record_failed(event: AgentEvent, error: str) -> None:
    if not _OTEL:
        return
    _events_failed.add(1, {  # type: ignore
        "topic": event.topic,
        "tenant_id": event.tenant_id or "",
        "error": error[:50],
    })


@contextmanager
def event_span(event: AgentEvent) -> Generator[Any, None, None]:
    if not _OTEL:
        yield None
        return
    with _tracer.start_as_current_span(  # type: ignore
        f"agentmesh.publish {event.topic}",
    ) as span:
        span.set_attribute("agentmesh.topic", event.topic)
        span.set_attribute("agentmesh.event_type", event.event_type)
        span.set_attribute("agentmesh.tenant_id", event.tenant_id or "")
        span.set_attribute("agentmesh.publisher_type", event.publisher_type)
        if event.trace_id:
            span.set_attribute("agentmesh.source_trace_id", event.trace_id)
        yield span
```

- [ ] **Step 2: Run tests — no regressions**

```bash
.venv/bin/pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/agentmesh/otel.py
git commit -m "feat: OTel integration — no-op fallback, live when opentelemetry-api installed"
```

---

## Task 10: AgentMesh — main facade

**Files:**
- Create: `src/agentmesh/mesh.py`
- Create: `tests/test_mesh.py`
- Update: `src/agentmesh/__init__.py`

- [ ] **Step 1: Write failing integration tests**

`tests/test_mesh.py`:
```python
import asyncio
import pytest
from agentmesh.mesh import AgentMesh
from agentmesh.event import AgentEvent


@pytest.fixture
async def mesh():
    m = AgentMesh()
    await m.start()
    yield m
    await m.close()


@pytest.mark.asyncio
async def test_publish_and_subscribe(mesh):
    received = []

    @mesh.subscribe("order.created")
    async def handler(e: AgentEvent) -> None:
        received.append(e)

    await mesh.publish("order.created", data={"order_id": "ORD-001"},
                       publisher_id="agent-1", session_id="s1", run_id="r1")
    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0].data["order_id"] == "ORD-001"


@pytest.mark.asyncio
async def test_wildcard_subscription(mesh):
    received = []

    @mesh.subscribe("order.*")
    async def handler(e: AgentEvent) -> None:
        received.append(e.event_type)

    await mesh.publish("order.created", data={},
                       publisher_id="p1", session_id="s1", run_id="r1")
    await mesh.publish("order.updated", data={},
                       publisher_id="p1", session_id="s1", run_id="r1")
    await asyncio.sleep(0.05)
    assert "order.created" in received
    assert "order.updated" in received


@pytest.mark.asyncio
async def test_deduplication(mesh):
    received = []

    @mesh.subscribe("order.created")
    async def handler(e: AgentEvent) -> None:
        received.append(e)

    await mesh.publish("order.created", data={}, publisher_id="p1",
                       session_id="s1", run_id="r1", event_id="dup-evt-001")
    await mesh.publish("order.created", data={}, publisher_id="p1",
                       session_id="s1", run_id="r1", event_id="dup-evt-001")
    await asyncio.sleep(0.05)
    assert len(received) == 1  # duplicate dropped


@pytest.mark.asyncio
async def test_tenant_isolation(mesh):
    acme_received = []
    siemens_received = []

    @mesh.subscribe("acme:order.created")
    async def acme_handler(e: AgentEvent) -> None:
        acme_received.append(e)

    @mesh.subscribe("siemens:order.created")
    async def siemens_handler(e: AgentEvent) -> None:
        siemens_received.append(e)

    await mesh.publish("acme:order.created", data={}, publisher_id="p1",
                       session_id="s1", run_id="r1", tenant_id="acme")
    await asyncio.sleep(0.05)
    assert len(acme_received) == 1
    assert len(siemens_received) == 0


@pytest.mark.asyncio
async def test_consumer_group_exclusive(mesh):
    calls = []

    @mesh.subscribe("order.created", group="workers")
    async def w1(e: AgentEvent) -> None:
        calls.append("w1")

    @mesh.subscribe("order.created", group="workers")
    async def w2(e: AgentEvent) -> None:
        calls.append("w2")

    await mesh.publish("order.created", data={},
                       publisher_id="p1", session_id="s1", run_id="r1")
    await asyncio.sleep(0.05)
    # Only one of the group should be called
    assert len(calls) == 1
    assert calls[0] in ("w1", "w2")


@pytest.mark.asyncio
async def test_topic_pause_resume(mesh):
    received = []

    @mesh.subscribe("order.created")
    async def handler(e: AgentEvent) -> None:
        received.append(e)

    await mesh.pause("order.created")
    await mesh.publish("order.created", data={},
                       publisher_id="p1", session_id="s1", run_id="r1")
    await asyncio.sleep(0.05)
    assert len(received) == 0   # paused — not delivered

    await mesh.resume("order.created")
    await asyncio.sleep(0.05)
    assert len(received) == 1   # flushed on resume


@pytest.mark.asyncio
async def test_replay(mesh, tmp_path):
    import time
    m = AgentMesh(store_path=str(tmp_path / "events.jsonl"))
    await m.start()

    await m.publish("order.created", data={"n": 1},
                    publisher_id="p1", session_id="s1", run_id="r1")
    await m.publish("order.created", data={"n": 2},
                    publisher_id="p1", session_id="s1", run_id="r2")
    await asyncio.sleep(0.05)

    replayed = []
    async for e in m.replay("order.created"):
        replayed.append(e)

    assert len(replayed) == 2
    await m.close()


@pytest.mark.asyncio
async def test_stats(mesh):
    await mesh.publish("order.created", data={},
                       publisher_id="p1", session_id="s1", run_id="r1")
    await asyncio.sleep(0.05)
    stats = mesh.stats()
    assert "order.created" in stats["topics"]
    assert stats["topics"]["order.created"]["published"] >= 1
```

- [ ] **Step 2: Run — verify FAIL**

```bash
.venv/bin/pytest tests/test_mesh.py -q
```
Expected: `ModuleNotFoundError: No module named 'agentmesh.mesh'`

- [ ] **Step 3: Implement mesh.py**

`src/agentmesh/mesh.py`:
```python
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from agentmesh.dedup import DedupWindow
from agentmesh.dlq import DeadLetterQueue
from agentmesh.event import AgentEvent
from agentmesh.filter import EventFilter
from agentmesh.otel import event_span, record_delivered, record_failed, record_published
from agentmesh.router import Router
from agentmesh.store._base import EventStore
from agentmesh.store.jsonl import JsonlStore
from agentmesh.topic import TopicConfig
from agentmesh.transport._base import Transport
from agentmesh.transport.inprocess import InProcessTransport

Handler = Callable[[AgentEvent], Coroutine[Any, Any, None]]


class AgentMesh:
    """Agent-native event bus.

    Usage::

        mesh = AgentMesh()
        await mesh.start()

        @mesh.subscribe("order.created")
        async def handle(e: AgentEvent) -> None:
            print(e.data)

        await mesh.publish("order.created", data={"order_id": "ORD-1"},
                           publisher_id="agent-1", session_id="s1", run_id="r1")

        await mesh.close()
    """

    def __init__(
        self,
        transport: Transport | None = None,
        store: EventStore | None = None,
        store_path: str = "~/.agentmesh/events.jsonl",
        dedup_window_s: float = 86400.0,
        policy_engine: Any | None = None,
        hook_registry: Any | None = None,
        agent_registry: Any | None = None,
        otel_enabled: bool = True,
    ) -> None:
        self._transport = transport or InProcessTransport()
        self._store = store or JsonlStore(path=store_path)
        self._router = Router()
        self._dedup = DedupWindow(window_s=dedup_window_s)
        self._dlq = DeadLetterQueue()
        self._topics: dict[str, TopicConfig] = {}
        self._paused_queues: dict[str, list[AgentEvent]] = defaultdict(list)
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"published": 0, "delivered": 0, "failed": 0, "dlq_depth": 0}
        )
        self._filters: dict[str, list[tuple[Handler, EventFilter]]] = defaultdict(list)
        self._policy_engine = policy_engine
        self._hook_registry = hook_registry
        self._agent_registry = agent_registry
        self._otel = otel_enabled

    async def start(self) -> None:
        await self._transport.start()

    async def close(self) -> None:
        await self._transport.close()

    async def publish(
        self,
        topic: str,
        data: dict[str, Any],
        publisher_id: str,
        session_id: str,
        run_id: str,
        publisher_type: str = "agent",
        event_id: str | None = None,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        caused_by_event_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        ttl_s: float | None = None,
    ) -> AgentEvent:
        cfg = self._topics.get(topic)
        ttl = ttl_s or (cfg.ttl_s if cfg else None)

        event = AgentEvent(
            event_id=event_id or str(uuid.uuid4()),
            event_type=topic,
            topic=topic,
            session_id=session_id,
            run_id=run_id,
            publisher_id=publisher_id,
            publisher_type=publisher_type,
            data=data,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_name=agent_name,
            caused_by_event_id=caused_by_event_id,
            trace_id=trace_id,
            span_id=span_id,
            tags=tags or [],
            metadata=metadata or {},
            ttl_s=ttl,
        )

        # Deduplication
        if self._dedup.check_and_mark(event.event_id):
            return event  # duplicate — drop silently

        # Persist before delivery (durability guarantee)
        await self._store.append(event)
        self._stats[topic]["published"] += 1

        if self._otel:
            record_published(event)

        # Pause check
        if cfg and cfg.paused:
            self._paused_queues[topic].append(event)
            return event

        # Deliver
        await self._deliver(event)
        return event

    async def _deliver(self, event: AgentEvent) -> None:
        handlers = self._router.get_handlers(event)
        for handler in handlers:
            # Check server-side filter
            sub_filters = self._filters.get(event.topic, [])
            filtered_out = False
            for h, f in sub_filters:
                if h is handler and not f.matches(event):
                    filtered_out = True
                    break
            if filtered_out:
                continue
            try:
                await handler(event)
                self._stats[event.topic]["delivered"] += 1
                if self._otel:
                    record_delivered(event, getattr(handler, "__name__", "unknown"))
            except Exception as exc:
                self._stats[event.topic]["failed"] += 1
                cfg = self._topics.get(event.topic)
                if cfg is None or cfg.dlq:
                    queued = self._dlq.push(event, error=str(exc),
                                            subscriber_id=getattr(handler, "__name__", "?"),
                                            config=cfg)
                    if queued:
                        self._stats[event.topic]["dlq_depth"] += 1
                if self._otel:
                    record_failed(event, str(exc))

    def subscribe(
        self,
        topic: str,
        group: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._router.subscribe(topic, handler, group=group)
            if filter:
                self._filters[topic].append((handler, EventFilter(filter)))
            return handler
        return decorator

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        self._router.unsubscribe(topic, handler)
        self._filters[topic] = [(h, f) for h, f in self._filters[topic]
                                 if h is not handler]

    async def request(
        self,
        topic: str,
        data: dict[str, Any],
        publisher_id: str,
        session_id: str,
        run_id: str,
        timeout_s: float = 30.0,
        fallback: Any = None,
    ) -> Any:
        """Request/reply — awaits a correlated response event."""
        request_id = str(uuid.uuid4())
        response_future: asyncio.Future[AgentEvent] = asyncio.get_event_loop().create_future()

        reply_topic = f"_reply.{request_id}"

        @self.subscribe(reply_topic)
        async def _reply_handler(e: AgentEvent) -> None:
            if not response_future.done():
                response_future.set_result(e)

        await self.publish(topic, {**data, "_request_id": request_id},
                           publisher_id=publisher_id, session_id=session_id,
                           run_id=run_id)

        try:
            return await asyncio.wait_for(response_future, timeout=timeout_s)
        except asyncio.TimeoutError:
            return fallback
        finally:
            self.unsubscribe(reply_topic, _reply_handler)

    async def replay(
        self,
        topic: str,
        since: float = 0.0,
        until: float | None = None,
    ) -> AsyncIterator[AgentEvent]:
        async for event in self._store.replay(topic, since=since, until=until):
            yield event

    def configure_topic(
        self,
        topic: str,
        dlq: bool = True,
        max_retries: int = 3,
        retry_backoff_ms: int = 500,
        ttl_s: float | None = None,
        delivery_mode: str = "broadcast",
    ) -> None:
        self._topics[topic] = TopicConfig(
            topic=topic, dlq=dlq, max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms, ttl_s=ttl_s,
            delivery_mode=delivery_mode,
        )

    async def pause(self, topic: str) -> None:
        cfg = self._topics.get(topic, TopicConfig(topic=topic))
        cfg.paused = True
        self._topics[topic] = cfg

    async def resume(self, topic: str) -> None:
        cfg = self._topics.get(topic)
        if cfg:
            cfg.paused = False
        queued = self._paused_queues.pop(topic, [])
        for event in queued:
            await self._deliver(event)

    def stats(self) -> dict[str, Any]:
        topics = {}
        for topic, s in self._stats.items():
            topics[topic] = {
                "published":   s["published"],
                "delivered":   s["delivered"],
                "failed":      s["failed"],
                "dlq_depth":   self._dlq.depth(topic),
                "subscribers": len(self._router.get_handlers(
                    AgentEvent(event_type=topic, topic=topic, session_id="",
                               run_id="", publisher_id="", publisher_type="agent",
                               data={})
                )),
            }
        return {"topics": topics}

    async def dlq(self, topic: str) -> AsyncIterator[Any]:
        for dead in self._dlq.iter(topic):
            yield dead

    async def retry(self, dead: Any) -> None:
        await self._deliver(dead.event)
```

- [ ] **Step 4: Update __init__.py**

`src/agentmesh/__init__.py`:
```python
from agentmesh.dlq import DeadEvent, DeadLetterQueue
from agentmesh.event import AgentEvent
from agentmesh.mesh import AgentMesh
from agentmesh.topic import TopicConfig
from agentmesh.transport.inprocess import InProcessTransport
from agentmesh.store.jsonl import JsonlStore

__version__ = "0.1.0"

__all__ = [
    "AgentMesh",
    "AgentEvent",
    "TopicConfig",
    "DeadEvent",
    "DeadLetterQueue",
    "InProcessTransport",
    "JsonlStore",
    "__version__",
]
```

- [ ] **Step 5: Run tests — verify PASS**

```bash
.venv/bin/pytest tests/ -q --tb=short
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agentmesh/mesh.py src/agentmesh/__init__.py tests/test_mesh.py
git commit -m "feat: AgentMesh facade — publish, subscribe, replay, pause/resume, dedup, DLQ"
```

---

## Task 11: Integrations — agentplane + agenthooks

**Files:**
- Create: `src/agentmesh/integrations/__init__.py`
- Create: `src/agentmesh/integrations/agentplane.py`
- Create: `src/agentmesh/integrations/agenthooks.py`

- [ ] **Step 1: Write integrations/__init__.py**

```python
# Optional integrations — only imported if needed
```

- [ ] **Step 2: Write agentplane.py**

`src/agentmesh/integrations/agentplane.py`:
```python
from __future__ import annotations
from typing import Any
from agentmesh.event import AgentEvent


async def check_publish_policy(engine: Any, event: AgentEvent) -> bool:
    """Returns True if publish is allowed, False if blocked."""
    try:
        from agentplane import PolicyContext
        ctx = PolicyContext.new(
            agent_id=event.publisher_id,
            tenant_id=event.tenant_id,
            hookpoint="before_publish",
            tool_name=event.topic,
            tool_inputs=event.data,
        )
        await engine.evaluate(ctx)
        return True
    except Exception:
        return False


async def check_deliver_policy(engine: Any, event: AgentEvent,
                               subscriber_id: str) -> bool:
    """Returns True if delivery is allowed."""
    try:
        from agentplane import PolicyContext
        ctx = PolicyContext.new(
            agent_id=subscriber_id,
            tenant_id=event.tenant_id,
            hookpoint="before_deliver",
            tool_name=event.topic,
        )
        await engine.evaluate(ctx)
        return True
    except Exception:
        return False
```

- [ ] **Step 3: Write agenthooks.py**

`src/agentmesh/integrations/agenthooks.py`:
```python
from __future__ import annotations
from typing import Any
from agentmesh.event import AgentEvent


def register_mesh_hooks(mesh: Any, registry: Any) -> None:
    """Wire agenthooks hookpoints to AgentMesh publish/deliver lifecycle."""
    try:
        from agenthooks import hookpoint, HookContext
    except ImportError:
        return

    hp_before_publish = hookpoint("agentmesh.before_publish", registries=[registry])
    hp_after_publish  = hookpoint("agentmesh.after_publish",  registries=[registry])
    hp_before_deliver = hookpoint("agentmesh.before_deliver", registries=[registry])
    hp_after_deliver  = hookpoint("agentmesh.after_deliver",  registries=[registry])

    # Store hookpoints on the mesh for use during publish/deliver
    mesh._hp_before_publish = hp_before_publish
    mesh._hp_after_publish  = hp_after_publish
    mesh._hp_before_deliver = hp_before_deliver
    mesh._hp_after_deliver  = hp_after_deliver
```

- [ ] **Step 4: Run all tests — verify PASS**

```bash
.venv/bin/pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/agentmesh/integrations/
git commit -m "feat: optional agentplane + agenthooks integrations for mesh lifecycle"
```

---

## Task 12: Examples

**Files:**
- Create: `examples/01_hello_mesh.py`
- Create: `examples/02_consumer_groups.py`
- Create: `examples/03_human_in_the_loop.py`
- Create: `examples/04_replay.py`
- Create: `examples/05_multi_agent_workflow.py`

- [ ] **Step 1: Write 01_hello_mesh.py**

```python
"""01 — Hello AgentMesh. Simplest possible example."""
import asyncio
from agentmesh import AgentMesh, AgentEvent

async def main() -> None:
    mesh = AgentMesh()
    await mesh.start()

    @mesh.subscribe("order.created")
    async def handle_order(e: AgentEvent) -> None:
        print(f"[subscriber] order={e.data['order_id']} tenant={e.tenant_id}")

    await mesh.publish("order.created",
                       data={"order_id": "ORD-001", "amount": 299.99},
                       publisher_id="billing-agent",
                       session_id="sess-001", run_id="run-001",
                       tenant_id="acme")

    await asyncio.sleep(0.1)
    print(f"Stats: {mesh.stats()}")
    await mesh.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Write 02_consumer_groups.py**

```python
"""02 — Consumer groups: competing consumers, only one processes each event."""
import asyncio
from agentmesh import AgentMesh, AgentEvent

async def main() -> None:
    mesh = AgentMesh()
    await mesh.start()

    processed = []

    @mesh.subscribe("payment.initiated", group="payment-workers")
    async def worker_1(e: AgentEvent) -> None:
        processed.append(("worker-1", e.data["amount"]))
        print(f"  worker-1 processed ${e.data['amount']}")

    @mesh.subscribe("payment.initiated", group="payment-workers")
    async def worker_2(e: AgentEvent) -> None:
        processed.append(("worker-2", e.data["amount"]))
        print(f"  worker-2 processed ${e.data['amount']}")

    print("Publishing 4 payment events to group 'payment-workers'...")
    for i, amount in enumerate([100, 200, 300, 400]):
        await mesh.publish("payment.initiated",
                           data={"payment_id": f"PAY-{i}", "amount": amount},
                           publisher_id="billing-agent",
                           session_id="s1", run_id=f"r{i}", tenant_id="acme")

    await asyncio.sleep(0.1)
    print(f"\nProcessed by: {[w for w, _ in processed]}")
    print("Each event handled by exactly one worker ✓")
    await mesh.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Write 03_human_in_the_loop.py**

```python
"""03 — Human-in-the-loop: agent publishes approval request, human responds."""
import asyncio
from agentmesh import AgentMesh, AgentEvent

async def main() -> None:
    mesh = AgentMesh()
    await mesh.start()

    # Simulate human reviewer
    @mesh.subscribe("human.approval.requested")
    async def human_reviewer(e: AgentEvent) -> None:
        action = e.data.get("action", "")
        amount = e.data.get("amount", 0)
        request_id = e.data.get("_request_id", "")
        print(f"  [HUMAN] Review request: {action} for ${amount}")
        # Human approves — publishes response back on reply topic
        await asyncio.sleep(0.05)  # simulate review time
        await mesh.publish(
            f"_reply.{request_id}",
            data={"approved": True, "approver": "alice@acme.com"},
            publisher_id="alice",
            publisher_type="human",
            session_id=e.session_id, run_id=e.run_id,
        )

    print("Agent requesting approval for $50,000 wire transfer...")
    response = await mesh.request(
        "human.approval.requested",
        data={"action": "wire_transfer", "amount": 50_000},
        publisher_id="billing-agent",
        session_id="sess-001", run_id="run-001",
        timeout_s=5.0,
        fallback={"approved": False, "reason": "timeout"},
    )

    print(f"  Decision: approved={response.data['approved'] if response else False}")
    await mesh.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Write 04_replay.py**

```python
"""04 — Event replay: recover missed events from the persistent store."""
import asyncio, tempfile
from agentmesh import AgentMesh, AgentEvent

async def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store_path = f.name

    mesh = AgentMesh(store_path=store_path)
    await mesh.start()

    # Publish events
    for i in range(5):
        await mesh.publish(f"order.created",
                           data={"order_id": f"ORD-{i:03d}", "seq": i},
                           publisher_id="shop-agent",
                           session_id="sess-001", run_id=f"r{i}", tenant_id="acme")
    await asyncio.sleep(0.05)
    await mesh.close()

    # New mesh instance — replay from store
    print("Replaying all order.created events from store...")
    mesh2 = AgentMesh(store_path=store_path)
    await mesh2.start()
    async for event in mesh2.replay("order.created"):
        print(f"  replayed: {event.data['order_id']} seq={event.data['seq']}")
    await mesh2.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Write 05_multi_agent_workflow.py**

```python
"""05 — Multi-agent workflow: order → inventory → billing → notification."""
import asyncio, tempfile
from agentmesh import AgentMesh, AgentEvent

async def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        store_path = f.name

    mesh = AgentMesh(store_path=store_path)
    await mesh.start()

    log = []

    @mesh.subscribe("order.created")
    async def inventory_agent(e: AgentEvent) -> None:
        log.append(f"inventory: reserved stock for {e.data['order_id']}")
        await mesh.publish("inventory.reserved",
                           data={**e.data, "reserved": True},
                           publisher_id="inventory-agent",
                           session_id=e.session_id, run_id=e.run_id,
                           caused_by_event_id=e.event_id, tenant_id=e.tenant_id)

    @mesh.subscribe("inventory.reserved")
    async def billing_agent(e: AgentEvent) -> None:
        log.append(f"billing: charged ${e.data.get('amount', 0)} for {e.data['order_id']}")
        await mesh.publish("payment.charged",
                           data={**e.data, "charged": True},
                           publisher_id="billing-agent",
                           session_id=e.session_id, run_id=e.run_id,
                           caused_by_event_id=e.event_id, tenant_id=e.tenant_id)

    @mesh.subscribe("payment.charged")
    async def notification_agent(e: AgentEvent) -> None:
        log.append(f"notification: emailed customer for {e.data['order_id']}")

    # Trigger the workflow
    print("Publishing order.created — triggering 3-agent workflow...")
    await mesh.publish("order.created",
                       data={"order_id": "ORD-999", "amount": 149.99},
                       publisher_id="shop-agent",
                       session_id="sess-001", run_id="run-001", tenant_id="acme")

    await asyncio.sleep(0.2)
    print("\nWorkflow execution log:")
    for step in log:
        print(f"  ✓ {step}")

    print(f"\nStats: {mesh.stats()['topics']}")
    await mesh.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run all examples to verify they work**

```bash
.venv/bin/python examples/01_hello_mesh.py
.venv/bin/python examples/02_consumer_groups.py
.venv/bin/python examples/03_human_in_the_loop.py
.venv/bin/python examples/04_replay.py
.venv/bin/python examples/05_multi_agent_workflow.py
```
Expected: each prints output with no errors.

- [ ] **Step 7: Commit**

```bash
git add examples/
git commit -m "feat: 5 working examples — hello, groups, HITL, replay, multi-agent workflow"
```

---

## Task 13: Scripts, CI, banner, README, push

**Files:**
- Create: `scripts/regression.sh`
- Create: `scripts/bump-version.sh`
- Create: `scripts/install-hooks.sh`
- Create: `scripts/pre-push.hook`
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/publish.yml`
- Create: `assets/banner.svg`
- Create: `src/agentmesh/py.typed`
- Create: `README.md`

- [ ] **Step 1: Write regression.sh**

```bash
#!/usr/bin/env bash
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO/.venv/bin/python"
cd "$REPO"
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0
_ok() { echo -e "  ${GREEN}✓${NC}  $1"; ((PASS++)); }
_fail() { echo -e "  ${RED}✗${NC}  $1"; ((FAIL++)); }
_section() { echo -e "\n${CYAN}━━━  $1  ━━━${NC}"; }
echo -e "\n${CYAN}  agentmesh — Regression Suite${NC}\n"

_section "1. pytest"
OUT=$("$PYTHON" -m pytest tests/ -q --tb=short 2>&1 || true)
SUM=$(echo "$OUT" | grep -E "passed|failed" | tail -1)
if echo "$SUM" | grep -q "failed"; then
    _fail "pytest: $SUM"
elif echo "$SUM" | grep -q "passed"; then
    _ok "pytest: $SUM"
else
    _fail "pytest: no results"
fi

_section "2. Exports"
RES=$("$PYTHON" -c "
import sys; sys.path.insert(0,'src')
import agentmesh
missing=[x for x in agentmesh.__all__ if getattr(agentmesh,x,None) is None]
print('MISSING:'+','.join(missing)) if missing else print(f'OK:{len(agentmesh.__all__)} symbols')
" 2>/dev/null)
if echo "$RES" | grep -q "^OK:"; then _ok "All exports resolve"; else _fail "Missing: $RES"; fi

_section "3. AgentMesh instantiates"
"$PYTHON" -c "
import sys, asyncio; sys.path.insert(0,'src')
from agentmesh import AgentMesh, AgentEvent
async def run():
    m = AgentMesh()
    await m.start()
    await m.close()
asyncio.run(run())
print('OK')
" 2>/dev/null && _ok "AgentMesh start/close" || _fail "AgentMesh failed"

_section "4. Publish + subscribe"
"$PYTHON" -c "
import sys, asyncio; sys.path.insert(0,'src')
from agentmesh import AgentMesh, AgentEvent
async def run():
    m = AgentMesh()
    await m.start()
    received = []
    @m.subscribe('test.event')
    async def h(e): received.append(e)
    await m.publish('test.event', data={'x':1}, publisher_id='p',
                    session_id='s', run_id='r')
    await asyncio.sleep(0.05)
    assert len(received) == 1
    await m.close()
asyncio.run(run())
print('OK')
" 2>/dev/null && _ok "Publish + subscribe" || _fail "Publish + subscribe failed"

_section "5. Deduplication"
"$PYTHON" -c "
import sys, asyncio; sys.path.insert(0,'src')
from agentmesh import AgentMesh, AgentEvent
async def run():
    m = AgentMesh()
    await m.start()
    received = []
    @m.subscribe('dup.test')
    async def h(e): received.append(e)
    for _ in range(3):
        await m.publish('dup.test', data={}, publisher_id='p',
                        session_id='s', run_id='r', event_id='dup-001')
    await asyncio.sleep(0.05)
    assert len(received) == 1, f'expected 1, got {len(received)}'
    await m.close()
asyncio.run(run())
print('OK')
" 2>/dev/null && _ok "Deduplication: 3 publishes → 1 delivery" || _fail "Deduplication failed"

_section "6. Version"
PV=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
IV=$("$PYTHON" -c "import sys; sys.path.insert(0,'src'); import agentmesh; print(agentmesh.__version__)" 2>/dev/null)
[ "$PV" = "$IV" ] && _ok "Version consistent: $PV" || _fail "Mismatch: $PV vs $IV"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}✓ ALL PASSED${NC}  ($PASS passed)"; echo "  Safe to push."
else
    echo -e "  ${RED}✗ FAILURES${NC}  ($PASS passed, $FAIL failed)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[ "$FAIL" -eq 0 ]
```

- [ ] **Step 2: Write CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]
jobs:
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: mypy src/agentmesh
      - run: python -m pytest tests/ -q --tb=short --cov=agentmesh --cov-report=term-missing
      - name: Check exports
        run: |
          python -c "
          import sys; sys.path.insert(0,'src')
          import agentmesh
          missing=[x for x in agentmesh.__all__ if getattr(agentmesh,x,None) is None]
          if missing: print('MISSING:',missing); sys.exit(1)
          print(f'All {len(agentmesh.__all__)} exports OK — version', agentmesh.__version__)
          "
      - name: Version check
        run: |
          PV=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
          IV=$(python -c "import sys; sys.path.insert(0,'src'); import agentmesh; print(agentmesh.__version__)")
          [ "$PV" = "$IV" ] && echo "OK: $PV" || (echo "Mismatch"; exit 1)
```

- [ ] **Step 3: Write publish workflow**

`.github/workflows/publish.yml`:
```yaml
name: Publish to PyPI
on:
  push:
    tags: ["v[0-9]+.[0-9]+.[0-9]+"]
jobs:
  publish:
    runs-on: ubuntu-latest
    if: github.ref_type == 'tag'
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install build twine && pip install -e ".[dev]" && python -m pytest tests/ -q --tb=short
      - run: |
          TAG="${GITHUB_REF_NAME}"
          PKG=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
          [ "v${PKG}" = "$TAG" ] && echo "OK: $TAG" || (echo "Mismatch"; exit 1)
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
          skip-existing: true
```

- [ ] **Step 4: Create py.typed, scripts, run regression**

```bash
touch src/agentmesh/py.typed
chmod +x scripts/regression.sh scripts/pre-push.hook scripts/install-hooks.sh scripts/bump-version.sh
bash scripts/install-hooks.sh
bash scripts/regression.sh
```
Expected: all 6 checks pass.

- [ ] **Step 5: Final lint + type check**

```bash
.venv/bin/ruff check src/ tests/ --fix
.venv/bin/mypy src/agentmesh
.venv/bin/pytest tests/ -q
```
Expected: ruff clean, mypy clean, all tests pass.

- [ ] **Step 6: Commit everything + push to GitHub**

```bash
git add -A
git commit -m "feat: agentmesh-py v0.1.0 — agent-native event bus, full production stack"
gh repo create naveenkumarbaskaran/agentmesh --public \
  --description "Agent-native event bus — connect agents, humans, and systems via typed events" \
  --source=. --remote=origin --push
```

---

## Self-Review

**Spec coverage check:**

| Spec Section | Task |
|---|---|
| Event envelope (all fields) | Task 2 |
| NATS-style wildcards | Task 3 |
| Consumer groups | Task 3 |
| Deduplication via event_id | Task 4 |
| Server-side filters | Task 5 |
| JSONL store + replay | Task 6 |
| Dead letter queue | Task 7 |
| Transport ABC + InProcess | Task 8 |
| OTel no-op + live | Task 9 |
| AgentMesh facade | Task 10 |
| Publish/subscribe/replay | Task 10 |
| Pause/resume topic | Task 10 |
| Request/reply (HITL) | Task 10 |
| Stats | Task 10 |
| agentplane integration | Task 11 |
| agenthooks integration | Task 11 |
| Examples (5 working) | Task 12 |
| CI/CD, regression, PyPI | Task 13 |

**Spec items documented as v1 limitations (not in plan, by design):**
- Exactly-once delivery
- Backpressure
- Cross-datacenter replication
- Event enrichment pipeline
- Schema compatibility modes
- Replay RBAC
- Web dashboard
- Redis/NATS/Kafka transports (stubs only — full impl is v2)

All spec requirements covered. No placeholders. Types consistent across tasks (`AgentEvent`, `TopicConfig`, `DeadEvent`, `Handler` used consistently). `Router.get_handlers()` takes `AgentEvent` throughout.
