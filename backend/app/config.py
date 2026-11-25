"""Application settings, read from environment variables (or backend/.env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]  # the backend/ folder
load_dotenv(BASE_DIR / ".env")

def _env(name: str, default: str = "") -> str:
    """Read an environment variable, falling back to default when unset or blank."""
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return val.strip()


DOCS_DIR = BASE_DIR / "data" / "docs"  # curated knowledge base shipped with the project
UPLOADS_DIR = Path(_env("UPLOADS_DIR", str(BASE_DIR / "data" / "uploads")))  # PDFs added via the UI
MODELS_DIR = BASE_DIR / "models"  # trained ML models and their metrics
DB_PATH = Path(_env("DB_PATH", str(BASE_DIR / "data" / "agriassist.db")))

DEV_AUTH_SECRET = "dev-only-change-me"


@dataclass(frozen=True)
class Settings:
    llm_provider: str        # "openai" (or any OpenAI-compatible API), "gemini", or "none"
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    top_k: int
    min_confidence: float
    chunk_words: int
    chunk_overlap: int
    cors_origins: str
    max_upload_mb: int
    auth_secret: str
    token_hours: int
    weather_base_url: str    # Open-Meteo (no key needed)
    datagov_api_key: str     # data.gov.in key for Agmarknet mandi prices
    datagov_resource_id: str


def load_settings() -> Settings:
    return Settings(
        llm_provider=_env("LLM_PROVIDER", "none").lower(),
        llm_api_key=_env("LLM_API_KEY", ""),
        llm_model=_env("LLM_MODEL", ""),
        llm_base_url=_env("LLM_BASE_URL", "https://api.openai.com/v1"),
        top_k=int(_env("TOP_K", "4")),
        min_confidence=float(_env("MIN_CONFIDENCE", "0.10")),
        chunk_words=int(_env("CHUNK_WORDS", "120")),
        chunk_overlap=int(_env("CHUNK_OVERLAP", "20")),
        cors_origins=_env("CORS_ORIGINS", "*"),
        max_upload_mb=int(_env("MAX_UPLOAD_MB", "10")),
        auth_secret=_env("AUTH_SECRET", DEV_AUTH_SECRET),
        token_hours=int(_env("TOKEN_HOURS", "168")),
        weather_base_url=_env("WEATHER_BASE_URL", "https://api.open-meteo.com").rstrip("/"),
        datagov_api_key=_env("DATAGOV_API_KEY", ""),
        # Agmarknet "current daily prices" resource on data.gov.in. Verify the ID on data.gov.in if results are empty.
        datagov_resource_id=_env("DATAGOV_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070"),
    )


settings = load_settings()
