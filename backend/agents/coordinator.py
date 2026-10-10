"""
Coordinator/Router Agent.
Receives user request, decides which specialist agents to invoke,
then merges all outputs into a single coherent response.
"""
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from backend.agents.state import FinancialPlannerState
from backend.core.llm_provider import get_llm_with_fallback, invoke_llm_with_tracing

logger = logging.getLogger(__name__)

COORDINATOR_SYSTEM_PROMPT = """You are the Coordinator Agent of a Multi-Agent Financial AI Planning System.
Your roles:
1. ROUTE: Analyze the user's financial question and decide which specialist agents are needed.
2. MERGE: After specialist agents respond, synthesize their outputs into one clear, helpful answer.

Available specialist agents:
- budget_agent: income/expense analysis, budget breakdowns, cash flow
- investment_agent: portfolio allocation, investment strategies, asset selection
- risk_agent: risk exposure analysis, risk profiling, concern flags
- goal_agent: financial goal setting, progress tracking, milestone planning

For ROUTING, respond with JSON:
{"agents": ["budget_agent", "risk_agent"], "reasoning": "User asked about spending and risk"}

For SYNTHESIS, provide a comprehensive, helpful financial planning response.

Always be professional, precise, and data-driven. Never make guaranteed return claims.
"""


async def coordinator_router_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Step 1: Route - determine which agents to invoke."""
    logger.info("[Coordinator] Routing user request...")
    llm = get_llm_with_fallback(temperature=0.0)

    messages = [
        SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User profile: {json.dumps(state.get('user_profile', {}), default=str)}\n\n"
                    f"User question: {state['user_input']}\n\n"
                    f"Decide which agents to invoke. Respond with JSON only: "
                    '{"agents": [...], "reasoning": "..."}'
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="coordinator",
        trace_name="coordinator-routing",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    try:
        content = response.content.strip()
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}")+1]
            routing = json.loads(json_str)
        else:
            routing = {"agents": ["budget_agent", "investment_agent", "risk_agent", "goal_agent"]}

        agents = routing.get("agents", [])
        reasoning = routing.get("reasoning", "")
        logger.info(f"[Coordinator] Routing to: {agents} | {reasoning}")
    except Exception as e:
        logger.error(f"[Coordinator] Routing parse error: {e}")
        agents = ["budget_agent", "investment_agent"]

    return {
        **state,
        "active_agents": agents,
        "current_agent": "coordinator",
        "trace_id": trace_info.get("trace_id"),
    }


async def coordinator_synthesizer_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Step 2: Synthesize - merge all specialist outputs into one response."""
    logger.info("[Coordinator] Synthesizing specialist outputs...")
    llm = get_llm_with_fallback(temperature=0.2)

    specialist_context = []
    if state.get("budget_analysis"):
        specialist_context.append(f"BUDGET ANALYSIS:\n{json.dumps(state['budget_analysis'], default=str, indent=2)}")
    if state.get("investment_plan"):
        specialist_context.append(f"INVESTMENT PLAN:\n{json.dumps(state['investment_plan'], default=str, indent=2)}")
    if state.get("risk_assessment"):
        specialist_context.append(f"RISK ASSESSMENT:\n{json.dumps(state['risk_assessment'], default=str, indent=2)}")
    if state.get("goal_tracking"):
        specialist_context.append(f"GOAL TRACKING:\n{json.dumps(state['goal_tracking'], default=str, indent=2)}")

    context_str = "\n\n".join(specialist_context) if specialist_context else "No specialist data available."

    messages = [
        SystemMessage(content=COORDINATOR_SYSTEM_PROMPT),
        HumanMessage(
            content=f"User question: {state['user_input']}\n\n"
                    f"Specialist Agent Outputs:\n{context_str}\n\n"
                    f"Synthesize all outputs into one comprehensive, actionable response for the user."
        ),
    ]

    response, trace_info = await invoke_llm_with_tracing(
        llm=llm,
        messages=messages,
        agent_name="coordinator",
        trace_name="coordinator-synthesis",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )

    return {
        **state,
        "coordinator_response": response.content,
        "current_agent": "coordinator_synthesizer",
    }
