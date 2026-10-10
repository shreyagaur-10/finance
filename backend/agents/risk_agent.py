"""
Risk Assessment Agent.
Evaluates financial risk exposure and flags concerns.
"""
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from backend.agents.state import FinancialPlannerState
from backend.core.llm_provider import get_llm_with_fallback, invoke_llm_with_tracing

logger = logging.getLogger(__name__)

RISK_SYSTEM_PROMPT = """You are the Risk Assessment Agent, a specialist in financial risk analysis.

Your capabilities:
- Evaluate portfolio concentration risk
- Assess debt-to-income ratio and leverage risk
- Identify sequence-of-returns risk for retirees
- Flag insufficient emergency funds
- Detect over-reliance on single income source
- Assess insurance gaps (health, life, disability)
- Score overall financial risk (1-10 scale)

Respond with structured JSON:
{
  "overall_risk_score": number (1-10, 10=highest risk),
  "risk_category": "low|medium|high|critical",
  "risk_factors": [
    {"factor": str, "severity": "low|medium|high", "description": str}
  ],
  "debt_to_income_ratio": number,
  "emergency_fund_adequacy": "insufficient|adequate|excellent",
  "insurance_gaps": [str],
  "concentration_risks": [str],
  "immediate_actions": [str],
  "long_term_recommendations": [str],
  "summary": "narrative"
}
"""


async def risk_agent_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Risk Assessment Agent node for LangGraph."""
    if "risk_agent" not in state.get("active_agents", []):
        logger.info("[Risk] Skipping - not in active_agents")
        return state

    logger.info("[Risk] Assessing financial risk...")
    llm = get_llm_with_fallback(temperature=0.1)
    profile = state.get("user_profile", {})

    messages = [
        SystemMessage(content=RISK_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User profile: {json.dumps(profile, default=str)}\n\n"
                    f"Budget data: {json.dumps(state.get('budget_analysis', {}), default=str)}\n\n"
                    f"User request: {state['user_input']}\n\n"
                    f"Provide risk assessment as JSON."
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="risk_agent",
        trace_name="risk-assessment",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    try:
        content = response.content.strip()
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}")+1]
            assessment = json.loads(json_str)
        else:
            assessment = {"summary": content}
    except Exception as e:
        logger.error(f"[Risk] JSON parse error: {e}")
        assessment = {"summary": response.content, "error": str(e)}

    assessment["trace_id"] = trace_info.get("trace_id")
    return {**state, "risk_assessment": assessment, "current_agent": "risk_agent"}
