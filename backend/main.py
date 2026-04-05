"""
RAG Pipeline Optimizer - Main application file (modular architecture).

This file serves as the application entry point and orchestrates:
- FastAPI app initialization
- CORS middleware configuration
- Router registration for modular route handling
- Lifespan events for startup/shutdown
"""
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from dependencies import get_current_user
from config import get_settings
from dependencies import get_embeddings
from core.retrieval import load_existing_collections

settings = get_settings()

# Import route modules
from routes import (
    analytics,
    collections,
    upload,
    ask,
    chat,
    leaderboard,
    batch_eval,
    image_test,
    export,
    page_index,
    models,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown."""
    # Startup - run async without blocking
    print("[INFO] Starting RAG Pipeline Optimizer...")
    print("[OK] Server started (Supabase JWKS auth + service role storage enabled)")
    
    # Load collections in background (don't block startup)
    try:
        load_existing_collections()
        print("[OK] Collections loaded")
    except Exception as e:
        print(f"[WARN] Could not preload collections: {e}")
    
    # Initialize embeddings in background
    try:
        provider = (settings.embedding_provider or "huggingface").strip().lower()
        if provider == "huggingface":
            print(f"[INFO] Using HuggingFace embeddings: {settings.huggingface_model}")
        elif provider == "ollama":
            print(f"[INFO] Using Ollama embeddings: {settings.ollama_embed_model}")
        get_embeddings()
        print("[OK] Embeddings initialized")
    except Exception as e:
        print(f"[WARN] Could not initialize embeddings: {e}")
    
    yield
    
    # Shutdown
    print("🛑 Server shutting down...")


# =========================
# FastAPI App Initialization
# =========================
app = FastAPI(
    title="RAG Pipeline Optimizer",
    version="2.3",
    lifespan=lifespan
)

# =========================
# CORS Middleware
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Health Check Routes
# =========================
@app.get("/")
def home():
    """Health check endpoint."""
    return {"message": "Backend running [OK]"}


@app.get("/auth-check")
def auth_check(user=Depends(get_current_user)):
    """Authentication verification endpoint."""
    return {"ok": True, "user_id": user.get("sub"), "email": user.get("email")}


# =========================
# Router Registration
# =========================
app.include_router(collections.router, tags=["Collections"])
app.include_router(upload.router, tags=["Upload"])
app.include_router(ask.router, tags=["Ask"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(leaderboard.router, tags=["Leaderboard"])
app.include_router(batch_eval.router, tags=["Batch Evaluation"])
app.include_router(image_test.router, tags=["Image Test"])
app.include_router(page_index.router, tags=["PageIndex"])
app.include_router(analytics.router, tags=["Analytics"])
app.include_router(export.router, tags=["Export"])
app.include_router(models.router, tags=["Models"])


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
