"""02_customer_extensibility.py — Customer freedom without fork.

An agent ships with hook points. Each customer deployment registers
their own logic: approval gates, data enrichment, compliance checks,
tenant-specific business rules. None of them touch the agent code.

This is the core promise of agenthooks: agents are extensible by
design. Customers own their logic. The agent owner owns the core.
"""
import asyncio
from agenthooks import (
    HookAgent, hookpoint, HookRegistry, HookContext,
    HookBlocked, inject, block_if,
)


class ApprovalAgent(HookAgent):
    """Agent that executes actions on behalf of a user.

    Hook points let customers plug in their approval workflows,
    compliance checks, and audit requirements.
    """
    before_execute = hookpoint("before_execute")
    after_execute = hookpoint("after_execute")

    async def execute(self, action: str, tenant_id: str) -> dict:
        ctx = HookContext.new(session_id="sess-1", tenant_id=tenant_id)
        ctx = ctx.replace("tool_name", action)

        try:
            async with self.before_execute.run(ctx) as ctx:
                approved_by = ctx.metadata.get("approved_by", "auto")
                result = {"action": action, "status": "executed", "approved_by": approved_by}

            async with self.after_execute.run(ctx) as ctx:
                pass

            return result

        except HookBlocked as e:
            return {"action": action, "status": "blocked", "reason": e.reason}


# ── Customer A: strict approval gate ────────────────────────────────────────

acme_registry = HookRegistry()


@acme_registry.implement("before_execute", filter={"tenant": "ACME"}, order=10)
@block_if(lambda ctx: ctx.tool_name in ("delete_all", "export_pii"), reason="Requires VP approval")
@inject(approved_by="manager@acme.com")
async def acme_approval(ctx: HookContext) -> HookContext:
    return ctx


# ── Customer B: compliance logging + enrichment ──────────────────────────────

compliance_registry = HookRegistry()


@compliance_registry.implement("before_execute", filter={"tenant": "GLOBEX"}, order=10)
@inject(compliance_tier="SOC2", data_residency="US")
async def globex_compliance(ctx: HookContext) -> HookContext:
    return ctx


@compliance_registry.implement("after_execute", filter={"tenant": "GLOBEX"})
async def globex_audit_log(ctx: HookContext) -> HookContext:
    print(f"[GLOBEX AUDIT] action={ctx.tool_name} tenant={ctx.tenant_id} trace={ctx.trace_id}")
    return ctx


async def main():
    # Agent is deployed once. Each customer attaches their registry.
    agent = ApprovalAgent(registries=[acme_registry, compliance_registry])

    print("=== ACME: normal action ===")
    print(await agent.execute("generate_report", "ACME"))

    print("\n=== ACME: blocked action ===")
    print(await agent.execute("delete_all", "ACME"))

    print("\n=== GLOBEX: compliance enrichment ===")
    print(await agent.execute("fetch_data", "GLOBEX"))

    print("\n=== Unknown tenant: no hooks fire ===")
    print(await agent.execute("fetch_data", "UNKNOWN"))


if __name__ == "__main__":
    asyncio.run(main())
