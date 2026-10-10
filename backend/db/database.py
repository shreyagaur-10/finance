import asyncpg
import logging
from typing import Optional
from uuid import UUID
from contextlib import asynccontextmanager
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("Database connection pool created.")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection():
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


class UserRepository:
    async def create(self, email: str, name: str = "", risk_profile: str = "moderate",
                     monthly_income: float = 0.0) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, name, risk_profile, monthly_income)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name
                RETURNING *
                """,
                email, name, risk_profile, monthly_income
            )
            return dict(row)

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id=$1", UUID(user_id))
            return dict(row) if row else None

    async def get_by_email(self, email: str) -> Optional[dict]:
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email=$1", email)
            return dict(row) if row else None

    async def update(self, user_id: str, **kwargs) -> Optional[dict]:
        if not kwargs:
            return await self.get_by_id(user_id)
        set_clauses = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
        values = list(kwargs.values())
        async with get_connection() as conn:
            row = await conn.fetchrow(
                f"UPDATE users SET {set_clauses} WHERE id=$1 RETURNING *",
                UUID(user_id), *values
            )
            return dict(row) if row else None


class SessionRepository:
    async def create(self, user_id: str, metadata: dict = None) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "INSERT INTO sessions (user_id, metadata) VALUES ($1, $2) RETURNING *",
                UUID(user_id), metadata or {}
            )
            return dict(row)

    async def get_by_id(self, session_id: str) -> Optional[dict]:
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM sessions WHERE id=$1", UUID(session_id))
            return dict(row) if row else None

    async def increment_request_count(self, session_id: str) -> int:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "UPDATE sessions SET request_count=request_count+1 WHERE id=$1 RETURNING request_count",
                UUID(session_id)
            )
            return row["request_count"] if row else 0

    async def close_session(self, session_id: str):
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE sessions SET ended_at=NOW() WHERE id=$1", UUID(session_id)
            )


class MessageRepository:
    async def save(self, session_id: str, user_id: str, role: str, content: str,
                   agent_name: str = None) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (session_id, user_id, role, content, agent_name)
                VALUES ($1, $2, $3, $4, $5) RETURNING *
                """,
                UUID(session_id), UUID(user_id), role, content, agent_name
            )
            return dict(row)

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM messages WHERE session_id=$1 ORDER BY created_at ASC LIMIT $2",
                UUID(session_id), limit
            )
            return [dict(r) for r in rows]


class GoalRepository:
    async def create(self, user_id: str, name: str, target_amount: float,
                     category: str = "other", description: str = "",
                     target_date: str = None, priority: int = 1) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO financial_goals
                    (user_id, name, target_amount, category, description, target_date, priority)
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
                """,
                UUID(user_id), name, target_amount, category, description, target_date, priority
            )
            return dict(row)

    async def get_user_goals(self, user_id: str) -> list[dict]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM financial_goals WHERE user_id=$1 AND status='active' ORDER BY priority ASC",
                UUID(user_id)
            )
            return [dict(r) for r in rows]

    async def update_progress(self, goal_id: str, current_amount: float) -> Optional[dict]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE financial_goals
                SET current_amount=$2,
                    status = CASE WHEN $2 >= target_amount THEN 'achieved' ELSE status END
                WHERE id=$1 RETURNING *
                """,
                UUID(goal_id), current_amount
            )
            return dict(row) if row else None

    async def delete(self, goal_id: str, user_id: str):
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE financial_goals SET status='cancelled' WHERE id=$1 AND user_id=$2",
                UUID(goal_id), UUID(user_id)
            )


class AgentRunRepository:
    async def create(self, session_id: str, user_id: str, agent_name: str,
                     trace_name: str = None, input_data: dict = None) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_runs (session_id, user_id, agent_name, trace_name, input_data)
                VALUES ($1, $2, $3, $4, $5) RETURNING *
                """,
                UUID(session_id) if session_id else None,
                UUID(user_id) if user_id else None,
                agent_name, trace_name, input_data
            )
            return dict(row)

    async def complete(self, run_id: str, output_data: dict, latency_ms: float,
                       input_tokens: int = 0, output_tokens: int = 0,
                       langfuse_trace_id: str = None) -> dict:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE agent_runs SET
                    status='completed', output_data=$2, latency_ms=$3,
                    input_tokens=$4, output_tokens=$5, total_tokens=$4+$5,
                    langfuse_trace_id=$6, completed_at=NOW()
                WHERE id=$1 RETURNING *
                """,
                UUID(run_id), output_data, latency_ms,
                input_tokens, output_tokens, langfuse_trace_id
            )
            return dict(row) if row else {}

    async def fail(self, run_id: str, error_message: str):
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE agent_runs SET status='failed', error_message=$2, completed_at=NOW() WHERE id=$1",
                UUID(run_id), error_message
            )


class EvalScoreRepository:
    async def save(self, agent_run_id: str, session_id: str, user_id: str,
                   accuracy: float, relevance: float, safety: float,
                   feedback: str = "", langfuse_score_id: str = None) -> dict:
        overall = round((accuracy + relevance + safety) / 3, 1)
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO evaluation_scores
                    (agent_run_id, session_id, user_id, accuracy_score, relevance_score,
                     safety_score, overall_score, feedback, langfuse_score_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *
                """,
                UUID(agent_run_id) if agent_run_id else None,
                UUID(session_id) if session_id else None,
                UUID(user_id) if user_id else None,
                accuracy, relevance, safety, overall, feedback, langfuse_score_id
            )
            return dict(row)


user_repo = UserRepository()
session_repo = SessionRepository()
message_repo = MessageRepository()
goal_repo = GoalRepository()
agent_run_repo = AgentRunRepository()
eval_score_repo = EvalScoreRepository()
