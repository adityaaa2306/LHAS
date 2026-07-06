import os
from dotenv import load_dotenv

load_dotenv()

_PLACEHOLDER_VALUES = frozenset({
    "",
    "api_key_here",
    "your_nvidia_api_key_here",
    "nvidia_api_key_here",
    "your_key",
    "your_openai_api_key_here",
})


def _env(name: str, default: str = "") -> str:
    """Read env var, treating template placeholders as unset."""
    value = os.getenv(name, default)
    if value is None:
        return default
    stripped = value.strip()
    if stripped.lower() in _PLACEHOLDER_VALUES:
        return default
    return stripped


class Settings:
    """Application settings from environment variables."""

    # API
    API_TITLE = "LHAS Dashboard API"
    API_VERSION = "1.0.0"
    API_DESCRIPTION = "Production-grade API for LHAS research mission dashboard"

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = ENVIRONMENT == "development"

    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/lhas",
    )
    SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_METHODS = ["*"]
    CORS_ALLOW_HEADERS = ["*"]

    # Pagination
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500

    # Paper Ingestion API Keys
    SEMANTIC_SCHOLAR_API_KEY = _env("SEMANTIC_SCHOLAR_API_KEY")
    PUBMED_API_KEY = _env("PUBMED_API_KEY")
    GROBID_URL = _env("GROBID_URL", "http://localhost:8070")

    # NVIDIA NIM Configuration (LLM Provider)
    NVIDIA_API_KEY = _env("NVIDIA_API_KEY")
    NVIDIA_BASE_URL = _env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL = _env("NVIDIA_MODEL", "deepseek-ai/deepseek-r1")
    NVIDIA_TEMPERATURE = float(_env("NVIDIA_TEMPERATURE", "0.6"))
    NVIDIA_TOP_P = float(_env("NVIDIA_TOP_P", "0.7"))
    NVIDIA_MAX_TOKENS = int(_env("NVIDIA_MAX_TOKENS", "4096"))

    # NVIDIA Embedding Model Configuration (falls back to NVIDIA_API_KEY if dedicated key unset)
    EMBEDDING_MODEL_API_KEY = _env("EMBEDDING_MODEL_API_KEY") or _env("NVIDIA_API_KEY")
    EMBEDDING_MODEL_NAME = _env("EMBEDDING_MODEL_NAME", "nvidia/llama-nemotron-embed-1b-v2")
    EMBEDDING_BASE_URL = _env("EMBEDDING_BASE_URL", "https://integrate.api.nvidia.com/v1")
    EMBEDDING_BATCH_SIZE = int(_env("EMBEDDING_BATCH_SIZE", "32"))

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
