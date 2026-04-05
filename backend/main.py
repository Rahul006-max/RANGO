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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings

settings = get_settings()

# Import route modules with error handling
try:
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
    routes_loaded = True
    print("[OK] All routes imported successfully")
except Exception as e:
    print(f"[WARN] Some routes failed to import: {e}")
    routes_loaded = False
    # Create empty module objects as fallbacks
    class EmptyRouter:
        router = None
    analytics = collections = upload = ask = chat = EmptyRouter()
    leaderboard = batch_eval = image_test = export = page_index = models = EmptyRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - minimal startup."""
    print("[INFO] RAG Pipeline Optimizer starting...")
    yield
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
# Health Check Endpoint
# =========================
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "RAG Pipeline Optimizer"}


# =========================
# Router Registration (with error handling)
# =========================
if routes_loaded:
    routers_to_include = [
        (collections, "Collections"),
        (upload, "Upload"),
        (ask, "Ask"),
        (chat, "Chat"),
        (leaderboard, "Leaderboard"),
        (batch_eval, "Batch Evaluation"),
        (image_test, "Image Test"),
        (page_index, "PageIndex"),
        (analytics, "Analytics"),
        (export, "Export"),
        (models, "Models"),
    ]
    
    for router_module, name in routers_to_include:
        try:
            if hasattr(router_module, 'router') and router_module.router:
                app.include_router(router_module.router, tags=[name])
        except Exception as e:
            print(f"[WARN] Could not include {name} router: {e}")
else:
    print("[WARN] Routes were not loaded, skipping router registration")


if __name__ == "__main__":
    try:
        import uvicorn
        port = int(os.getenv("PORT", 8002))
        print(f"[INFO] Starting server on 0.0.0.0:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        import traceback
        traceback.print_exc()
        raise
