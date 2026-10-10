"""
Budget Analysis Agent.
Analyzes income/expenses, builds budget breakdowns, identifies savings opportunities.
"""
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from backend.agents.state import FinancialPlannerState
from backend.core.llm_provider import get_llm_with_fallback, invoke_llm_with_tracing

logger = logging.getLogger(__name__)

BUDGET_SYSTEM_PROMPT = """You are the Budget Analysis Agent, a specialist in personal finance budgeting.

Your capabilities:
- Analyze income vs expenses to determine cash flow
- Categorize spending (housing, food, transport, entertainment, savings, etc.)
- Apply the 50/30/20 rule and other budgeting frameworks
- Identify overspending categories and savings opportunities
- Calculate emergency fund requirements
- Suggest expense reduction strategies

Always respond with structured JSON:
{
  "summary": "brief narrative",
  "monthly_income": number,
  "total_expenses": number,
  "net_cash_flow": number,
  "savings_rate_percent": number,
  "expense_breakdown": {"category": amount},
  "budget_framework": {"needs_percent": n, "wants_percent": n, "savings_percent": n},
  "recommendations": ["action items"],
  "emergency_fund_target": number,
  "emergency_fund_months": number
}
"""


async def budget_agent_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Budget Analysis Agent node for LangGraph."""
    if "budget_agent" not in state.get("active_agents", []):
        logger.info("[Budget] Skipping - not in active_agents")
        return state

    logger.info("[Budget] Running budget analysis...")
    llm = get_llm_with_fallback(temperature=0.1)
    profile = state.get("user_profile", {})

    messages = [
        SystemMessage(content=BUDGET_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User profile: {json.dumps(profile, default=str)}\n\n"
                    f"User request: {state['user_input']}\n\n"
                    f"Provide detailed budget analysis as JSON."
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="budget_agent",
        trace_name="budget-analysis",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    try:
        content = response.content.strip()
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}")+1]
            analysis = json.loads(json_str)
        else:
            analysis = {"summary": content, "raw_response": content}
    except Exception as e:
        logger.error(f"[Budget] JSON parse error: {e}")
        analysis = {"summary": response.content, "error": str(e)}

    analysis["trace_id"] = trace_info.get("trace_id")
    analysis["latency_ms"] = trace_info.get("latency_ms")

    return {**state, "budget_analysis": analysis, "current_agent": "budget_agent"}
