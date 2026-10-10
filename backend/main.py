"""
FastAPI backend for the Multi-Agent Financial AI Planner.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from backend.core.config import get_settings
from backend.db.database import (
    get_pool, close_pool,
    user_repo, session_repo, message_repo, goal_repo, agent_run_repo
)
from backend.agents.graph import run_pipeline
from backend.agents.state import FinancialPlannerState
from backend.guardrails.input_guard import validate_input
from backend.guardrails.output_guard import validate_output
from backend.queue.redis_queue import (
    rate_limit_check, enqueue_task, get_queue_length, task_worker
)

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Financial AI Planner API...")
    await get_pool()
    task_worker.register_handler("analyze", _handle_analyze_task)
    worker_task = asyncio.create_task(task_worker.start())
    yield
    await task_worker.stop()
    worker_task.cancel()
    await close_pool()
    logger.info("Shutdown complete.")


async def _handle_analyze_task(payload: dict):
    """Queue worker handler for async analysis tasks."""
    logger.info(f"[Worker] Processing analyze task: {payload.get('session_id')}")
    state: FinancialPlannerState = {
        **payload,
        "messages": [],
        "active_agents": [],
        "current_agent": "",
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
    await run_pipeline(state)


app = FastAPI(
    title="Financial AI Planner API",
    description="Multi-Agent Financial Planning System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---
class UserCreate(BaseModel):
    email: str
    name: str = ""
    risk_profile: str = "moderate"
    monthly_income: float = 0.0


class SessionCreate(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    user_profile: Optional[dict] = None

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        return v


class GoalCreate(BaseModel):
    user_id: str
    name: str
    target_amount: float
    category: str = "other"
    description: str = ""
    target_date: Optional[str] = None
    priority: int = 1


class GoalUpdate(BaseModel):
    current_amount: float


class AsyncAnalysisRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    user_profile: Optional[dict] = None


# --- Routes ---
@app.get("/health")
async def health():
    queue_len = await get_queue_length()
    return {
        "status": "healthy",
        "service": "Financial AI Planner",
        "queue_depth": queue_len,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/users", status_code=201)
async def create_user(body: UserCreate):
    user = await user_repo.create(
        email=body.email, name=body.name,
        risk_profile=body.risk_profile, monthly_income=body.monthly_income,
    )
    return {"user": _serialize(user)}


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": _serialize(user)}


@app.patch("/users/{user_id}")
async def update_user(user_id: str, body: dict):
    user = await user_repo.update(user_id, **body)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": _serialize(user)}


@app.post("/sessions", status_code=201)
async def create_session(body: SessionCreate):
    session = await session_repo.create(user_id=body.user_id)
    return {"session": _serialize(session)}


@app.post("/chat")
async def chat(body: ChatRequest):
    """Main chat endpoint. Runs through the full multi-agent pipeline."""
    # 1. Rate limiting
    allowed, count = await rate_limit_check(body.user_id, settings.max_requests_per_minute)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {count}/{settings.max_requests_per_minute}/min")

    # 2. Input guardrails
    guard = validate_input(body.message, enforce_finance_domain=False)
    if not guard.allowed:
        raise HTTPException(status_code=400, detail=guard.reason)
    clean_input = guard.sanitized_input or body.message

    # 3. Validate user + session
    user = await user_repo.get_by_id(body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session = await session_repo.get_by_id(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 4. Save user message
    await message_repo.save(session_id=body.session_id, user_id=body.user_id,
                            role="user", content=clean_input)
    await session_repo.increment_request_count(body.session_id)

    # 5. Load conversation history
    history = await message_repo.get_history(body.session_id, limit=20)

    # 6. Create agent run record
    run = await agent_run_repo.create(
        session_id=body.session_id, user_id=body.user_id,
        agent_name="coordinator", trace_name="chat-pipeline",
        input_data={"message": clean_input},
    )

    # 7. Build state and run pipeline
    start = time.time()
    user_profile = body.user_profile or _serialize(user)
    state: FinancialPlannerState = {
        "messages": [],
        "user_input": clean_input,
        "session_id": body.session_id,
        "user_id": body.user_id,
        "active_agents": [],
        "current_agent": "",
        "user_profile": user_profile,
        "conversation_history": history,
        "budget_analysis": None,
        "investment_plan": None,
        "risk_assessment": None,
        "goal_tracking": None,
        "coordinator_response": None,
        "judge_scores": None,
        "agent_run_id": str(run["id"]),
        "trace_id": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        final_state = await run_pipeline(state)
        latency_ms = (time.time() - start) * 1000
        response_text = final_state.get("coordinator_response", "I was unable to generate a response.")

        # 8. Output guardrails
        output_guard = validate_output(response_text, agent_name="coordinator")
        safe_response = output_guard.sanitized_output or response_text

        # 9. Complete agent run
        await agent_run_repo.complete(
            run_id=str(run["id"]),
            output_data={"response": safe_response[:2000]},
            latency_ms=latency_ms,
            langfuse_trace_id=final_state.get("trace_id"),
        )

        # 10. Save assistant message
        await message_repo.save(
            session_id=body.session_id, user_id=body.user_id,
            role="assistant", content=safe_response, agent_name="coordinator",
        )

        return {
            "response": safe_response,
            "agents_invoked": final_state.get("active_agents", []),
            "judge_scores": final_state.get("judge_scores"),
            "latency_ms": round(latency_ms, 1),
            "session_id": body.session_id,
            "guard_flags": output_guard.risk_flags,
        }

    except Exception as e:
        await agent_run_repo.fail(str(run["id"]), str(e))
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/analyze/async")
async def analyze_async(body: AsyncAnalysisRequest):
    """Enqueue analysis as async task via Upstash Redis."""
    allowed, count = await rate_limit_check(body.user_id, settings.max_requests_per_minute)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    guard = validate_input(body.message)
    if not guard.allowed:
        raise HTTPException(status_code=400, detail=guard.reason)

    task_id = await enqueue_task(
        task_type="analyze",
        payload={
            "user_input": guard.sanitized_input or body.message,
            "session_id": body.session_id,
            "user_id": body.user_id,
            "user_profile": body.user_profile or {},
            "conversation_history": [],
        },
    )
    queue_depth = await get_queue_length()
    return {
        "task_id": task_id,
        "status": "queued",
        "queue_depth": queue_depth,
        "message": "Task enqueued. Results stored in the database.",
    }


@app.get("/goals/{user_id}")
async def get_goals(user_id: str):
    goals = await goal_repo.get_user_goals(user_id)
    return {"goals": [_serialize(g) for g in goals]}


@app.post("/goals", status_code=201)
async def create_goal(body: GoalCreate):
    goal = await goal_repo.create(
        user_id=body.user_id, name=body.name,
        target_amount=body.target_amount, category=body.category,
        description=body.description, target_date=body.target_date,
        priority=body.priority,
    )
    return {"goal": _serialize(goal)}


@app.patch("/goals/{goal_id}")
async def update_goal_progress(goal_id: str, body: GoalUpdate):
    goal = await goal_repo.update_progress(goal_id, body.current_amount)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"goal": _serialize(goal)}


@app.delete("/goals/{goal_id}")
async def cancel_goal(goal_id: str, user_id: str):
    await goal_repo.delete(goal_id, user_id)
    return {"message": "Goal cancelled"}


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    messages = await message_repo.get_history(session_id, limit=100)
    return {"messages": [_serialize(m) for m in messages]}


@app.get("/queue/status")
async def queue_status():
    depth = await get_queue_length()
    return {"queue_depth": depth}


def _serialize(obj):
    """Convert asyncpg Record/dict to JSON-serializable dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    return obj


def _serialize_value(v):
    from datetime import date
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v
