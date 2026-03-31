"""Central application configuration helpers."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppSettings:
    """All configurable values for the backend."""

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    jwt_secret: str
    jwks_url: str
    storage_bucket: str = "rag-pdfs"
    image_storage_bucket: str = "rag-images"
    collection_root: str = "collections"
    upload_root: str = "uploads"
    image_upload_root: str = os.path.join("uploads", "images")
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "huggingface")
    huggingface_model: str = os.getenv("HF_EMBED_MODEL", "all-MiniLM-L6-v2")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    ollama_llm_model: str = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:3b")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-specdec")
    groq_vision_model: str = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    vision_model_name: str = os.getenv("VISION_MODEL_NAME", "llava")
    vision_base_url: str = os.getenv("VISION_BASE_URL", "http://localhost:11434")
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173", "*")


def _build_settings() -> AppSettings:
    load_dotenv()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_anon_key or not supabase_service_role_key:
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", supabase_url),
                ("SUPABASE_ANON_KEY", supabase_anon_key),
                ("SUPABASE_SERVICE_ROLE_KEY", supabase_service_role_key),
            )
            if not value
        ]
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"

    return AppSettings(
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        supabase_service_role_key=supabase_service_role_key,
        jwt_secret=jwt_secret,
        jwks_url=jwks_url,
        storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "rag-pdfs"),
        image_storage_bucket=os.getenv("SUPABASE_IMAGE_BUCKET", "rag-images"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "huggingface"),
        huggingface_model=os.getenv("HF_EMBED_MODEL", "all-MiniLM-L6-v2"),
        ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        ollama_llm_model=os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:3b"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        groq_vision_model=os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        vision_model_name=os.getenv("VISION_MODEL_NAME", "llava"),
        vision_base_url=os.getenv("VISION_BASE_URL", "http://localhost:11434"),
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""
    return _build_settings()


# Backwards-compatible module-level exports for legacy imports
settings = get_settings()
SUPABASE_URL = settings.supabase_url
SUPABASE_ANON_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY = settings.supabase_service_role_key
STORAGE_BUCKET = settings.storage_bucket
JWKS_URL = settings.jwks_url