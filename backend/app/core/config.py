from typing import Literal

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

    # Long TTL for memory hygiene, not correctness — model, task_type, and
    # output dimensionality are already part of the query-embedding cache
    # key, so a model change naturally produces fresh keys with no
    # explicit invalidation needed.
    embedding_cache_ttl_seconds: int = 2_592_000  # 30 days

    invite_token_expire_hours: int = 48

    # "local" writes uploaded PDFs to documents_storage_dir on whichever
    # machine handles the request — only correct when the API and worker
    # share a filesystem, as they do in docker-compose. "azure_blob" is
    # required once they run on separate hosts (Container Apps + a VM),
    # since there's no disk shared between them there.
    storage_backend: Literal["local", "azure_blob"] = "local"
    documents_storage_dir: str = "/app/data/documents"
    azure_storage_connection_string: str | None = None
    documents_blob_container: str = "documents"

    # Comma-separated list of origins allowed to call the API cross-origin.
    # Placeholder until the Static Web Apps domain exists (deployment Phase 3a).
    cors_allowed_origins: str = "https://PLACEHOLDER.azurestaticapps.net"


settings = Settings()
