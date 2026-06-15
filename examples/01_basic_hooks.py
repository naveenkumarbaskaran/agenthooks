"""01_basic_hooks.py — Hello World for agenthooks.

Any production agent exposes named hook points. Anyone who deploys
that agent can register their own implementations without touching
the agent source code. This example shows the minimal setup.
"""
import asyncio
from agenthooks import HookAgent, hookpoint, HookRegistry, HookContext


class SearchAgent(HookAgent):
    """A search agent with a before_search hook point.

    Users who deploy this agent can register hook implementations
    to enrich context, inject filters, or transform queries before
    the search executes — no source code changes required.
    """
    before_search = hookpoint("before_search")

    async def search(self, query: str) -> dict:
        ctx = HookContext.new(session_id="session-1", tenant_id="demo", query=query)
        async with self.before_search.run(ctx) as ctx:
            filters = ctx.metadata.get("filters", {})
            return {
                "query": ctx.query,
                "filters": filters,
                "results": [f"Result for: {ctx.query}"],
            }


# Customer registers their logic — no fork, no subclass, no PR needed.
customer_registry = HookRegistry()


@customer_registry.implement("before_search")
async def inject_region_filter(ctx: HookContext) -> HookContext:
    return ctx.enrich("filters", {"region": "EU", "language": "en"})


async def main():
    # Agent author ships the agent.
    # Customer attaches their registry at deploy time.
    agent = SearchAgent(registries=[customer_registry])

    result = await agent.search("quarterly revenue report")
    print(result)
    # {'query': 'quarterly revenue report',
    #  'filters': {'region': 'EU', 'language': 'en'},
    #  'results': ['Result for: quarterly revenue report']}


if __name__ == "__main__":
    asyncio.run(main())
