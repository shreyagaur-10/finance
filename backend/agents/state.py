"""
LangGraph shared state definition.
All agents read from and write to this TypedDict.
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class FinancialPlannerState(TypedDict):
    # Core conversation
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    session_id: str
    user_id: str

    # Routing
    active_agents: list[str]
    current_agent: str

    # User context
    user_profile: dict
    conversation_history: list[dict]

    # Agent outputs
    budget_analysis: Optional[dict]
    investment_plan: Optional[dict]
    risk_assessment: Optional[dict]
    goal_tracking: Optional[dict]
    coordinator_response: Optional[str]

    # Evaluation
    judge_scores: Optional[dict]
    agent_run_id: Optional[str]

    # Metadata
    trace_id: Optional[str]
    latency_ms: Optional[float]
    error: Optional[str]


def default_state() -> FinancialPlannerState:
    return {
        "messages": [],
        "user_input": "",
        "session_id": "",
        "user_id": "",
        "active_agents": [],
        "current_agent": "",
        "user_profile": {},
        "conversation_history": [],
        "budget_analysis": None,
        "investment_plan": None,
        "risk_assessment": None,
        "goal_tracking": None,
        "coordinator_response": None,
        "judge_scores": None,
        "agent_run_id": None,
        "trace_id": None,
        "latency_ms": None,
        "error": None,
    }
