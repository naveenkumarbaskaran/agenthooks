"""04_resilience.py — Timeout and error isolation.

Hook failures never crash the agent. Each hook implementation runs
under a timeout budget. If it exceeds the budget or throws an exception,
the executor degrades gracefully — the agent continues with whatever
context was available before the failure.

This is the production reliability guarantee: customer hook code cannot
take down the agent.
"""
import asyncio
from agenthooks import HookAgent, hookpoint, HookRegistry, HookContext


class ResilientAgent(HookAgent):
    before_call = hookpoint("before_call")

    async def run(self, query: str) -> dict:
        ctx = HookContext.new(session_id="s1", tenant_id="demo", query=query)
        async with self.before_call.run(ctx) as ctx:
            return {
                "answer": f"Answer to: {ctx.query}",
                "enriched_with": list(ctx.metadata.keys()),
            }


registry = HookRegistry()


@registry.implement("before_call", timeout_ms=100, fallback=True, order=10)
async def slow_enrichment(ctx: HookContext) -> HookContext:
    """Simulates a slow external API call. Times out — agent continues."""
    await asyncio.sleep(2.0)
    return ctx.enrich("slow_data", "this never arrives")


@registry.implement("before_call", fallback=True, order=20)
async def unreliable_enrichment(ctx: HookContext) -> HookContext:
    """Simulates an external service that throws. Agent continues."""
    raise ConnectionError("CRM service unavailable")


@registry.implement("before_call", order=30)
async def reliable_enrichment(ctx: HookContext) -> HookContext:
    """Always succeeds — this is the only enrichment that lands."""
    return ctx.enrich("user_tier", "premium")


async def main():
    agent = ResilientAgent(registries=[registry])
    result = await agent.run("What is my account balance?")
    print(result)
    # slow_enrichment timed out (degraded)
    # unreliable_enrichment errored (degraded)
    # reliable_enrichment succeeded
    # agent never crashed
    # Output: {'answer': '...', 'enriched_with': ['user_tier']}


if __name__ == "__main__":
    asyncio.run(main())
