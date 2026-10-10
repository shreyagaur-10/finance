import time
import logging
from typing import Optional, Any
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_primary_llm(temperature: float = 0.1, max_tokens: int = 4096) -> BaseChatModel:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_fallback_llm(temperature: float = 0.1, max_tokens: int = 4096) -> BaseChatModel:
    return ChatGoogleGenerativeAI(
        google_api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def get_llm_with_fallback(temperature: float = 0.1, max_tokens: int = 4096) -> BaseChatModel:
    primary = get_primary_llm(temperature=temperature, max_tokens=max_tokens)
    fallback = get_fallback_llm(temperature=temperature, max_tokens=max_tokens)
    return primary.with_fallbacks([fallback])


async def invoke_llm_with_tracing(
    llm: BaseChatModel,
    messages: list,
    agent_name: str,
    trace_name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> tuple[Any, dict]:
    from backend.observability.langfuse_client import get_langfuse_client
    langfuse = get_langfuse_client()
    start_time = time.time()

    trace = langfuse.trace(
        name=trace_name,
        session_id=session_id,
        user_id=user_id,
        metadata={"agent": agent_name, **(metadata or {})},
        tags=[agent_name, "llm-call"],
    )

    generation = trace.generation(
        name=f"{agent_name}-generation",
        model=settings.groq_model,
        input=[{"role": m.type, "content": m.content} for m in messages],
    )

    try:
        response = await llm.ainvoke(messages)
        latency_ms = (time.time() - start_time) * 1000

        token_usage = {}
        if hasattr(response, "response_metadata"):
            rm = response.response_metadata
            if "token_usage" in rm:
                tu = rm["token_usage"]
                token_usage = {
                    "input_tokens": tu.get("prompt_tokens", 0),
                    "output_tokens": tu.get("completion_tokens", 0),
                    "total_tokens": tu.get("total_tokens", 0),
                }

        generation.end(
            output=response.content,
            usage={
                "input": token_usage.get("input_tokens", 0),
                "output": token_usage.get("output_tokens", 0),
                "total": token_usage.get("total_tokens", 0),
            },
            metadata={"latency_ms": latency_ms},
        )
        trace.update(output=response.content[:500])

        return response, {"trace_id": trace.id, "latency_ms": latency_ms, **token_usage}
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        generation.end(output=str(e), level="ERROR", status_message=str(e))
        logger.error(f"[{agent_name}] LLM call failed: {e}")
        raise
