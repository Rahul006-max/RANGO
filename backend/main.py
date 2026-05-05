"""
RAG Pipeline Optimizer - Minimal startup version
Ensures server starts quickly without blocking on heavy initialization.
"""
import os
import sys
import asyncio
import importlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Global flag for routes
routes_loaded = False

# ===== LIFESPAN HANDLER (doesn't block port binding) =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background task for non-critical startup work."""
    print("[INFO] Lifespan started - server listening on port")
    asyncio.create_task(load_existing_collections_async())
    yield
    print("[INFO] Server shutting down...")


def load_routes(app: FastAPI):
    """Load API routes at import time so the server never starts route-less."""
    global routes_loaded
    routers = [
        ("routes.collections", "Collections"),
        ("routes.upload", "Upload"),
        ("routes.ask", "Ask"),
        ("routes.chat", "Chat"),
        ("routes.leaderboard", "Leaderboard"),
        ("routes.batch_eval", "Batch Eval"),
        ("routes.image_test", "Image Test"),
        ("routes.export", "Export"),
        ("routes.page_index", "PageIndex"),
        ("routes.analytics", "Analytics"),
        ("routes.models", "Models"),
    ]

    loaded = 0
    for module_path, name in routers:
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "router") and module.router:
                app.include_router(module.router, tags=[name])
                loaded += 1
                print(f"[OK] Loaded {name} router")
        except Exception as e:
            print(f"[WARN] Could not load {name} router: {str(e)[:200]}")

    routes_loaded = loaded > 0
    print(f"[OK] Loaded {loaded}/{len(routers)} API routers")


async def load_existing_collections_async():
    """Load existing collections from database/disk into memory after binding."""
    try:
        print("[INFO] Scanning for existing collections...")
        from core.retrieval import load_existing_collections
        await asyncio.to_thread(load_existing_collections)
        print("[INFO] Loaded existing collections into memory")
    except Exception as e:
        print(f"[WARN] Failed to load existing collections: {e}")


# Create FastAPI app with lifespan handler
app = FastAPI(
    title="RAG Pipeline Optimizer",
    version="2.3",
    lifespan=lifespan
)

# Define allowed origins
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://rango-ruddy.vercel.app",
    "https://rango-er7c.onrender.com"
]

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_routes(app)

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
