"""03_multi_tenant_isolation.py — Per-tenant hooks with zero cross-contamination.

Hook implementations are filtered by tenant at execution time. A hook
registered for tenant A never fires for tenant B. Multiple customers
can register implementations on the same hook point — each only sees
their own execution.

This is how you ship one agent binary and let N customers extend it
independently.
"""
import asyncio
from agenthooks import HookAgent, hookpoint, HookRegistry, HookContext


class DataAgent(HookAgent):
    before_query = hookpoint("before_query")

    async def query(self, question: str, tenant_id: str) -> dict:
        ctx = HookContext.new(session_id="s1", tenant_id=tenant_id, query=question)
        async with self.before_query.run(ctx) as ctx:
            return {
                "question": ctx.query,
                "tenant": ctx.tenant_id,
                "context": ctx.metadata,
            }


# Three independent customer registries — each knows nothing about the others.
acme = HookRegistry()
globex = HookRegistry()
initech = HookRegistry()


@acme.implement("before_query", filter={"tenant": "ACME"})
async def acme_context(ctx: HookContext) -> HookContext:
    return (
        ctx.enrich("fiscal_year", "FY2026")
           .enrich("currency", "EUR")
           .enrich("data_scope", "EMEA")
    )


@globex.implement("before_query", filter={"tenant": "GLOBEX"})
async def globex_context(ctx: HookContext) -> HookContext:
    return (
        ctx.enrich("fiscal_year", "FY2025")
           .enrich("currency", "USD")
           .enrich("data_scope", "AMERICAS")
    )


@initech.implement("before_query", filter={"tenant": "INITECH"})
async def initech_context(ctx: HookContext) -> HookContext:
    # Initech transforms the query before it reaches the LLM
    sanitised = ctx.query.lower().strip() if ctx.query else ctx.query
    return ctx.replace("query", sanitised).enrich("sanitised", True)


async def main():
    # All three registries attached — agent routes automatically.
    agent = DataAgent(registries=[acme, globex, initech])

    for tenant in ["ACME", "GLOBEX", "INITECH", "UNKNOWN"]:
        result = await agent.query("Show me revenue", tenant)
        print(f"{tenant}: {result['context']}")


if __name__ == "__main__":
    asyncio.run(main())
