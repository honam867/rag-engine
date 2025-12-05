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
    # Default query mode for RAG-Anything (e.g. "mix", "hybrid", "local").
    query_mode: str = "mix"
    # Logical model names for LLM and embeddings used by RAG-Anything.
    # These are passed through to the underlying client implementation.
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-large"


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
    redis: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
