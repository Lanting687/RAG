from pathlib import Path
from typing import List
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str
    gemini_chat_endpoint: AnyUrl
    gemini_embeddings_endpoint: AnyUrl
    gemini_chat_fallback_models: str | None = None

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str
    qdrant_collection_name: str = "documents"

    cors_origins: List[str] = ["http://localhost:5173"]

    confluence_base_url: str | None = None
    confluence_username: str | None = None
    confluence_api_token: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    class Config:
        env_file = str(Path(__file__).resolve().parents[1] / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
