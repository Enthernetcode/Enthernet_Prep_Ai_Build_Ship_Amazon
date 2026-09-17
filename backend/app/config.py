from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret: str = "change-me"
    log_level: str = "INFO"

    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60

    postgres_user: str = "eprep"
    postgres_password: str = "eprep"
    postgres_db: str = "eprep"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    redis_url: str = "redis://redis:6379/0"

    s3_endpoint_url: str = "http://minio:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "eprep-minio"
    s3_secret_key: str = "eprep-minio-secret"
    s3_bucket: str = "eprep-uploads"
    s3_region: str = "us-east-1"

    document_max_size_bytes: int = 26214400  # 25 MiB
    document_presign_ttl_seconds: int = 300
    document_chunk_size: int = 1000
    document_chunk_overlap: int = 150
    document_allowed_mimes: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        ]
    )

    gemini_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    aws_bedrock_region: str = ""

    llm_provider: str = "mock"           # mock | openai
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "mock"     # mock | openai
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    retrieval_default_k: int = 8
    retrieval_max_k: int = 50

    alexa_skill_id: str = ""
    alexa_client_id: str = ""
    alexa_client_secret: str = ""

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
