"""
LangGraph StateGraph definition.
Wires all agents into a directed graph with explicit state passing.
"""
import logging
from langgraph.graph import StateGraph, END
from backend.agents.state import FinancialPlannerState
from backend.agents.coordinator import coordinator_router_node, coordinator_synthesizer_node
from backend.agents.budget_agent import budget_agent_node
from backend.agents.investment_agent import investment_agent_node
from backend.agents.risk_agent import risk_agent_node
from backend.agents.goal_agent import goal_agent_node

logger = logging.getLogger(__name__)


async def judge_node(state: FinancialPlannerState) -> FinancialPlannerState:
    """Post-execution Judge Agent node."""
    from backend.evaluation.judge_agent import run_judge
    response = state.get("coordinator_response", "")
    if not response:
        return state

    scores = await run_judge(
        user_question=state["user_input"],
        agent_response=response,
        agent_name="full_pipeline",
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
        agent_run_id=state.get("agent_run_id"),
        trace_id=state.get("trace_id"),
    )
    return {**state, "judge_scores": scores}


def build_graph() -> StateGraph:
    """
    Build and compile the LangGraph StateGraph.

    Flow:
    coordinator_router
        -> budget_agent -> investment_agent -> risk_agent -> goal_agent
        -> coordinator_synthesizer
        -> judge
        -> END
    """
    workflow = StateGraph(FinancialPlannerState)

    # Add all nodes
    workflow.add_node("coordinator_router", coordinator_router_node)
    workflow.add_node("budget_agent", budget_agent_node)
    workflow.add_node("investment_agent", investment_agent_node)
    workflow.add_node("risk_agent", risk_agent_node)
    workflow.add_node("goal_agent", goal_agent_node)
    workflow.add_node("coordinator_synthesizer", coordinator_synthesizer_node)
    workflow.add_node("judge", judge_node)

    # Entry point
    workflow.set_entry_point("coordinator_router")

    # Edges: router -> specialists -> synthesizer -> judge -> END
    workflow.add_edge("coordinator_router", "budget_agent")
    workflow.add_edge("budget_agent", "investment_agent")
    workflow.add_edge("investment_agent", "risk_agent")
    workflow.add_edge("risk_agent", "goal_agent")
    workflow.add_edge("goal_agent", "coordinator_synthesizer")
    workflow.add_edge("coordinator_synthesizer", "judge")
    workflow.add_edge("judge", END)

    return workflow.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_pipeline(state: FinancialPlannerState) -> FinancialPlannerState:
    """Execute the full multi-agent pipeline. Returns final state."""
    graph = get_graph()
    final_state = await graph.ainvoke(state)
    return final_state
