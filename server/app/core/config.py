from functools import lru_cache
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


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()  # type: ignore[call-arg]
    r2: R2Settings = R2Settings()  # type: ignore[call-arg]
    auth: AuthSettings = AuthSettings()  # type: ignore[call-arg]
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
