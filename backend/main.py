"""
RAG Pipeline Optimizer - Minimal startup version
Ensures server starts quickly without blocking on heavy initialization.
"""
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create minimal FastAPI app
app = FastAPI(
    title="RAG Pipeline Optimizer",
    version="2.3"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== BASIC ENDPOINTS =====
@app.get("/")
def home():
    return {"status": "ok", "message": "RAG Pipeline Optimizer Backend Running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ===== LOAD ROUTES AFTER STARTUP =====
@app.on_event("startup")
async def load_routes():
    """Load routes after server starts (doesn't block port binding)."""
    print("[INFO] Loading API routes...")
    try:
        from routes import (
            analytics, collections, upload, ask, chat,
            leaderboard, batch_eval, image_test, export,
            page_index, models
        )
        
        # Register all available routers
        routers = [
            (collections, "Collections"),
            (upload, "Upload"),
            (ask, "Ask"),
            (chat, "Chat"),
            (leaderboard, "Leaderboard"),
            (batch_eval, "Batch Eval"),
            (image_test, "Image Test"),
            (export, "Export"),
            (page_index, "PageIndex"),
            (analytics, "Analytics"),
            (models, "Models"),
        ]
        
        for module, name in routers:
            try:
                if hasattr(module, 'router') and module.router:
                    app.include_router(module.router, tags=[name])
                    print(f"[OK] Loaded {name} router")
            except Exception as e:
                print(f"[WARN] Could not load {name} router: {str(e)[:100]}")
                
        print("[OK] Route loading complete")
    except Exception as e:
        print(f"[WARN] Failed to load routes: {str(e)[:200]}")
        print("[INFO] Running in minimal mode")


if __name__ == "__main__":
    try:
        import uvicorn
        port = int(os.getenv("PORT", 8002))
        print(f"[INFO] Starting RAG Pipeline Optimizer on 0.0.0.0:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        print(f"[ERROR] Failed to start: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
