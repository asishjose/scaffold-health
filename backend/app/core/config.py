from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://scaffold:scaffold@localhost:5433/scaffold"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    clinic_registration_code: str = "DEV-CLINIC-CODE"

    # Groq handles fact extraction and brief generation (chat completions).
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"

    # Groq has no embeddings API — Gemini fills that one gap in the pipeline.
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "gemini-embedding-001"

    invite_token_expire_hours: int = 48

    documents_storage_dir: str = "/app/data/documents"


settings = Settings()
