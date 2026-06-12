# agenthooks

**BAdI for AI agents.** Define hook points in your agent. Let customers implement them. Nothing breaks if a hook fails.

```bash
pip install agenthooks
```

## Quick start

```python
from agenthooks import HookAgent, hookpoint, HookRegistry, HookContext

class MyAgent(HookAgent):
    before_call = hookpoint("before_call")

    async def run(self, query: str) -> str:
        ctx = HookContext.new(session_id="s1", tenant_id="acme")
        async with self.before_call.run(ctx) as ctx:
            return f"Result for: {ctx.query or query}"

registry = HookRegistry()

@registry.implement("before_call")
async def inject_context(ctx: HookContext) -> HookContext:
    return ctx.enrich("plant", "1000")

agent = MyAgent(registries=[registry])
```

See `examples/` for full cookbook.
