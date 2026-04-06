"""
RAG Pipeline Optimizer - Minimal startup version
Ensures server starts quickly without blocking on heavy initialization.
"""
import os
import sys
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Global flag for routes
routes_loaded = False

# ===== LIFESPAN HANDLER (doesn't block port binding) =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background task to load routes."""
    print("[INFO] Lifespan started - server listening on port")
    # Create background task without awaiting (non-blocking)
    asyncio.create_task(load_routes_async(app))
    yield
    print("[INFO] Server shutting down...")


async def load_routes_async(app: FastAPI):
    """Load routes asynchronously in background."""
    global routes_loaded
    print("[INFO] Loading API routes in background...")
    await asyncio.sleep(0.1)  # Small delay to ensure port is bound
    
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
                
        routes_loaded = True
        print("[OK] All routes loaded successfully")
    except Exception as e:
        print(f"[WARN] Failed to load routes: {str(e)[:200]}")
        print("[INFO] Running in minimal mode")


# Create FastAPI app with lifespan handler
app = FastAPI(
    title="RAG Pipeline Optimizer",
    version="2.3",
    lifespan=lifespan
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "ok", "message": "RAG Pipeline Optimizer Backend Running"}

@app.get("/health")
def health():
    return {"status": "ok"}


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
