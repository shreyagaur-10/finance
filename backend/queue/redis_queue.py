import json
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Awaitable, Optional
from upstash_redis.asyncio import Redis
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

QUEUE_KEY = "financial_planner:task_queue"
DLQ_KEY = "financial_planner:dlq"
MAX_RETRIES = 3


def get_redis() -> Redis:
    return Redis(
        url=settings.upstash_redis_url,
        token=settings.upstash_redis_token,
    )


async def enqueue_task(task_type: str, payload: dict, priority: int = 0) -> str:
    task = {
        "task_id": str(uuid.uuid4()),
        "task_type": task_type,
        "payload": payload,
        "priority": priority,
        "retries": 0,
        "enqueued_at": time.time(),
    }
    redis = get_redis()
    await redis.rpush(QUEUE_KEY, json.dumps(task))
    logger.info(f"Enqueued task {task['task_id']} of type '{task_type}'")
    return task["task_id"]


async def dequeue_task() -> Optional[dict]:
    redis = get_redis()
    result = await redis.lpop(QUEUE_KEY)
    if result:
        return json.loads(result)
    return None


async def get_queue_length() -> int:
    redis = get_redis()
    return await redis.llen(QUEUE_KEY)


async def send_to_dlq(task: dict, error: str):
    task["error"] = error
    redis = get_redis()
    await redis.rpush(DLQ_KEY, json.dumps(task))
    logger.warning(f"Task {task.get('task_id')} moved to DLQ: {error}")


async def rate_limit_check(user_id: str, max_per_minute: int) -> tuple[bool, int]:
    redis = get_redis()
    now = int(time.time())
    window_key = f"rate_limit:{user_id}:{now // 60}"
    count = await redis.incr(window_key)
    if count == 1:
        await redis.expire(window_key, 120)
    allowed = count <= max_per_minute
    if not allowed:
        logger.warning(f"Rate limit exceeded for user {user_id}: {count}/{max_per_minute}")
    return allowed, count


class TaskWorker:
    def __init__(self):
        self._handlers: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self._running = False

    def register_handler(self, task_type: str, handler: Callable[[dict], Awaitable[Any]]):
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    async def start(self, poll_interval: float = 1.0):
        self._running = True
        logger.info("TaskWorker started.")
        while self._running:
            task = await dequeue_task()
            if task:
                await self._process(task)
            else:
                await asyncio.sleep(poll_interval)

    async def stop(self):
        self._running = False
        logger.info("TaskWorker stopped.")

    async def _process(self, task: dict):
        task_type = task.get("task_type")
        handler = self._handlers.get(task_type)
        if not handler:
            logger.error(f"No handler for task_type: {task_type}")
            await send_to_dlq(task, f"No handler for {task_type}")
            return
        try:
            logger.info(f"Processing task {task['task_id']} ({task_type})")
            await handler(task["payload"])
        except Exception as e:
            task["retries"] = task.get("retries", 0) + 1
            if task["retries"] < MAX_RETRIES:
                redis = get_redis()
                await redis.rpush(QUEUE_KEY, json.dumps(task))
                logger.warning(f"Task {task['task_id']} retrying ({task['retries']}/{MAX_RETRIES}): {e}")
            else:
                await send_to_dlq(task, str(e))


task_worker = TaskWorker()
