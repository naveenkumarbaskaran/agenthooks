# AgentMesh — Design Specification
**Version:** 1.0.0  
**Date:** 2026-06-17  
**Status:** Approved for implementation

---

## 1. Purpose

AgentMesh is a production-grade, agent-native event bus. Agents, humans, and systems publish typed events to topics. Subscribers react asynchronously. The mesh is the nervous system of a multi-agent architecture — connecting agents across process boundaries without coupling them directly.

AgentMesh is **not** a replacement for Kafka or Redis. It is an agent-native intelligence layer that can sit on top of any transport — in-process queues for development, Redis Streams for staging, Kafka for production scale. The transport is swappable. The agent-native semantics are constant.

---

## 2. Core Principles

1. **Zero-dep start.** `pip install agentmesh-py` runs in-process with no external infrastructure.
2. **Pluggable transport.** Swap in Redis, NATS, or Kafka in one line. Same API.
3. **Agent-native.** Every event carries `tenant_id`, `trace_id`, `agent_id`, `caused_by_event_id`. Kafka carries bytes. AgentMesh carries meaning.
4. **Always persistent.** Every event is stored before delivery. Full replay always available.
5. **Three publisher types.** Agents, humans, and systems are all first-class publishers.
6. **OTel-native.** Events double as OTLP span events. Works with Grafana, Datadog, Honeycomb, Jaeger out of the box.
7. **Optional integrations.** agentplane, agenthooks, agentregistry — zero-dep core, opt-in power.

---

## 3. Publisher Types

```
Agent    → automated, high-frequency
           "tool.call.started", "order.created", "llm.call.completed"

Human    → manual, deliberate, awaited
           "human.approval.granted", "human.input.received"
           A human is a first-class publisher. Their decisions are audited,
           governed, and observable like any agent event.

System   → infrastructure, operational
           "system.rate_limit.hit", "policy.breached", "connection.failed"
           The mesh itself, agentplane, agentguard all publish here.
```

---

## 4. Event Envelope

Every event — regardless of type — carries this standard envelope:

```python
@dataclass
class AgentEvent:
    # ── Identity ──────────────────────────────────────────────────────────────
    event_id:           str          # UUID. Also the idempotency key.
                                     # Set deterministically for dedup:
                                     # uuid5(namespace, order_id) for financial events.
                                     # Random UUID when dedup not needed.
    event_type:         str          # "tool.call.started" — category.entity.verb
    schema_version:     str          # "1.0" — for schema evolution

    # ── Temporal ──────────────────────────────────────────────────────────────
    timestamp:          float        # unix epoch ms

    # ── Hierarchy (execution tree reconstruction) ─────────────────────────────
    session_id:         str          # top-level agent session
    run_id:             str          # current operation UUID
    parent_run_id:      str | None   # parent operation — enables nested spans
    caused_by_event_id: str | None   # event that caused this one
                                     # chains: order.created → invoice.generated
                                     #         → email.sent — full causality

    # ── OTel compatibility ────────────────────────────────────────────────────
    trace_id:           str | None   # OTel trace ID — propagates across hops
    span_id:            str | None   # OTel span ID

    # ── Source ────────────────────────────────────────────────────────────────
    agent_id:           str | None
    agent_name:         str | None
    tenant_id:          str | None   # enforced at topic level
    publisher_type:     str          # "agent" | "human" | "system"
    publisher_id:       str          # agent_id, user_id, or service_id
    provider:           str | None   # "anthropic", "openai", "langgraph"

    # ── Routing ───────────────────────────────────────────────────────────────
    topic:              str          # "order.created" or "acme:order.created"
    delivery_mode:      str          # "broadcast" | "exclusive"
    ttl_s:              float | None # expire after N seconds

    # ── Classification ────────────────────────────────────────────────────────
    tags:               list[str]
    metadata:           dict[str, Any]

    # ── Payload ───────────────────────────────────────────────────────────────
    data:               dict[str, Any]   # event-specific fields (see taxonomy)
```

---

## 5. Topic Naming

### Convention
```
{category}.{entity}.{verb}

order.created
order.payment.failed
agent.tool.call.started
llm.response.completed
human.approval.granted
system.rate_limit.hit
```

### Tenant namespacing
Topics are globally scoped by default. For tenant isolation, prefix with tenant:

```
acme:order.created       # only ACME agents see this
siemens:order.created    # only Siemens agents see this
order.created            # global — all tenants (use carefully)
```

The mesh enforces tenant prefixes via `tenant_id` on the event — a publisher with `tenant_id="acme"` cannot publish to `siemens:*` topics. agentplane governs cross-tenant access.

---

## 6. Event Taxonomy — 14 Categories

### 6.1 `session.*` — Agent session lifecycle
```
session.started           session_id, agent_id, agent_name, config, parent_session_id?
session.completed         session_id, duration_ms, token_usage
session.failed            session_id, error_type, error_message, partial_output?
session.cancelled         session_id, cancellation_reason
session.paused            session_id, pause_reason, resume_hint
session.resumed           session_id, resume_data
```

### 6.2 `llm.*` — LLM inference
```
llm.call.started          run_id, model, provider, messages[], tools[]?,
                          temperature?, max_tokens?, stream: bool
llm.call.streaming        run_id, chunk_index, delta_text?, delta_tool_args?
llm.call.completed        run_id, model, stop_reason, output_messages[],
                          usage: {input_tokens, output_tokens,
                                  cache_read_tokens, cache_write_tokens,
                                  reasoning_tokens}
llm.call.failed           run_id, error_type, error_message, retryable: bool
llm.thinking.started      run_id, thinking_budget?
llm.thinking.streaming    run_id, thinking_delta
llm.thinking.completed    run_id, thinking_summary?, signature?
llm.prompt.rendered       run_id, rendered_prompt, function_name
```

### 6.3 `tool.*` — Tool/function execution
```
tool.call.requested       run_id, tool_call_id, tool_name, arguments, model_turn_id
tool.call.started         run_id, tool_call_id, tool_name, arguments, timeout?
tool.call.streaming       run_id, tool_call_id, chunk
tool.call.completed       run_id, tool_call_id, tool_name, result, duration_ms
tool.call.failed          run_id, tool_call_id, tool_name, error_type, error_message
tool.validation.failed    run_id, tool_name, validation_errors[]
tool.selection.failed     run_id, attempted_tool, error_message
tool.list.changed         session_id, added_tools[], removed_tools[]
```

### 6.4 `memory.*` — Memory read/write
```
memory.write.started      session_id, store_id, value, metadata
memory.write.completed    session_id, store_id, record_id, duration_ms
memory.write.failed       session_id, store_id, error_message
memory.query.started      session_id, store_id, query, limit, score_threshold?
memory.query.completed    session_id, store_id, results[], duration_ms
memory.query.failed       session_id, store_id, error_message
memory.retrieval.started  session_id, task_id?
memory.retrieval.completed session_id, task_id, content, duration_ms
```

### 6.5 `retrieval.*` — RAG / knowledge search
```
retrieval.started         run_id, query, data_source_id, top_k?
retrieval.streaming       run_id, chunk: Document[]
retrieval.completed       run_id, documents[], duration_ms, data_source_id
retrieval.failed          run_id, query, error_message
```

### 6.6 `human.*` — Human-in-the-loop
```
human.input.requested     session_id, request_id, prompt,
                          possible_outcomes[]?, timeout_s?
human.input.received      session_id, request_id, response, outcome?
human.approval.requested  session_id, request_id, action_description,
                          action_payload, risk_level?, timeout_s?
human.approval.granted    session_id, request_id, approver_id?,
                          modified_payload?
human.approval.denied     session_id, request_id, reason?
human.escalation.triggered session_id, escalation_reason, context_snapshot
```

Note: `human.input.requested` and `human.approval.requested` use **request/reply** pattern — the publisher awaits a correlated response event matched by `request_id`. All other events are fire-and-forget pub/sub.

### 6.7 `agent.*` — Agent reasoning and planning
```
agent.reasoning.started   session_id, agent_id, task_id, attempt_number
agent.reasoning.completed session_id, agent_id, plan, ready_to_execute: bool
agent.reasoning.failed    session_id, agent_id, error_message
agent.step.started        session_id, agent_id, step_number, step_description
agent.step.completed      session_id, step_number, key_info, replan_needed: bool
agent.step.failed         session_id, step_number, error_message
agent.plan.refined        session_id, refined_steps_count, refinements[]
agent.plan.replanned      session_id, replan_reason, replan_count
agent.goal.achieved       session_id, remaining_steps, completed_steps
agent.evaluation.started  session_id, agent_id, task_id, iteration_number
agent.evaluation.completed session_id, metric_category, score, details
```

### 6.8 `multiagent.*` — Agent-to-agent coordination
```
multiagent.delegation.started   session_id, delegator_id, delegate_id,
                                delegate_endpoint?, task_description, context_id
multiagent.delegation.completed session_id, context_id, status, result
multiagent.delegation.failed    session_id, context_id, error_message
multiagent.message.sent         session_id, from_agent_id, to_agent_id,
                                message_id, content, turn_number
multiagent.message.received     session_id, from_agent_id, to_agent_id,
                                message_id, content, final_response: bool
multiagent.handoff.requested    session_id, from_agent_id, target_agent_id, context
multiagent.handoff.completed    session_id, from_agent_id, target_agent_id
multiagent.broadcast            session_id, from_agent_id, recipient_ids[], content
multiagent.streaming.started    session_id, task_id, context_id, turn_number
multiagent.streaming.chunk      session_id, task_id, chunk_text, chunk_index, is_final
multiagent.context.created      context_id, created_at
multiagent.context.completed    context_id, total_tasks, duration_ms
multiagent.context.expired      context_id, age_ms, task_count
multiagent.artifact.produced    session_id, task_id, artifact_id, name, mime_type
```

### 6.9 `connection.*` — External service connections
```
connection.established      connection_id, service_type, service_name,
                            endpoint_url, transport
connection.ready            connection_id, service_name, capabilities,
                            protocol_version
connection.failed           connection_id, service_name, endpoint,
                            error_type, error_message, http_status?
connection.closed           connection_id, service_name, reason
connection.auth.failed      connection_id, endpoint, auth_type, http_status
connection.transport.negotiated connection_id, negotiated_transport
```

### 6.10 `resource.*` — MCP resources
```
resource.read.started       connection_id, uri, mime_type?
resource.read.completed     connection_id, uri, content_type, size_bytes
resource.list.changed       connection_id, server_name
resource.updated            connection_id, uri
resource.subscribed         connection_id, uri
```

### 6.11 `guardrail.*` — Safety and policy enforcement
```
guardrail.check.started     session_id, run_id, guardrail_name,
                            guardrail_type, retry_count
guardrail.check.passed      session_id, guardrail_name, validation_result
guardrail.check.failed      session_id, guardrail_name, failure_reason,
                            violations[], retry_count
guardrail.check.error       session_id, guardrail_name, error_message
```

Note: `guardrail.check.started` supports **pre-emption** — a subscriber can inject a rejection before the operation completes. This is how AgentGuard and agentplane hook into the mesh.

### 6.12 `flow.*` — Orchestration and workflow
```
flow.started                flow_id, flow_name, initial_state
flow.completed              flow_id, final_state, duration_ms
flow.method.started         flow_id, method_name, inputs
flow.method.completed       flow_id, method_name, outputs, duration_ms
flow.method.failed          flow_id, method_name, error_message
flow.method.paused          flow_id, method_name, current_state,
                            feedback_message, possible_outcomes[]
flow.state.updated          flow_id, previous_state, new_state, trigger
```

### 6.13 `system.*` — Infrastructure and operational
```
system.heartbeat            service_id, timestamp
system.rate_limit.hit       service_id, endpoint, retry_after_ms, limit_type
system.timeout              session_id, run_id, operation, timeout_ms
system.max_iterations       session_id, iteration_count, limit
system.token_limit          session_id, tokens_used, token_limit
system.log                  level, message, component, session_id?
system.error                error_type, error_message, component, session_id?
system.capability.changed   service_id, added[], removed[]
```

### 6.14 `push.*` — Async webhook delivery
```
push.registered             task_id, context_id, callback_url
push.sent                   task_id, context_id, callback_url,
                            state, delivery_success
push.received               task_id, context_id, state
push.timeout                task_id, context_id, timeout_ms
```

---

## 7. Core API

```python
# ── Create mesh ───────────────────────────────────────────────────────────────
mesh = AgentMesh()                                    # in-process, zero deps
mesh = AgentMesh(transport=RedisTransport("redis://localhost"))
mesh = AgentMesh(transport=KafkaTransport(brokers=["kafka:9092"]))

# ── Publish ───────────────────────────────────────────────────────────────────
event = await mesh.publish(
    topic="order.created",
    data={"order_id": "ORD-001", "amount": 299.99},
    agent_id="billing-agent",
    tenant_id="acme",
    caused_by_event_id="evt-abc123",   # causality chain
    event_id=str(uuid5(...)),          # deterministic = dedup
)

# ── Subscribe — broadcast (all subscribers get every event) ───────────────────
@mesh.subscribe("order.created")
async def handle_order(event: AgentEvent) -> None:
    print(f"Order {event.data['order_id']}")

# ── Subscribe — exclusive consumer group (one subscriber per event) ───────────
@mesh.subscribe("order.created", group="billing-workers")
async def bill_order(event: AgentEvent) -> None:
    await billing.charge(event.data)

# ── Subscribe — NATS-style wildcard ──────────────────────────────────────────
@mesh.subscribe("order.*")             # all order events
@mesh.subscribe("*.failed")            # every failure
@mesh.subscribe("acme:>")             # everything for acme tenant
@mesh.subscribe("tool.*.failed")       # all tool failures

# ── Subscribe — server-side filter (evaluated before delivery) ────────────────
@mesh.subscribe(
    "order.created",
    filter={"data.amount": {"$gt": 1000}, "tenant_id": "acme"},
)
async def big_orders(event: AgentEvent) -> None:
    ...

# ── Request/reply (human-in-the-loop) ────────────────────────────────────────
response = await mesh.request(
    topic="human.approval.requested",
    data={"action": "wire_transfer", "amount": 50000},
    timeout_s=300.0,    # 5 minutes for human to respond
    fallback="deny",    # if timeout: auto-deny
)

# ── Replay ────────────────────────────────────────────────────────────────────
async for event in mesh.replay("order.created", since=time.time() - 86400):
    print(event)

async for event in mesh.replay("order.created", since=0, until=time.time()):
    print(event)   # full history

# ── Topic control ─────────────────────────────────────────────────────────────
mesh.configure_topic(
    "order.created",
    dlq=True,
    max_retries=3,
    retry_backoff_ms=500,
    ttl_s=86400,         # events expire after 24h
    delivery_mode="broadcast",
)

await mesh.pause("payment.initiated")    # queue events, halt delivery
await mesh.resume("payment.initiated")  # flush queue, resume

# ── DLQ ───────────────────────────────────────────────────────────────────────
async for dead in mesh.dlq("payment.initiated"):
    print(dead.error, dead.attempts)
    await mesh.retry(dead)

# ── Mesh health ───────────────────────────────────────────────────────────────
stats = mesh.stats()
# {
#   "topics": {"order.created": {"published": 1420, "delivered": 1418,
#                                "dlq_depth": 2, "subscribers": 3}},
#   "latency_p99_ms": 4.2,
#   "events_per_sec": 340,
# }
```

---

## 8. Transport Layer

```python
class Transport(ABC):
    async def publish(self, topic: str, event: AgentEvent) -> None: ...
    async def subscribe(self, topic: str, group: str | None,
                        handler: Callable) -> None: ...
    async def unsubscribe(self, topic: str, group: str | None) -> None: ...
    async def close(self) -> None: ...

# Built-in transports
InProcessTransport()                         # default, asyncio queues, zero deps
RedisTransport(url="redis://...")            # pip install agentmesh-py[redis]
NATSTransport(url="nats://...")             # pip install agentmesh-py[nats]
KafkaTransport(brokers=["kafka:9092"])       # pip install agentmesh-py[kafka]
```

**Transport capability matrix:**

| Feature | InProcess | Redis | NATS | Kafka |
|---|---|---|---|---|
| Wildcard subscriptions | ✓ | partial | ✓ | ✓ |
| Consumer groups | ✓ | ✓ | ✓ | ✓ |
| Persistence | JSONL | Redis Streams | JetStream | Log segments |
| Replay | ✓ | ✓ | ✓ | ✓ |
| Cross-process | ✗ | ✓ | ✓ | ✓ |
| Ordering guarantee | ✓ | per-stream | per-subject | per-partition |
| At-least-once | ✓ | ✓ | ✓ | ✓ |
| Zero infra | ✓ | ✗ | ✗ | ✗ |

---

## 9. Event Store

Always-on persistence. Every event written to store before delivery.

```python
class EventStore(ABC):
    async def append(self, event: AgentEvent) -> None: ...
    async def get(self, event_id: str) -> AgentEvent | None: ...
    async def replay(self, topic: str, since: float,
                     until: float | None = None,
                     filter: dict | None = None) -> AsyncIterator[AgentEvent]: ...
    async def delete_expired(self) -> int: ...    # TTL GC

# Built-in stores
JsonlStore(path="~/.agentmesh/events.jsonl")     # default, zero deps
SqliteStore(path="~/.agentmesh/events.db")       # pip install agentmesh-py[sqlite]
RedisStore(url="redis://...")                     # pip install agentmesh-py[redis]
```

---

## 10. Dead Letter Queue

```python
@dataclass
class DeadEvent:
    event: AgentEvent
    error: str
    attempts: int
    last_attempt_at: float
    subscriber_id: str

# Per-topic DLQ config
mesh.configure_topic("payment.initiated",
    dlq=True,
    max_retries=3,
    retry_backoff_ms=500,   # exponential: 500ms, 1s, 2s
)

# Fire-and-forget topics (no DLQ)
mesh.configure_topic("system.heartbeat", dlq=False)
```

---

## 11. Idempotency and Deduplication

`event_id` is the idempotency key. The mesh maintains a dedup window (default 24h):

```python
# Deterministic event_id for financial events — safe to retry
import uuid
order_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"order.created:{order_id}"))

await mesh.publish("order.created", data={...}, event_id=order_event_id)
# Publishing again with the same event_id → silently dropped
```

---

## 12. OTel Integration

Every `*.started` → `*.completed` pair maps to an OTel span automatically:

```python
mesh = AgentMesh(otel_enabled=True)   # default True if opentelemetry-api installed

# Emits to configured OTel exporter:
# → Grafana (via OTLP)
# → Datadog
# → Honeycomb
# → Jaeger
# → Any OTLP-compatible backend

# Same pattern as agentplane/agenthooks — zero vendor coupling
```

Span attributes follow OTel GenAI semantic conventions:
- `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`
- `agentmesh.topic`, `agentmesh.event_type`, `agentmesh.tenant_id`
- `agentmesh.publisher_type`, `agentmesh.delivery_mode`

---

## 13. Optional Integrations

All integrations are zero-dep unless opted in:

```python
# agentplane — policy enforcement on publish and delivery
mesh = AgentMesh(policy_engine=engine)
# Before publish: evaluates policy → can block event
# Before deliver: evaluates policy → can filter subscriber

# agenthooks — hook points on mesh operations
mesh = AgentMesh(hook_registry=registry)
# Hookpoints: before_publish, after_publish,
#             before_deliver, after_deliver,
#             on_dlq, on_replay

# agentregistry — auto-discover subscribers from registry
mesh = AgentMesh(agent_registry=registry)
# Agents that declare event capabilities in their manifest
# are automatically subscribed to matching topics

# Combined
mesh = AgentMesh(
    transport=RedisTransport("redis://localhost"),
    policy_engine=engine,
    hook_registry=registry,
    agent_registry=registry,
    otel_enabled=True,
)
```

---

## 14. Mesh-Level Metrics

AgentMesh emits its own operational metrics via OTel:

```
agentmesh.events.published      Counter   {topic, tenant_id, publisher_type}
agentmesh.events.delivered      Counter   {topic, tenant_id, subscriber_id}
agentmesh.events.failed         Counter   {topic, tenant_id, error_type}
agentmesh.events.dlq            Counter   {topic}
agentmesh.delivery.latency_ms   Histogram {topic, subscriber_id}
agentmesh.store.size_bytes      Gauge     {topic}
agentmesh.dlq.depth             Gauge     {topic}
agentmesh.replay.lag_ms         Histogram {topic}
agentmesh.subscribers.active    Gauge     {topic}
```

Visible in Grafana, Datadog, Prometheus — same OTel pipeline, zero extra config.

---

## 15. Framework Adapters

Thin adapters translate framework-native events into AgentMesh events:

```python
# LangGraph
from agentmesh.adapters.langgraph import LangGraphAdapter
adapter = LangGraphAdapter(mesh)
# Wraps astream_events() → publishes to mesh

# CrewAI
from agentmesh.adapters.crewai import CrewAIAdapter
adapter = CrewAIAdapter(mesh)
# Listens to CrewAI event bus → republishes to mesh

# Anthropic
from agentmesh.adapters.anthropic import AnthropicAdapter
adapter = AnthropicAdapter(mesh)
# Wraps streaming SSE → publishes llm.* events

# OpenAI
from agentmesh.adapters.openai import OpenAIAdapter
adapter = OpenAIAdapter(mesh)
```

---

## 16. Repo Structure

```
agentmesh/
├── src/agentmesh/
│   ├── __init__.py          # AgentMesh, AgentEvent, exports
│   ├── mesh.py              # AgentMesh — main entry point
│   ├── event.py             # AgentEvent dataclass
│   ├── router.py            # topic → subscriber routing, wildcards
│   ├── dedup.py             # idempotency / deduplication window
│   ├── topic.py             # TopicConfig (DLQ, TTL, delivery mode)
│   ├── transport/
│   │   ├── _base.py         # Transport ABC
│   │   ├── inprocess.py     # asyncio queues — default
│   │   ├── redis.py         # Redis Streams
│   │   ├── nats.py          # NATS JetStream
│   │   └── kafka.py         # aiokafka
│   ├── store/
│   │   ├── _base.py         # EventStore ABC
│   │   ├── jsonl.py         # JSONL — default
│   │   ├── sqlite.py        # SQLite
│   │   └── redis.py         # Redis Streams as store
│   ├── dlq.py               # DeadLetterQueue
│   ├── replay.py            # ReplayEngine
│   ├── filter.py            # Server-side subscription filters
│   ├── schema/
│   │   ├── registry.py      # SchemaRegistry (opt-in)
│   │   └── validator.py     # payload validation
│   ├── integrations/
│   │   ├── agentplane.py    # policy enforcement
│   │   ├── agenthooks.py    # hook points
│   │   └── agentregistry.py # auto-subscribe from registry
│   ├── adapters/
│   │   ├── langgraph.py
│   │   ├── crewai.py
│   │   ├── anthropic.py
│   │   └── openai.py
│   ├── otel.py              # OTel span/metric emission
│   └── metrics.py           # mesh-level metrics
├── tests/
│   ├── test_mesh.py
│   ├── test_router.py
│   ├── test_store.py
│   ├── test_dlq.py
│   ├── test_replay.py
│   ├── test_dedup.py
│   ├── test_filter.py
│   └── test_integrations.py
├── examples/
│   ├── 01_hello_mesh.py
│   ├── 02_consumer_groups.py
│   ├── 03_human_in_the_loop.py
│   ├── 04_replay.py
│   ├── 05_multi_agent_workflow.py
│   ├── 06_redis_transport.py
│   └── 07_full_stack.py
├── scripts/
│   ├── regression.sh
│   ├── bump-version.sh
│   ├── release.sh
│   └── install-hooks.sh
├── .github/workflows/
│   ├── ci.yml
│   └── publish.yml
├── assets/banner.svg
├── pyproject.toml           # name="agentmesh-py"
├── README.md
└── .gitignore
```

**PyPI:** `agentmesh-py`

---

## 17. pyproject.toml (key sections)

```toml
[project]
name = "agentmesh-py"
version = "0.1.0"
description = "Agent-native event bus — connect agents, humans, and systems via typed events"
dependencies = []   # zero-dep core

[project.optional-dependencies]
redis   = ["redis>=5.0"]
nats    = ["nats-py>=2.0"]
kafka   = ["aiokafka>=0.10"]
sqlite  = ["aiosqlite>=0.20"]
otel    = ["opentelemetry-api>=1.20"]
all     = ["agentmesh-py[redis,nats,kafka,sqlite,otel]"]
dev     = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0",
           "ruff>=0.5", "mypy>=1.10"]
```

---

## 18. v1 Limitations (documented)

The following are known limitations of v1, intentionally deferred:

1. **Exactly-once delivery** — v1 provides at-least-once. Idempotency keys handle dedup on the consumer side. True exactly-once (Kafka transactions) is v2.

2. **Backpressure** — if a publisher outpaces subscribers, v1 buffers in-memory. For production high-volume, use Kafka transport which handles backpressure natively.

3. **Cross-datacenter replication** — v1 is single-region. Multi-region event replication (Kafka MirrorMaker pattern) is v2.

4. **Event enrichment pipeline** — v1 does not have a middleware chain for auto-enriching events before delivery (e.g. injecting geo, risk score). Use agenthooks `before_publish` as a workaround.

5. **Schema compatibility enforcement** — v1 schema registry validates against registered schemas but does not enforce backward/forward compatibility modes (Confluent-style). Teams must manage schema evolution manually.

6. **Replay access control** — v1 replay is governed by agentplane if configured, but has no built-in RBAC for replay operations. v2 will add fine-grained replay permissions.

7. **Streaming token events at scale** — `llm.call.streaming` events can be 100k+/minute per agent. v1 persists every streaming token. v2 will add optional sampling/batching for streaming events to reduce store pressure.

8. **Web dashboard** — v1 exposes metrics via OTel. A dedicated AgentMesh web dashboard (like agentobserve but mesh-specific) is v2.

---

## 19. v2 Roadmap

- Exactly-once delivery (Kafka transactions)
- Event enrichment pipeline (middleware chain)
- Schema compatibility modes (backward, forward, full)
- Multi-region replication
- Streaming event sampling/batching
- Replay RBAC
- AgentMesh web dashboard
- AgentGrid integration (routing layer on top of mesh)
- AgentPub integration (shared learning via mesh)
- WASM-based filter evaluation (server-side filters without Python)

---

## 20. Stack Position

```
AgentGrid       → routing      which agent handles what (future)
AgentPub        → learning     shared knowledge across agents (future)
─────────────────────────────────────────────────────────────────
AgentMesh       → events       connects agents, humans, systems   ← THIS
─────────────────────────────────────────────────────────────────
agentplane      → policy       governs what agents can do
agenthooks      → hooks        extends agent execution
AgentGuard      → safety       protects agent inputs/outputs
agentregistry   → discovery    finds agents
agenteval       → testing      validates agent behaviour
agentobserve    → visibility   shows what's happening
```

AgentMesh is the connective tissue. Everything else becomes observable through it.
