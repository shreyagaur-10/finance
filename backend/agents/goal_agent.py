"""
Goal Tracking Agent.
Tracks user financial goals persisted in Postgres.
"""
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from backend.agents.state import FinancialPlannerState
from backend.core.llm_provider import get_llm_with_fallback, invoke_llm_with_tracing
from backend.db.database import goal_repo

logger = logging.getLogger(__name__)

GOAL_SYSTEM_PROMPT = """You are the Goal Tracking Agent, a specialist in financial goal management.

Your capabilities:
- Track progress toward user-defined financial goals
- Calculate monthly savings required to meet goals by deadline
- Prioritize goals based on urgency and importance
- Identify goal conflicts (e.g., saving for home + retirement simultaneously)
- Celebrate milestones and adjust plans when goals are achieved
- Flag at-risk goals that need attention

Respond with structured JSON:
{
  "goals_summary": [
    {
      "goal_name": str,
      "category": str,
      "target_amount": number,
      "current_amount": number,
      "progress_percent": number,
      "months_remaining": number,
      "monthly_required": number,
      "status": "on_track|at_risk|achieved|behind",
      "recommendation": str
    }
  ],
  "total_goals_count": number,
  "achieved_count": number,
  "at_risk_count": number,
  "priority_action": str,
  "new_goals_suggested": [str],
  "summary": "narrative"
}
"""


async def goal_agent_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Goal Tracking Agent node for LangGraph."""
    if "goal_agent" not in state.get("active_agents", []):
        logger.info("[Goal] Skipping - not in active_agents")
        return state

    logger.info("[Goal] Tracking financial goals...")
    llm = get_llm_with_fallback(temperature=0.1)
    profile = state.get("user_profile", {})
    user_id = state.get("user_id")

    # Load goals from Postgres
    db_goals = []
    if user_id:
        try:
            db_goals = await goal_repo.get_user_goals(user_id)
        except Exception as e:
            logger.error(f"[Goal] Failed to load goals from DB: {e}")

    messages = [
        SystemMessage(content=GOAL_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User profile: {json.dumps(profile, default=str)}\n\n"
                    f"Existing goals from database: {json.dumps(db_goals, default=str)}\n\n"
                    f"Budget data: {json.dumps(state.get('budget_analysis', {}), default=str)}\n\n"
                    f"User request: {state['user_input']}\n\n"
                    f"Provide goal tracking analysis as JSON."
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="goal_agent",
        trace_name="goal-tracking",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    try:
        content = response.content.strip()
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}")+1]
            tracking = json.loads(json_str)
        else:
            tracking = {"summary": content}
    except Exception as e:
        logger.error(f"[Goal] JSON parse error: {e}")
        tracking = {"summary": response.content, "error": str(e)}

    tracking["db_goals_loaded"] = len(db_goals)
    tracking["trace_id"] = trace_info.get("trace_id")
    return {**state, "goal_tracking": tracking, "current_agent": "goal_agent"}
