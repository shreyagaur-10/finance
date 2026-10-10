import logging
from functools import lru_cache
from langfuse import Langfuse
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache()
def get_langfuse_client() -> Langfuse:
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    logger.info(f"Langfuse client initialized — host: {settings.langfuse_host}")
    return client


def record_agent_span(trace, span_name: str, agent_name: str, input_data: dict,
                     output_data: dict, latency_ms: float, metadata: dict = None):
    span = trace.span(
        name=span_name,
        input=input_data,
        output=output_data,
        metadata={"agent": agent_name, "latency_ms": latency_ms, **(metadata or {})},
    )
    span.end()
    return span


def record_score(trace, name: str, value: float, comment: str = None):
    return trace.score(name=name, value=value, comment=comment)
