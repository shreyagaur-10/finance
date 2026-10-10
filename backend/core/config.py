from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # LLM Providers
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", env="GROQ_MODEL")
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", env="GEMINI_MODEL")

    # Supabase (Postgres)
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_anon_key: str = Field(..., env="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")
    database_url: str = Field(..., env="DATABASE_URL")

    # Upstash Redis
    upstash_redis_url: str = Field(..., env="UPSTASH_REDIS_URL")
    upstash_redis_token: str = Field(..., env="UPSTASH_REDIS_TOKEN")

    # Langfuse Observability
    langfuse_public_key: str = Field(..., env="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(..., env="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", env="LANGFUSE_HOST")

    # Application
    app_name: str = Field(default="Financial AI Planner", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    secret_key: str = Field(..., env="SECRET_KEY")
    allowed_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:8501"], env="ALLOWED_ORIGINS")
    max_requests_per_minute: int = Field(default=10, env="MAX_REQUESTS_PER_MINUTE")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
