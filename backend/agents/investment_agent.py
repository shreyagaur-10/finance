"""
Investment Planning Agent.
Suggests portfolio allocations based on risk profile and goals.
"""
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from backend.agents.state import FinancialPlannerState
from backend.core.llm_provider import get_llm_with_fallback, invoke_llm_with_tracing

logger = logging.getLogger(__name__)

INVESTMENT_SYSTEM_PROMPT = """You are the Investment Planning Agent, a specialist in portfolio construction.

Your capabilities:
- Design asset allocation based on risk tolerance (conservative/moderate/aggressive)
- Suggest index funds, ETFs, and asset classes (not individual stocks)
- Apply Modern Portfolio Theory principles
- Factor in investment horizon and liquidity needs
- Recommend tax-advantaged accounts (401k, IRA, HSA)
- Calculate required monthly investment to meet goals

Respond with structured JSON:
{
  "risk_profile": "conservative|moderate|aggressive",
  "investment_horizon_years": number,
  "monthly_investment_amount": number,
  "portfolio_allocation": {
    "US_Stocks": percent,
    "International_Stocks": percent,
    "Bonds": percent,
    "Real_Estate": percent,
    "Cash": percent
  },
  "recommended_funds": [
    {"name": str, "ticker": str, "allocation_percent": number, "reason": str}
  ],
  "tax_advantaged_accounts": ["401k up to match", "Roth IRA"],
  "expected_annual_return_range": {"low": percent, "high": percent},
  "recommendations": ["action items"],
  "summary": "narrative"
}

Do NOT guarantee returns. Always note market risk.
"""


async def investment_agent_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Investment Planning Agent node for LangGraph."""
    if "investment_agent" not in state.get("active_agents", []):
        logger.info("[Investment] Skipping - not in active_agents")
        return state

    logger.info("[Investment] Building investment plan...")
    llm = get_llm_with_fallback(temperature=0.1)
    profile = state.get("user_profile", {})

    messages = [
        SystemMessage(content=INVESTMENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User profile: {json.dumps(profile, default=str)}\n\n"
                    f"User request: {state['user_input']}\n\n"
                    f"Provide investment plan as JSON."
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="investment_agent",
        trace_name="investment-planning",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    try:
        content = response.content.strip()
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}")+1]
            plan = json.loads(json_str)
        else:
            plan = {"summary": content}
    except Exception as e:
        logger.error(f"[Investment] JSON parse error: {e}")
        plan = {"summary": response.content, "error": str(e)}

    plan["trace_id"] = trace_info.get("trace_id")
    return {**state, "investment_plan": plan, "current_agent": "investment_agent"}
