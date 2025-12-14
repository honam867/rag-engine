from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SUPABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore other SUPABASE_* keys (jwt_secret handled by AuthSettings)
    )

    db_url: str


class R2Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="R2_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SUPABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore other SUPABASE_* keys meant for DatabaseSettings
    )

    jwt_secret: str


class DocumentAISettings(BaseSettings):
    """Settings for Google Cloud Document AI (Phase 2).

    All fields are optional so that the app can start without Document AI
    configured; the parser worker should validate presence before use.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    location: str | None = Field(default=None, alias="GCP_LOCATION")
    ocr_processor_id: str | None = Field(default=None, alias="DOCAI_OCR_PROCESSOR_ID")
    credentials_path: str | None = Field(default=None, alias="GCP_CREDENTIALS_PATH")


class RagSettings(BaseSettings):
    """Settings for RAG‑Anything / LightRAG integration (Phase 3)."""

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base directory where per-workspace LightRAG data will be stored.
    # Each workspace will use a subdirectory of this path.
    working_dir: str = "./rag_workspaces"
    # Default query mode for RAG-Anything / LightRAG (e.g. "mix", "hybrid", "local").
    query_mode: str = "mix"
    # Logical model names for LLM and embeddings used by RAG-Anything / LightRAG.
    # These are passed through to the underlying client implementation.
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-large"
    # Default temperature for the LightRAG LLM calls.
    # Lower values keep answers more deterministic and grounded in retrieved context.
    llm_temperature: float = 0.4


class AnswerSettings(BaseSettings):
    """Settings for the Phase 8 Answer Orchestrator LLM.

    This controls the independent LLM used to generate chat answers
    (separate from the LLM used inside RAG-Anything / LightRAG).
    """

    model_config = SettingsConfigDict(
        env_prefix="ANSWER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Default model for answer generation. This should be an OpenAI-compatible
    # chat model name (e.g. gpt-4.1-mini, gpt-4o-mini).
    model: str = "gpt-4.1-mini"
    # Optional base URL for OpenAI-compatible APIs (if not set, falls back
    # to OPENAI_BASE_URL or the official api.openai.com endpoint).
    base_url: str | None = None
    # Optional dedicated API key; if not set, the client will fall back to
    # OPENAI_API_KEY from the environment.
    api_key: str | None = None
    # Default completion limits.
    max_tokens: int = 2048
    temperature: float = 0.2


class RedisSettings(BaseSettings):
    """Settings for Redis Event Bus (Phase 6)."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Full Redis URL, e.g. redis://localhost:6379/0
    url: str = "redis://localhost:6379/0"


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()  # type: ignore[call-arg]
    r2: R2Settings = R2Settings()  # type: ignore[call-arg]
    auth: AuthSettings = AuthSettings()  # type: ignore[call-arg]
    docai: DocumentAISettings = DocumentAISettings()  # type: ignore[call-arg]
    rag: RagSettings = RagSettings()  # type: ignore[call-arg]
    answer: AnswerSettings = AnswerSettings()  # type: ignore[call-arg]
    redis: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
