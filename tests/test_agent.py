import time
import pytest
import asyncio
from agenthooks import HookAgent, hookpoint, HookRegistry, HookContext, HookBlocked, HookWrapper

def make_ctx(**kwargs) -> HookContext:
    defaults = dict(session_id="s1", tenant_id="acme", trace_id="t1", span_id="sp1", turn=0, timestamp=time.time())
    return HookContext(**{**defaults, **kwargs})

@pytest.mark.asyncio
async def test_runs_without_registries():
    class MyAgent(HookAgent):
        before_call = hookpoint("before_call")
        async def run(self, query: str) -> str:
            ctx = HookContext.new(session_id="s1", tenant_id="demo", query=query)
            async with self.before_call.run(ctx) as ctx:
                return ctx.query

    agent = MyAgent()
    result = await agent.run("hello")
    assert result == "hello"

@pytest.mark.asyncio
async def test_applies_registry():
    class MyAgent(HookAgent):
        before_call = hookpoint("before_call")
        async def run(self, query: str) -> dict:
            ctx = HookContext.new(session_id="s1", tenant_id="demo", query=query)
            async with self.before_call.run(ctx) as ctx:
                return {"query": ctx.query, "metadata": ctx.metadata}

    registry = HookRegistry()

    @registry.implement("before_call")
    async def inject_plant(ctx: HookContext) -> HookContext:
        return ctx.enrich("plant", "1000")

    agent = MyAgent(registries=[registry])
    result = await agent.run("hello")
    assert result["metadata"]["plant"] == "1000"

@pytest.mark.asyncio
async def test_blocked_propagates():
    class MyAgent(HookAgent):
        before_call = hookpoint("before_call")
        async def run(self) -> str:
            ctx = HookContext.new(session_id="s1", tenant_id="demo")
            async with self.before_call.run(ctx) as ctx:
                return "ok"

    registry = HookRegistry()

    @registry.implement("before_call")
    async def blocker(ctx: HookContext) -> HookContext:
        raise HookBlocked("Access denied")

    agent = MyAgent(registries=[registry])
    with pytest.raises(HookBlocked, match="Access denied"):
        await agent.run()

@pytest.mark.asyncio
async def test_wrapper_wraps_callable():
    async def my_agent(inputs: dict) -> dict:
        return {"answer": inputs.get("query", ""), "processed": True}

    wrapper = HookWrapper(my_agent)
    result = await wrapper.invoke({"query": "hello"})
    assert result["processed"] is True
    assert result["answer"] == "hello"
