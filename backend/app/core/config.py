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

    # Groq is the primary provider for text generation (fact extraction,
    # briefs, assistant/copilot answers).
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"

    # Gemini is the fallback provider for those same text-generation calls
    # if Groq fails, and the sole provider for embeddings (Groq has no
    # embeddings API).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    invite_token_expire_hours: int = 48

    documents_storage_dir: str = "/app/data/documents"


settings = Settings()
