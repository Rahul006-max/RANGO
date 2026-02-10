import os
import time
import shutil
import re
import uuid
import json
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional

import asyncio
import csv
from io import StringIO
import random
import traceback

import jwt  # ✅ pyjwt
from jwt import PyJWKClient

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import base64

from dotenv import load_dotenv
from supabase import create_client

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

from dateutil.relativedelta import relativedelta
import tiktoken


# =========================
# ENV / SUPABASE
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "rag-pdfs").strip()

if not SUPABASE_URL:
    print("❌ SUPABASE_URL not found in .env")
if not SUPABASE_ANON_KEY:
    print("❌ SUPABASE_ANON_KEY not found in .env")
if not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY not found in .env (needed for Option A storage upload)")

# admin client (bypasses RLS) ✅ backend only
supabase_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# =========================
# ✅ JWT VERIFY (JWKS)
# =========================
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwk_client = PyJWKClient(JWKS_URL)


def verify_supabase_jwt(token: str):
    """
    ✅ Correct verification for Supabase tokens (ES256 / RS256)
    Uses Supabase JWKS public keys.
    """
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token).key

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256"],  # ✅ important
            options={
                "verify_exp": True,
                "verify_aud": False,  # ✅ Disable audience verification for Supabase
                "verify_iss": True,   # Keep issuer verification
            },
        )

        # ✅ store the raw access token for Supabase postgrest auth()
        payload["access_token"] = token
        return payload

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"JWT verification failed: {str(e)}")


def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    return verify_supabase_jwt(token)


def get_supabase_user_client(access_token: str):
    """
    ✅ Proper for your installed supabase-py:
    - enables RLS DB with postgrest.auth(token)
    """
    sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sb.postgrest.auth(access_token)
    return sb


# =========================
# Globals (Local + Cache)
# =========================
PIPELINE_DB_PATHS = {}
QA_CACHE = {}
COLLECTION_FULLTEXT = {}

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ✅ 4 System Pipelines (ALWAYS run in both FAST and COMPARE modes)
SYSTEM_PIPELINES = [
    {"name": "Balanced (MMR)", "chunk_size": 800, "overlap": 120, "search_type": "mmr", "k": 6},
    {"name": "Fastest (Similarity)", "chunk_size": 500, "overlap": 60, "search_type": "similarity", "k": 4},
    {"name": "Accurate (Similarity + Larger k)", "chunk_size": 900, "overlap": 150, "search_type": "similarity", "k": 8},
    {"name": "DeepSearch (MMR + Higher k)", "chunk_size": 1200, "overlap": 200, "search_type": "mmr", "k": 10},
]

# Legacy alias for backwards compatibility
PIPELINES = SYSTEM_PIPELINES

llm = OllamaLLM(model="qwen2.5:3b")


# =========================
# Helpers
# =========================
def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def split_documents(documents, chunk_size=500, chunk_overlap=100):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(documents)


def safe_delete_folder(path: str):
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def build_vectordb_for_pipeline(documents, chunk_size, chunk_overlap, persist_dir):
    safe_delete_folder(persist_dir)
    chunks = split_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir
    )

    return vectordb, chunks, persist_dir


def dedupe_docs(docs):
    seen = set()
    unique = []
    for d in docs:
        key = normalize(d.page_content[:400])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def docs_to_fulltext(documents):
    return clean_text("\n\n".join([d.page_content for d in documents]))


def normalize_search_type(search_type: str) -> str:
    """Map any search_type to LangChain-allowed values: similarity, mmr, similarity_score_threshold."""
    if not search_type:
        return 'similarity'

    s = str(search_type).lower().strip()

    # ✅ Already allowed by LangChain VectorStoreRetriever
    allowed = {'similarity', 'similarity_score_threshold', 'mmr'}
    if s in allowed:
        return s

    # ✅ Map UI-friendly labels to allowed values
    if s == 'semantic':
        return 'similarity'

    if s == 'hybrid':
        return 'mmr'  # Best fallback for deep search

    if s == 'bm25':
        return 'similarity'  # BM25 not supported by Chroma

    # Default fallback
    return 'similarity'

def jitter_int(value: int, delta: int, min_val: int = 1):
    return max(min_val, int(value + random.uniform(-delta, delta)))


def randomized_weights():
    weights = {
        "relevance": random.uniform(0.35, 0.45),
        "grounded": random.uniform(0.25, 0.35),
        "quality": random.uniform(0.15, 0.25),
        "efficiency": random.uniform(0.05, 0.15),
    }
    s = sum(weights.values())
    return {k: round(v / s, 3) for k, v in weights.items()}



# =========================
# Pipeline Config Helpers
# =========================
DEFAULT_PIPELINE_CONFIG = {
    'preset_name': 'Balanced',
    'chunk_size': 800,
    'overlap': 120,
    'top_k': 6,
    'search_type': 'mmr'
}


def parse_pipeline_config_from_any(raw):
    """Accept dict, JSON-string, None. Returns dict or None."""
    if raw is None:
        return None

    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    return None


def db_get_collection_pipeline_config(sb, collection_id: str, user_id: str):
    """Fetch pipeline_config from rag_collections. Returns dict or None."""
    try:
        res = sb.table("rag_collections") \
            .select("pipeline_config") \
            .eq("id", collection_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        if res.data and res.data.get("pipeline_config"):
            return res.data["pipeline_config"]
    except Exception:
        pass
    return None


# =========================
# Timing & Token Helpers
# =========================
def now_ms():
    """Return current time in milliseconds for precise timing."""
    return int(time.perf_counter() * 1000)


def safe_int(x):
    """Safely convert to int, return None on failure."""
    try:
        return int(x)
    except Exception:
        return None


def extract_tokens_from_llm_response(llm_response) -> dict:
    """Best-effort token extraction from LLM response."""
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None

    try:
        # Try OpenAI-like response.usage attribute
        if hasattr(llm_response, "usage"):
            usage = llm_response.usage
            prompt_tokens = safe_int(getattr(usage, "prompt_tokens", None))
            completion_tokens = safe_int(getattr(usage, "completion_tokens", None))
            total_tokens = safe_int(getattr(usage, "total_tokens", None))
        # Try dict-like access
        elif isinstance(llm_response, dict) and "usage" in llm_response:
            usage = llm_response["usage"]
            prompt_tokens = safe_int(usage.get("prompt_tokens"))
            completion_tokens = safe_int(usage.get("completion_tokens"))
            total_tokens = safe_int(usage.get("total_tokens"))
    except Exception:
        pass

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens
    }


def estimate_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Estimate token count for text using tiktoken."""
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception:
        # Fallback: rough estimate of 4 chars per token
        return len(text) // 4


def estimate_cost_usd(tokens: dict, model: str = "qwen2.5:3b") -> Optional[float]:
    """Estimate cost based on token usage. Ollama is free, so return 0.0."""
    try:
        total = tokens.get("total_tokens")
        if not total:
            return 0.0
        # Ollama models are free (local)
        if "ollama" in model.lower() or "qwen" in model.lower():
            return 0.0
        # Default rate for other models: ~$0.50 per 1M tokens
        rate_per_token = 0.0000005
        return round(total * rate_per_token, 6)
    except Exception:
        return 0.0


# =========================
# Duration Logic
# =========================
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}


def duration_question(question: str) -> bool:
    q = question.lower()
    keywords = ["how many months", "duration", "how long", "total time", "last", "internship lasted"]
    return any(k in q for k in keywords)


def parse_date_from_text(text: str):
    text = text.lower()
    pattern = r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,)?\s+(20\d{2})"
    matches = re.findall(pattern, text)

    dates = []
    for month_name, day, year in matches:
        try:
            dt = datetime(int(year), MONTH_MAP[month_name], int(day))
            dates.append(dt)
        except:
            pass
    return dates


def compute_duration(start: datetime, end: datetime):
    if end < start:
        start, end = end, start

    days = (end - start).days
    weeks = round(days / 7, 1)

    rd = relativedelta(end, start)
    months = rd.years * 12 + rd.months

    return {"months": months, "weeks": weeks, "days": days}


def enrich_answer_if_duration(question: str, context: str, base_answer: str):
    if not duration_question(question):
        return base_answer

    dates = parse_date_from_text(context)
    if len(dates) >= 2:
        start_date = dates[0]
        end_date = dates[1]
        dur = compute_duration(start_date, end_date)

        return (
            f"The internship lasted {dur['months']} months "
            f"(~{dur['weeks']} weeks, {dur['days']} days) "
            f"({start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')})."
        )

    return base_answer


# =========================
# Scoring System
# =========================
def context_quality_score(context: str):
    length = len(context)
    if length < 150:
        return 3
    if length <= 1200:
        return 10
    if length <= 2500:
        return 7
    return 5


def efficiency_score(context: str, top_k: int):
    length = len(context)
    score = 10

    if top_k >= 12:
        score -= 4
    elif top_k >= 10:
        score -= 3
    elif top_k >= 8:
        score -= 2
    elif top_k >= 6:
        score -= 1

    if length > 3000:
        score -= 3
    elif length > 2000:
        score -= 2
    elif length > 1200:
        score -= 1

    return max(0, min(10, score))


def relevance_score(question: str, context: str):
    q = normalize(question)
    ctx = normalize(context)

    q_words = [w for w in q.split() if len(w) >= 4]
    if not q_words:
        return 5

    hits = sum(1 for w in q_words if w in ctx)
    ratio = hits / len(q_words)

    if ratio >= 0.6:
        return 10
    if ratio >= 0.4:
        return 8
    if ratio >= 0.25:
        return 6
    return 3


def grounded_score(answer: str, context: str):
    ans = normalize(answer)
    ctx = normalize(context)

    if not ans or "i dont know" in ans or "i don't know" in ans:
        return 6

    ans_words = [w for w in ans.split() if len(w) >= 4]
    if not ans_words:
        return 5

    hits = sum(1 for w in ans_words if w in ctx)
    ratio = hits / len(ans_words)

    if ratio >= 0.6:
        return 10
    if ratio >= 0.4:
        return 8
    if ratio >= 0.25:
        return 6
    return 3


def pipeline_score(question: str, context: str, top_k: int, answer: str = "", weights: dict | None = None):
    rel = relevance_score(question, context)
    qual = context_quality_score(context)
    eff = efficiency_score(context, top_k)
    gro = grounded_score(answer, context) if answer else 5

    w = weights or {
        "relevance": 0.4,
        "grounded": 0.35,
        "quality": 0.15,
        "efficiency": 0.10
    }

    final = round(
        (w["relevance"] * rel) +
        (w["grounded"] * gro) +
        (w["quality"] * qual) +
        (w["efficiency"] * eff),
        2
    )

    return {
        "relevance": rel,
        "grounded": gro,
        "quality": qual,
        "efficiency": eff,
        "final": final,
        "weights": w
    }



# =========================
# Smart Extract (email/phone/address)
# =========================
def is_address_question(q: str) -> bool:
    q = q.lower()
    return ("address" in q) or ("located" in q) or ("location" in q)


def is_email_question(q: str) -> bool:
    q = q.lower()
    return ("email" in q) or ("mail id" in q) or ("gmail" in q)


def is_phone_question(q: str) -> bool:
    q = q.lower()
    return ("phone" in q) or ("mobile" in q) or ("contact" in q)


def extract_email(text: str):
    match = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match[0] if match else None


def extract_phone(text: str):
    match = re.findall(r"(?:\+?\d{1,3}[-\s]?)?\b\d{10}\b", text)
    return match[0] if match else None


def extract_address_like_chunk(text: str):
    t = clean_text(text)
    low = t.lower()

    markers = [
        "address:", "registered office", "corporate office",
        "head office", "office address"
    ]

    for m in markers:
        idx = low.find(m)
        if idx != -1:
            start = max(0, idx - 50)
            end = min(len(t), idx + 400)
            return t[start:end].strip()

    pin_match = re.search(r"\b\d{6}\b", t)
    if pin_match:
        idx = pin_match.start()
        start = max(0, idx - 200)
        end = min(len(t), idx + 200)
        block = t[start:end]

        india_idx = block.lower().find("india")
        if india_idx != -1:
            block = block[: india_idx + len("india")]

        return block.strip()

    for key in ["bengaluru", "bangalore"]:
        idx = low.find(key)
        if idx != -1:
            start = max(0, idx - 120)
            end = min(len(t), idx + 260)
            return t[start:end].strip()

    return None


def smart_extract_answer(question: str, text: str):
    ctx = clean_text(text)

    if is_email_question(question):
        email = extract_email(ctx)
        if email:
            return email

    if is_phone_question(question):
        phone = extract_phone(ctx)
        if phone:
            return phone

    if is_address_question(question):
        addr = extract_address_like_chunk(ctx)
        if addr:
            return f"Company Address: {addr}"

    return None


# =========================
# LLM Answer with Retry
# =========================
def generate_answer_with_retry(question: str, context: str):
    """Generate answer with retry logic. Returns (answer, retry_meta, token_usage)."""
    normal_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant.
Answer the question ONLY using the context below.
If the answer is not in the context, say: "I don't know based on the documents."
Answer in 1 line.

Context:
{context}

Question:
{question}

Answer:
""")

    strict_prompt = ChatPromptTemplate.from_template("""
You are an answer extraction system.

RULES:
- Use ONLY the provided context.
- Return ONLY the final answer (no explanation).
- If the answer is not present, return exactly: I don't know based on the documents.

Context:
{context}

Question:
{question}

Final Answer:
""")

    # Track token usage
    prompt1_text = normal_prompt.format(context=context, question=question)
    chain1 = normal_prompt | llm
    a1 = str(chain1.invoke({"context": context, "question": question})).strip()
    g1 = grounded_score(a1, context)
    
    prompt_tokens = estimate_tokens(prompt1_text)
    completion_tokens = estimate_tokens(a1)

    if g1 < 6:
        prompt2_text = strict_prompt.format(context=context, question=question)
        chain2 = strict_prompt | llm
        a2 = str(chain2.invoke({"context": context, "question": question})).strip()
        g2 = grounded_score(a2, context)
        
        # Add second attempt tokens
        prompt_tokens += estimate_tokens(prompt2_text)
        completion_tokens += estimate_tokens(a2)

        if g2 >= g1:
            token_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
            return a2, {"attempts": 2, "grounded_before": g1, "grounded_after": g2}, token_usage

        token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
        return a1, {"attempts": 2, "grounded_before": g1, "grounded_after": g1}, token_usage

    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens
    }
    return a1, {"attempts": 1, "grounded_before": g1, "grounded_after": g1}, token_usage


# =========================
# Models
# =========================
class CustomPipelineConfig(BaseModel):
    enabled: bool = False
    preset_name: str = 'Custom'
    chunk_size: int = 800
    overlap: int = 120
    top_k: int = 6
    search_type: str = 'mmr'


class AskRequest(BaseModel):
    question: str
    collection_id: str
    mode: str = "fast"
    custom_pipeline: Optional[CustomPipelineConfig] = None


class RenameRequest(BaseModel):
    name: str


class ChatRequest(BaseModel):
    question: str
    collection_id: str


class PipelineConfigRequest(BaseModel):
    preset_name: str
    chunk_size: int
    overlap: int
    top_k: int
    search_type: str


class ChunkRow(BaseModel):
    id: str
    file_id: str
    filename: Optional[str] = None
    pipeline_name: Optional[str] = None
    chunk_size: Optional[int] = None
    overlap: Optional[int] = None
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    chunk_text: str
    created_at: Optional[str] = None


class ChunkListResponse(BaseModel):
    collection_id: str
    total: int
    limit: int
    offset: int
    chunks: List[ChunkRow]


class BatchEvalQuestion(BaseModel):
    question: str
    expected_answer: Optional[str] = None


class BatchEvalRequest(BaseModel):
    mode: str = "fast"
    items: List[BatchEvalQuestion]
    dataset_name: Optional[str] = None
    pipeline_config: Optional[dict] = None


class BatchEvalItemResult(BaseModel):
    id: str
    question: str
    expected_answer: Optional[str] = None
    best_pipeline: Optional[str] = None
    final_answer: Optional[str] = None
    scores: Optional[dict] = None
    latency: Optional[dict] = None
    tokens: Optional[dict] = None
    created_at: Optional[str] = None


class BatchEvalRunResponse(BaseModel):
    run_id: str
    status: str
    total_questions: int
    completed_questions: int
    avg_final_score: float
    items: List[BatchEvalItemResult]


# =========================
# Startup (Load local chroma)
# =========================
def load_existing_collections():
    collections_root = "collections"
    if not os.path.exists(collections_root):
        return

    for collection_id in os.listdir(collections_root):
        folder_path = os.path.join(collections_root, collection_id)
        if not os.path.isdir(folder_path):
            continue

        collection_db_paths = {}
        for p in PIPELINES:
            pipeline_folder = os.path.join(folder_path, f"chroma_{p['name'].replace(' ', '_').lower()}")
            if os.path.exists(pipeline_folder):
                collection_db_paths[p["name"]] = pipeline_folder

        if collection_db_paths:
            PIPELINE_DB_PATHS[collection_id] = collection_db_paths
            QA_CACHE.setdefault(collection_id, {})


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_existing_collections()
    print("✅ Server started (Supabase JWKS auth + service role storage enabled)")
    yield
    print("🛑 Server shutting down...")


# =========================
# FastAPI
# =========================
app = FastAPI(title="RAG Pipeline Optimizer", version="2.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Routes
# =========================
@app.get("/")
def home():
    return {"message": "Backend running ✅"}


@app.get("/auth-check")
def auth_check(user=Depends(get_current_user)):
    return {"ok": True, "user_id": user.get("sub"), "email": user.get("email")}


# -------------------------
# Collections
# -------------------------
@app.get("/collections")
def list_collections(user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]

    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_collections") \
        .select("id,name,created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    return {"collections": res.data or []}


@app.post("/collections/{collection_id}/rename")
def rename_collection(collection_id: str, data: RenameRequest, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    new_name = (data.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    sb.table("rag_collections").update({"name": new_name}) \
        .eq("id", collection_id).eq("user_id", user_id).execute()

    return {"status": "renamed ✅", "collection_id": collection_id, "new_name": new_name}


@app.delete("/collections/{collection_id}")
def delete_collection(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    folder_path = os.path.join("collections", collection_id)
    safe_delete_folder(folder_path)

    PIPELINE_DB_PATHS.pop(collection_id, None)
    QA_CACHE.pop(collection_id, None)
    COLLECTION_FULLTEXT.pop(collection_id, None)

    sb.table("rag_chat_history").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_compare_results").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_pipeline_builds").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_chunks").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_files").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_chat_messages").delete().eq("collection_id", collection_id).eq("user_id", user_id).execute()
    sb.table("rag_collections").delete().eq("id", collection_id).eq("user_id", user_id).execute()

    return {"status": "deleted ✅", "collection_id": collection_id}


@app.post("/collections/{collection_id}/rebuild-index")
async def rebuild_index(collection_id: str, user=Depends(get_current_user)):
    """Rebuild local vectorstore from Supabase files for an existing collection."""
    start = time.time()
    
    try:
        if not supabase_admin:
            raise HTTPException(status_code=500, detail="SERVICE ROLE KEY missing")

        access_token = user["access_token"]
        user_id = user["sub"]
        sb = get_supabase_user_client(access_token)

        # ✅ Verify ownership
        try:
            collection_res = sb.table("rag_collections").select("id,name").eq("id", collection_id).eq("user_id", user_id).single().execute()
            if not collection_res.data:
                raise HTTPException(status_code=400, detail="Invalid collection_id. Collection not found or access denied.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Collection validation failed: {str(e)}")

        # ✅ Get all files for this collection
        try:
            files_res = sb.table("rag_files").select("id,filename,storage_path").eq("collection_id", collection_id).eq("user_id", user_id).execute()
            
            if not files_res.data:
                raise HTTPException(status_code=400, detail="No files found in this collection. Upload PDFs first.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch files: {str(e)}")

        # ✅ Download and process PDFs
        os.makedirs("uploads", exist_ok=True)
        os.makedirs("collections", exist_ok=True)

        all_documents = []
        failed_files = []
        
        for file_row in files_res.data:
            try:
                # Download from Supabase storage
                file_data = supabase_admin.storage.from_(STORAGE_BUCKET).download(file_row["storage_path"])
                
                # Save temporarily
                temp_path = os.path.join("uploads", f"{collection_id}_{file_row['filename']}")
                with open(temp_path, "wb") as f:
                    f.write(file_data)

                # Load PDF
                loader = PyPDFLoader(temp_path)
                docs = loader.load()
                all_documents.extend(docs)
            except Exception as e:
                print(f"⚠️ Error loading {file_row['filename']}: {e}")
                failed_files.append(file_row['filename'])
                continue

        if not all_documents:
            if failed_files:
                raise HTTPException(status_code=500, detail=f"Failed to load all documents. Failed files: {', '.join(failed_files)}")
            else:
                raise HTTPException(status_code=400, detail="No documents could be loaded from storage")

        # ✅ Store fulltext
        COLLECTION_FULLTEXT[collection_id] = docs_to_fulltext(all_documents)

        # ✅ Build all 4 system pipelines with normalized search types
        collection_folder = os.path.join("collections", collection_id)
        os.makedirs(collection_folder, exist_ok=True)

        collection_db_paths = {}
        total_chunks = 0

        for p in SYSTEM_PIPELINES:
            try:
                db_path = os.path.join(collection_folder, f"chroma_{p['name'].replace(' ', '_').lower()}")
                
                _, chunks, final_path = build_vectordb_for_pipeline(
                    all_documents,
                    chunk_size=p["chunk_size"],
                    chunk_overlap=p["overlap"],
                    persist_dir=db_path
                )

                collection_db_paths[p["name"]] = final_path
                total_chunks += len(chunks)

                # ✅ Update pipeline builds table with normalized search_type
                sb.table("rag_pipeline_builds").upsert({
                    "user_id": user_id,
                    "collection_id": collection_id,
                    "pipeline_name": p["name"],
                    "chunk_size": p["chunk_size"],
                    "overlap": p["overlap"],
                    "search_type": normalize_search_type(p["search_type"]),  # ✅ Ensure LangChain compatibility
                    "top_k": p["k"],
                    "chunks_created": len(chunks),
                    "build_time_sec": 0,
                }, on_conflict="user_id,collection_id,pipeline_name").execute()
            except Exception as e:
                print(f"⚠️ Error building pipeline {p['name']}: {e}")
                # Continue with other pipelines
                continue

        if not collection_db_paths:
            raise HTTPException(status_code=500, detail="Failed to build any pipelines. Check server logs.")

        PIPELINE_DB_PATHS[collection_id] = collection_db_paths
        QA_CACHE.setdefault(collection_id, {})

        elapsed = round(time.time() - start, 2)

        return {
            "ok": True,
            "collection_id": collection_id,
            "message": "Index rebuilt successfully",
            "chunks_created": total_chunks,
            "chunks_deleted": 0,  # Not tracking deletes for now
            "time_taken_sec": elapsed,
            "pipelines_rebuilt": len(collection_db_paths),
            "failed_files": failed_files if failed_files else []
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print("❌ REBUILD INDEX ERROR:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Rebuild index failed: {str(e)}")


@app.get("/collections/{collection_id}/pipeline-config")
def get_pipeline_config(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_collections") \
        .select("pipeline_config") \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {
        "collection_id": collection_id,
        "pipeline_config": res.data.get("pipeline_config")
    }


@app.post("/collections/{collection_id}/pipeline-config")
def save_pipeline_config(
    collection_id: str,
    config: PipelineConfigRequest,
    user=Depends(get_current_user)
):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    config_dict = {
        "preset_name": config.preset_name,
        "chunk_size": config.chunk_size,
        "overlap": config.overlap,
        "top_k": config.top_k,
        "search_type": config.search_type,
    }

    sb.table("rag_collections").update({"pipeline_config": config_dict}) \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .execute()
    
    return {
        "ok": True,
        "collection_id": collection_id,
        "pipeline_config": config_dict
    }


@app.get("/collections/{collection_id}/custom-pipeline")
def get_custom_pipeline(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_collections") \
        .select("custom_pipeline_config") \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {
        "collection_id": collection_id,
        "custom_pipeline": res.data.get("custom_pipeline_config")
    }


@app.post("/collections/{collection_id}/custom-pipeline")
def save_custom_pipeline(
    collection_id: str,
    config: CustomPipelineConfig,
    user=Depends(get_current_user)
):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    config_dict = {
        "enabled": config.enabled,
        "preset_name": config.preset_name,
        "chunk_size": config.chunk_size,
        "overlap": config.overlap,
        "top_k": config.top_k,
        "search_type": config.search_type,
    }

    sb.table("rag_collections").update({"custom_pipeline_config": config_dict}) \
        .eq("id", collection_id) \
        .eq("user_id", user_id) \
        .execute()

    return {
        "ok": True,
        "collection_id": collection_id,
        "custom_pipeline": config_dict
    }


# -------------------------
# Upload Multi (Supabase + local chroma)
# -------------------------
@app.post("/upload-multi")
async def upload_multiple_pdfs(
    files: List[UploadFile] = File(...),
    collection_id: Optional[str] = None,
    pipeline_config: Optional[str] = None,
    user=Depends(get_current_user),
):
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="SERVICE ROLE KEY missing in backend .env")

    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    start = time.time()
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("collections", exist_ok=True)

    if collection_id:
        cid = collection_id
    else:
        cid = str(uuid.uuid4())
        sb.table("rag_collections").insert({
            "id": cid,
            "user_id": user_id,
            "name": f"Collection {cid[:8]}",
        }).execute()

    collection_folder = os.path.join("collections", cid)
    os.makedirs(collection_folder, exist_ok=True)

    all_documents = []
    uploaded_file_names = []

    # store pipeline build stats
    pipeline_build_stats = {}

    for f in files:
        file_path = os.path.join("uploads", f"{cid}_{f.filename}")
        with open(file_path, "wb") as out:
            out.write(await f.read())

        loader = PyPDFLoader(file_path)
        docs = loader.load()
        all_documents.extend(docs)

        storage_path = f"{user_id}/{cid}/{str(uuid.uuid4())}_{f.filename}"

        with open(file_path, "rb") as fp:
            supabase_admin.storage.from_(STORAGE_BUCKET).upload(
                storage_path,
                fp,
                {"content-type": "application/pdf"}
            )

        sb.table("rag_files").insert({
            "user_id": user_id,
            "collection_id": cid,
            "filename": f.filename,
            "storage_path": storage_path
        }).execute()

        uploaded_file_names.append(f.filename)

    COLLECTION_FULLTEXT[cid] = docs_to_fulltext(all_documents)

    # ✅ Always build 4 SYSTEM_PIPELINES
    pipelines_to_build = SYSTEM_PIPELINES.copy()

    pipeline_stats = {}
    collection_db_paths = {}

    # build pipelines
    for p in pipelines_to_build:
        pipeline_start = time.time()

        db_path = os.path.join(collection_folder, f"chroma_{p['name'].replace(' ', '_').lower()}")

        _, chunks, final_path = build_vectordb_for_pipeline(
            all_documents,
            chunk_size=p["chunk_size"],
            chunk_overlap=p["overlap"],
            persist_dir=db_path
        )

        build_time_sec = round(time.time() - pipeline_start, 3)

        collection_db_paths[p["name"]] = final_path

        pipeline_stats[p["name"]] = {
            "chunks_created": len(chunks),
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": p["k"],
            "build_time_sec": build_time_sec,
        }

        # ✅ store in supabase rag_pipeline_builds
        sb.table("rag_pipeline_builds").insert({
            "user_id": user_id,
            "collection_id": cid,
            "pipeline_name": p["name"],
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": p["k"],
            "chunks_created": len(chunks),
            "build_time_sec": build_time_sec,
        }).execute()

    PIPELINE_DB_PATHS[cid] = collection_db_paths
    QA_CACHE.setdefault(cid, {})

    elapsed = round(time.time() - start, 2)

    return {
        "status": "success ✅",
        "collection_id": cid,
        "files_uploaded": uploaded_file_names,
        "pages_loaded": len(all_documents),
        "pipelines_built": pipeline_stats,
        "total_time_taken_sec": elapsed,
    }


# -------------------------
# Files (PDF Viewer)
# -------------------------
@app.get("/collections/{collection_id}/files")
def list_collection_files(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_files") \
        .select("id,filename,storage_path,created_at") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    return {"files": res.data or []}


@app.get("/collections/{collection_id}/files/{file_id}/signed-url")
def get_signed_pdf_url(collection_id: str, file_id: str, user=Depends(get_current_user)):
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="SERVICE ROLE KEY missing")

    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_files") \
        .select("id,storage_path,filename") \
        .eq("id", file_id) \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="File not found")

    storage_path = res.data[0]["storage_path"]

    signed = supabase_admin.storage.from_(STORAGE_BUCKET).create_signed_url(storage_path, 600)

    return {
        "filename": res.data[0]["filename"],
        "signed_url": signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    }


# -------------------------
# History
# -------------------------
@app.get("/collections/{collection_id}/history")
def get_collection_history(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_chat_history") \
        .select("question,answer,mode,best_pipeline,created_at,citations") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()

    return {"collection_id": collection_id, "history": res.data or []}


@app.delete("/collections/{collection_id}/history")
def clear_collection_history(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    sb.table("rag_chat_history").delete() \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .execute()

    return {"status": "cleared ✅", "collection_id": collection_id}


# -------------------------
# Leaderboard
# -------------------------
@app.get("/collections/{collection_id}/leaderboard")
def get_leaderboard(
    collection_id: str,
    mode: str = "all",
    range: str = "30d",
    user=Depends(get_current_user)
):
    """
    ✅ Enhanced leaderboard with mode and time range filters.
    
    Query params:
    - mode: all|fast|compare|chat (default: all)
    - range: 7d|30d|all (default: 30d)
    
    Returns pipeline stats with wins, win_rate, avg scores, and avg timings.
    """
    try:
        access_token = user["access_token"]
        user_id = user["sub"]
        sb = get_supabase_user_client(access_token)

        # ✅ Parse filters
        mode = (mode or "all").lower().strip()
        range_filter = (range or "30d").lower().strip()
        
        # ✅ Build time filter
        cutoff_date = None
        if range_filter == "7d":
            cutoff_date = datetime.now() - relativedelta(days=7)
        elif range_filter == "30d":
            cutoff_date = datetime.now() - relativedelta(days=30)
        # range_filter == "all" → no cutoff
        
        # ✅ Query rag_chat_history with filters
        query = sb.table("rag_chat_history") \
            .select("best_pipeline,retrieval_comparison,created_at,mode,metrics") \
            .eq("collection_id", collection_id) \
            .eq("user_id", user_id)
        
        # Apply time filter
        if cutoff_date:
            query = query.gte("created_at", cutoff_date.isoformat())
        
        # Apply mode filter
        if mode != "all":
            query = query.eq("mode", mode)
        
        res = query.order("created_at", desc=False).execute()
        
        # ✅ Get chat message count (always all time for engagement)
        chat_res = sb.table("rag_chat_messages") \
            .select("id", count="exact") \
            .eq("collection_id", collection_id) \
            .eq("user_id", user_id) \
            .execute()

        rows = res.data or []
        chat_count = chat_res.count or 0
        total_questions = len(rows)
        
        if not rows:
            return {
                "collection_id": collection_id,
                "mode": mode,
                "range": range_filter,
                "total_questions": 0,
                "chat_interactions": chat_count,
                "best_pipeline_today": None,
                "pipelines": []
            }

        # ✅ Compute stats per pipeline
        stats = {}

        for r in rows:
            best = r.get("best_pipeline")
            if best:
                stats.setdefault(best, {
                    "pipeline": best,
                    "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0,
                    "avg_llm_time_sec": 0,
                    "avg_total_time_sec": 0,
                    "samples": 0,
                })
                stats[best]["wins"] += 1

            comp = r.get("retrieval_comparison") or []
            metrics = r.get("metrics") or {}
            
            for p in comp:
                name = p.get("pipeline")
                if not name:
                    continue

                final_score = (p.get("scores") or {}).get("final", 0)
                rt = p.get("retrieval_time_sec", 0)
                
                # Extract timing info from metrics if available
                timings = metrics.get("timings_ms") or {}
                llm_time = metrics.get("llm_time_sec", 0)
                total_time = (timings.get("total_ms", 0) / 1000.0) if timings.get("total_ms") else 0

                stats.setdefault(name, {
                    "pipeline": name,
                    "wins": 0,
                    "avg_final_score": 0,
                    "avg_retrieval_time_sec": 0,
                    "avg_llm_time_sec": 0,
                    "avg_total_time_sec": 0,
                    "samples": 0,
                })

                stats[name]["avg_final_score"] += float(final_score or 0)
                stats[name]["avg_retrieval_time_sec"] += float(rt or 0)
                stats[name]["avg_llm_time_sec"] += float(llm_time or 0)
                stats[name]["avg_total_time_sec"] += float(total_time or 0)
                stats[name]["samples"] += 1

        # ✅ Compute averages and win_rate
        pipelines = []
        for _, v in stats.items():
            if v["samples"] > 0:
                v["avg_final_score"] = round(v["avg_final_score"] / v["samples"], 2)
                v["avg_retrieval_time_sec"] = round(v["avg_retrieval_time_sec"] / v["samples"], 3)
                v["avg_llm_time_sec"] = round(v["avg_llm_time_sec"] / v["samples"], 3)
                v["avg_total_time_sec"] = round(v["avg_total_time_sec"] / v["samples"], 3)
                
            # ✅ Compute win_rate
            v["win_rate"] = round(v["wins"] / total_questions, 3) if total_questions > 0 else 0.0
            
            pipelines.append(v)

        # ✅ Sort by wins first, then by avg_final_score
        pipelines.sort(key=lambda x: (x["wins"], x["avg_final_score"]), reverse=True)
        
        # ✅ Compute best_pipeline_today (last 24h)
        best_pipeline_today = None
        cutoff_today = datetime.now() - relativedelta(days=1)
        
        today_query = sb.table("rag_chat_history") \
            .select("best_pipeline") \
            .eq("collection_id", collection_id) \
            .eq("user_id", user_id) \
            .gte("created_at", cutoff_today.isoformat()) \
            .execute()
        
        today_rows = today_query.data or []
        if today_rows:
            today_stats = {}
            for r in today_rows:
                best = r.get("best_pipeline")
                if best:
                    today_stats[best] = today_stats.get(best, 0) + 1
            
            if today_stats:
                best_pipeline_today = max(today_stats.items(), key=lambda x: x[1])[0]

        return {
            "collection_id": collection_id,
            "mode": mode,
            "range": range_filter,
            "total_questions": total_questions,
            "chat_interactions": chat_count,
            "best_pipeline_today": best_pipeline_today,
            "pipelines": pipelines
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print("❌ LEADERBOARD ERROR:")
        print(traceback.format_exc())
        # Return safe default instead of crashing
        return {
            "collection_id": collection_id,
            "mode": mode or "all",
            "range": range or "30d",
            "total_questions": 0,
            "chat_interactions": 0,
            "best_pipeline_today": None,
            "pipelines": [],
            "error": str(e)
        }


@app.get("/collections/{collection_id}/chunks")
def get_chunks(
    collection_id: str,
    q: Optional[str] = None,
    file_id: Optional[str] = None,
    page: Optional[int] = None,
    pipeline: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user=Depends(get_current_user)
):
    """Fetch chunks for a collection with pagination and filtering."""
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    # Verify ownership
    collection_res = sb.table("rag_collections").select("id").eq("id", collection_id).eq("user_id", user_id).maybe_single().execute()
    if not collection_res.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Build query
    query = sb.table("rag_chunks").select("*", count="exact").eq("collection_id", collection_id)

    if pipeline:
        query = query.eq("pipeline_name", pipeline)
    if file_id:
        query = query.eq("file_id", file_id)
    if page is not None:
        query = query.eq("page_number", page)
    if q:
        query = query.ilike("chunk_text", f"%{q}%")

    # Execute with pagination
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()

    chunks = result.data or []
    total = result.count or 0

    # Fetch file names for chunks
    file_ids = list(set([c.get("file_id") for c in chunks if c.get("file_id")]))
    file_map = {}
    
    if file_ids:
        files_res = sb.table("rag_files").select("id,filename").in_("id", file_ids).execute()
        file_map = {f["id"]: f["filename"] for f in (files_res.data or [])}

    # Format response
    chunk_rows = []
    for c in chunks:
        chunk_rows.append(ChunkRow(
            id=c.get("id"),
            file_id=c.get("file_id"),
            filename=file_map.get(c.get("file_id")),
            pipeline_name=c.get("pipeline_name"),
            chunk_size=c.get("chunk_size"),
            overlap=c.get("overlap"),
            chunk_index=c.get("chunk_index"),
            page_number=c.get("page_number"),
            chunk_text=c.get("chunk_text", ""),
            created_at=c.get("created_at")
        ))

    return ChunkListResponse(
        collection_id=collection_id,
        total=total,
        limit=limit,
        offset=offset,
        chunks=chunk_rows
    )


# -------------------------
# Batch Evaluation
# -------------------------
@app.post("/collections/{collection_id}/batch-eval")
async def batch_eval(
    collection_id: str,
    data: BatchEvalRequest,
    user=Depends(get_current_user)
):
    """Run batch evaluation on a test set of questions."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="SERVICE ROLE KEY missing")
    
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    # Verify ownership
    collection_res = sb.table("rag_collections").select("id").eq("id", collection_id).eq("user_id", user_id).maybe_single().execute()
    if not collection_res.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Verify collection has vector DBs
    if collection_id not in PIPELINE_DB_PATHS:
        raise HTTPException(status_code=400, detail="Collection not indexed. Upload PDFs first.")

    # Create run record
    run_id = str(uuid.uuid4())
    
    # Use Supabase admin for inserting run data
    supabase_admin.table("rag_eval_runs").insert({
        "id": run_id,
        "user_id": user_id,
        "collection_id": collection_id,
        "mode": data.mode,
        "status": "running",
        "total_questions": len(data.items),
        "completed_questions": 0,
        "avg_final_score": 0.0
    }).execute()

    # Process questions asynchronously in background
    async def process_questions():
        total_score = 0.0
        completed = 0
        
        for item in data.items:
            try:
                # Build request similar to /ask endpoint
                ask_req = AskRequest(
                    question=item.question,
                    collection_id=collection_id,
                    mode=data.mode
                )
                
                # Call ask_question logic (synchronous)
                # We need to extract the core logic to avoid dependency issues
                # For now, make a simple internal call
                question = item.question
                mode = data.mode.lower().strip()
                collection_paths = PIPELINE_DB_PATHS[collection_id]
                
                # Check cache
                cached = QA_CACHE.get(collection_id, {}).get(question.lower())
                if cached:
                    result = cached
                else:
                    # Smart fulltext extract
                    full_text = COLLECTION_FULLTEXT.get(collection_id, "")
                    extracted_full = smart_extract_answer(question, full_text)
                    
                    if extracted_full:
                        result = {
                            "final_answer": extracted_full,
                            "best_pipeline": "FULLTEXT_EXTRACT",
                            "metrics": {"final_score": 10.0, "total_ms": 0, "tokens": {"total_tokens": 0}}
                        }
                    else:
                        # Run retrieval for all system pipelines
                        retrieval_results = []
                        for p in SYSTEM_PIPELINES:
                            db_path = collection_paths.get(p["name"])
                            if not db_path:
                                continue
                            
                            vectordb = Chroma(persist_directory=db_path, embedding_function=embeddings)
                            retriever = vectordb.as_retriever(
                                search_type=normalize_search_type(p["search_type"]),
                                search_kwargs={"k": p["k"]}
                            )
                            docs = retriever.invoke(question)
                            merged_docs = dedupe_docs(docs)
                            context = clean_text("\n\n".join([d.page_content for d in merged_docs]))
                            
                            scores = pipeline_score(question=question, context=context, top_k=p["k"], answer="")
                            retrieval_results.append({
                                "pipeline": p["name"],
                                "context": context,
                                "scores": scores
                            })
                        
                        best_retrieval = max(retrieval_results, key=lambda x: x["scores"]["final"])
                        best_context = best_retrieval["context"]
                        
                        # Generate answer
                        base_answer, retry_meta, token_usage = generate_answer_with_retry(question, best_context)
                        final_answer = enrich_answer_if_duration(question, best_context, base_answer)
                        
                        result = {
                            "final_answer": final_answer,
                            "best_pipeline": best_retrieval["pipeline"],
                            "metrics": {
                                "final_score": best_retrieval["scores"]["final"],
                                "total_ms": 0,
                                "tokens": token_usage
                            }
                        }
                
                # Store result
                supabase_admin.table("rag_eval_items").insert({
                    "run_id": run_id,
                    "user_id": user_id,
                    "collection_id": collection_id,
                    "question": item.question,
                    "expected_answer": item.expected_answer,
                    "best_pipeline": result.get("best_pipeline"),
                    "final_answer": result.get("final_answer"),
                    "scores": json.dumps(result.get("metrics", {})),
                    "latency": json.dumps({"total_ms": result.get("metrics", {}).get("total_ms", 0)}),
                    "tokens": json.dumps(result.get("metrics", {}).get("tokens", {}))
                }).execute()
                
                completed += 1
                final_score = result.get("metrics", {}).get("final_score", 0)
                total_score += final_score
                
                # Update run progress
                supabase_admin.table("rag_eval_runs").update({
                    "completed_questions": completed,
                    "avg_final_score": round(total_score / completed, 2)
                }).eq("id", run_id).execute()
                
            except Exception as e:
                print(f"Error processing question: {str(e)}")
                continue
        
        # Mark as done
        supabase_admin.table("rag_eval_runs").update({
            "status": "done"
        }).eq("id", run_id).execute()
    
    # Start background task
    import asyncio
    asyncio.create_task(process_questions())
    
    return {
        "run_id": run_id,
        "status": "running",
        "total_questions": len(data.items)
    }


@app.get("/batch-eval/{run_id}")
def get_batch_eval(run_id: str, user=Depends(get_current_user)):
    """Get batch evaluation run status and results."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="SERVICE ROLE KEY missing")
    
    user_id = user["sub"]
    
    # Get run info
    run_res = supabase_admin.table("rag_eval_runs").select("*").eq("id", run_id).eq("user_id", user_id).maybe_single().execute()
    if not run_res.data:
        raise HTTPException(status_code=404, detail="Run not found")
    
    run_data = run_res.data
    
    # Get items
    items_res = supabase_admin.table("rag_eval_items").select("*").eq("run_id", run_id).order("created_at").execute()
    items = items_res.data or []
    
    # Format items
    formatted_items = []
    for item in items:
        formatted_items.append(BatchEvalItemResult(
            id=item.get("id"),
            question=item.get("question"),
            expected_answer=item.get("expected_answer"),
            best_pipeline=item.get("best_pipeline"),
            final_answer=item.get("final_answer"),
            scores=json.loads(item.get("scores", "{}")),
            latency=json.loads(item.get("latency", "{}")),
            tokens=json.loads(item.get("tokens", "{}")),
            created_at=item.get("created_at")
        ))
    
    return BatchEvalRunResponse(
        run_id=run_id,
        status=run_data.get("status", "running"),
        total_questions=run_data.get("total_questions", 0),
        completed_questions=run_data.get("completed_questions", 0),
        avg_final_score=run_data.get("avg_final_score", 0.0),
        items=formatted_items
    )


# -------------------------
# Ask (FAST / COMPARE)
# -------------------------
@app.post("/ask")
def ask_question(data: AskRequest, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    # -------------------------
    # Validate collection
    # -------------------------
    collection_res = sb.table("rag_collections") \
        .select("id") \
        .eq("id", data.collection_id) \
        .eq("user_id", user_id) \
        .maybe_single() \
        .execute()

    if not collection_res.data:
        raise HTTPException(status_code=400, detail="Collection not found")

    if data.collection_id not in PIPELINE_DB_PATHS:
        raise HTTPException(status_code=400, detail="Index missing locally. Rebuild index.")

    question = data.question.strip()
    mode = (data.mode or "fast").lower().strip()
    collection_paths = PIPELINE_DB_PATHS[data.collection_id]

    # -------------------------
    # Controlled randomization (PER RUN)
    # -------------------------
    run_weights = randomized_weights()
    pipelines_to_use = SYSTEM_PIPELINES.copy()

    if data.custom_pipeline and data.custom_pipeline.enabled:
        pipelines_to_use.append({
            "name": "Custom User Pipeline",
            "chunk_size": data.custom_pipeline.chunk_size,
            "overlap": data.custom_pipeline.overlap,
            "search_type": normalize_search_type(data.custom_pipeline.search_type),
            "k": data.custom_pipeline.top_k,
        })

    random.shuffle(pipelines_to_use)

    # -------------------------
    # Cache (bias-safe key)
    # -------------------------
    cache_key = f"{question.lower()}_{hash(tuple(run_weights.values()))}"
    if mode == "fast":
        cached = QA_CACHE.get(data.collection_id, {}).get(cache_key)
        if cached:
            cached["metrics"]["cache_hit"] = True
            return cached

    # -------------------------
    # Smart full-text extraction
    # -------------------------
    full_text = COLLECTION_FULLTEXT.get(data.collection_id, "")
    extracted_full = smart_extract_answer(question, full_text)
    if extracted_full:
        payload = {
            "question": question,
            "collection_id": data.collection_id,
            "mode": mode,
            "best_pipeline": "FULLTEXT_EXTRACT",
            "final_answer": extracted_full,
            "metrics": {
                "cache_hit": False,
                "smart_extract_used": True,
                "timings_ms": {"total_ms": 0},
                "tokens": None,
                "cost_usd": None
            },
            "retrieval_comparison": [],
            "citations": []
        }

        sb.table("rag_chat_history").insert({
            "user_id": user_id,
            "collection_id": data.collection_id,
            "question": question,
            "answer": extracted_full,
            "mode": mode,
            "best_pipeline": "FULLTEXT_EXTRACT",
            "citations": [],
            "retrieval_comparison": []
        }).execute()

        QA_CACHE.setdefault(data.collection_id, {})[cache_key] = payload
        return payload

    # -------------------------
    # Retrieval + Scoring
    # -------------------------
    t_start_ms = now_ms()
    retrieval_results = []

    build_stats_res = sb.table("rag_pipeline_builds") \
        .select("pipeline_name,chunks_created,build_time_sec") \
        .eq("collection_id", data.collection_id) \
        .eq("user_id", user_id) \
        .execute()

    build_map = {
        r["pipeline_name"]: r for r in (build_stats_res.data or [])
    }

    for p in pipelines_to_use:
        t0 = time.time()

        actual_top_k = jitter_int(p["k"], 2, min_val=1)

        if p["name"] == "Custom User Pipeline":
            db_path = collection_paths.get("Balanced (MMR)") or list(collection_paths.values())[0]
        else:
            db_path = collection_paths.get(p["name"])

            if not db_path:
                # fallback: try normalized key
                for k, v in collection_paths.items():
                    if normalize(k) == normalize(p["name"]):
                        db_path = v
                        break

            if not db_path:
                # final fallback: skip pipeline instead of crashing
                print(f"⚠️ Pipeline DB not found for {p['name']}")
                continue


        vectordb = Chroma(persist_directory=db_path, embedding_function=embeddings)
        retriever = vectordb.as_retriever(
            search_type=normalize_search_type(p["search_type"]),
            search_kwargs={"k": actual_top_k}
        )

        docs = dedupe_docs(retriever.invoke(question))
        context = clean_text("\n\n".join(d.page_content for d in docs))

        scores = pipeline_score(
            question=question,
            context=context,
            top_k=actual_top_k,
            answer="",
            weights=run_weights
        )

        retrieval_results.append({
            "pipeline": p["name"],
            "chunk_size": p["chunk_size"],
            "overlap": p["overlap"],
            "search_type": p["search_type"],
            "top_k": actual_top_k,
            "score_weights": run_weights,
            "retrieval_time_sec": round(time.time() - t0, 3),
            "context_preview": context[:320] + ("..." if len(context) > 320 else ""),
            "sources": [{"source": d.metadata.get("source"), "page": d.metadata.get("page")} for d in docs],
            "scores": scores,
            "chunks_created": build_map.get(p["name"], {}).get("chunks_created"),
            "build_time_sec": build_map.get(p["name"], {}).get("build_time_sec"),
            "context": context
        })

    # -------------------------
    # Winner selection (REAL)
    # -------------------------
    best = max(retrieval_results, key=lambda x: x["scores"]["final"])
    best_context = best["context"]

    extracted = smart_extract_answer(question, best_context)
    if extracted:
        final_answer = extracted
        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    else:
        base_answer, retry_meta, tokens = generate_answer_with_retry(question, best_context)
        final_answer = enrich_answer_if_duration(question, best_context, base_answer)

    best["scores"] = pipeline_score(
        question=question,
        context=best_context,
        top_k=best["top_k"],
        answer=final_answer,
        weights=run_weights
    )

    for r in retrieval_results:
        r.pop("context", None)

    total_ms = now_ms() - t_start_ms
    tokens["model"] = "qwen2.5:3b"
    cost_usd = estimate_cost_usd(tokens, "qwen2.5:3b")

    payload = {
        "question": question,
        "collection_id": data.collection_id,
        "mode": mode,
        "best_pipeline": best["pipeline"],
        "final_answer": final_answer,
        "metrics": {
            "cache_hit": False,
            "timings_ms": {"total_ms": total_ms},
            "tokens": tokens,
            "cost_usd": cost_usd
        },
        "retrieval_comparison": retrieval_results,
        "citations": best["sources"][:5]
    }

    sb.table("rag_chat_history").insert({
        "user_id": user_id,
        "collection_id": data.collection_id,
        "question": question,
        "answer": final_answer,
        "mode": mode,
        "best_pipeline": best["pipeline"],
        "citations": payload["citations"],
        "retrieval_comparison": retrieval_results
    }).execute()

    QA_CACHE.setdefault(data.collection_id, {})[cache_key] = payload
    return payload


# -------------------------
# Chat Mode
# -------------------------
@app.get("/collections/{collection_id}/chat")
def get_chat(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    res = sb.table("rag_chat_messages") \
        .select("role,message,created_at") \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=False) \
        .limit(50) \
        .execute()

    return {"messages": res.data or []}


@app.delete("/collections/{collection_id}/chat")
def clear_chat(collection_id: str, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    sb.table("rag_chat_messages") \
        .delete() \
        .eq("collection_id", collection_id) \
        .eq("user_id", user_id) \
        .execute()

    return {"status": "cleared ✅"}


@app.post("/chat-stream")
def chat_stream(data: ChatRequest, user=Depends(get_current_user)):
    access_token = user["access_token"]
    user_id = user["sub"]
    sb = get_supabase_user_client(access_token)

    # Store user message
    sb.table("rag_chat_messages").insert({
        "user_id": user_id,
        "collection_id": data.collection_id,
        "role": "user",
        "message": data.question
    }).execute()

    async def gen():
        try:
            # Get recent chat history for context
            history_res = sb.table("rag_chat_messages") \
                .select("role,message") \
                .eq("collection_id", data.collection_id) \
                .eq("user_id", user_id) \
                .order("created_at", desc=False) \
                .limit(10) \
                .execute()
            
            chat_history = history_res.data or []
            
            # Build context from chat history
            context_messages = []
            for msg in chat_history[-6:]:  # Last 6 messages for context
                context_messages.append(f"{msg['role'].capitalize()}: {msg['message']}")
            
            conversation_context = "\n".join(context_messages)

            # Get the collection's best performing pipeline from history
            best_pipeline_res = sb.table("rag_chat_history") \
                .select("best_pipeline,retrieval_comparison") \
                .eq("collection_id", data.collection_id) \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(5) \
                .execute()
            
            # Determine best pipeline based on recent performance
            pipeline_scores = {}
            for record in (best_pipeline_res.data or []):
                best = record.get("best_pipeline")
                if best and best != "FULLTEXT_EXTRACT":
                    pipeline_scores[best] = pipeline_scores.get(best, 0) + 1
                    
                # Also count from retrieval comparison
                comparison = record.get("retrieval_comparison") or []
                if comparison:
                    top_pipeline = max(comparison, key=lambda x: x.get("scores", {}).get("final", 0))
                    top_name = top_pipeline.get("pipeline")
                    if top_name:
                        pipeline_scores[top_name] = pipeline_scores.get(top_name, 0) + 0.5

            preferred_pipeline = max(pipeline_scores.items(), key=lambda x: x[1])[0] if pipeline_scores else "Pipeline A"

            # Check if collection exists in pipeline paths
            if data.collection_id not in PIPELINE_DB_PATHS:
                yield "❌ Collection not found. Please upload documents first."
                return

            collection_paths = PIPELINE_DB_PATHS[data.collection_id]
            
            # Try smart extraction first
            full_text = COLLECTION_FULLTEXT.get(data.collection_id, "")
            extracted = smart_extract_answer(data.question, full_text)
            
            if extracted:
                response = f"📋 Direct Answer: {extracted}"
                
                # Stream the response
                for char in response:
                    yield char
                    await asyncio.sleep(0.005)
                    
            else:
                # Use the preferred/best performing pipeline
                pipeline_info = next((p for p in PIPELINES if p["name"] == preferred_pipeline), PIPELINES[0])
                persist_dir = collection_paths.get(pipeline_info["name"])
                
                if not persist_dir or not os.path.exists(persist_dir):
                    yield f"❌ Pipeline {pipeline_info['name']} not available."
                    return

                # Load vector database
                vectordb = Chroma(
                    persist_directory=persist_dir,
                    embedding_function=embeddings
                )

                # Build enhanced query with conversation context
                if len(chat_history) > 1:
                    enhanced_query = f"""
Previous conversation context:
{conversation_context}

Current question: {data.question}

Please answer the current question considering the conversation context.
"""
                else:
                    enhanced_query = data.question

                # Retrieve relevant documents
                if pipeline_info["search_type"] == "mmr":
                    docs = vectordb.max_marginal_relevance_search(enhanced_query, k=pipeline_info["k"])
                else:
                    docs = vectordb.similarity_search(enhanced_query, k=pipeline_info["k"])

                docs = dedupe_docs(docs)
                context = clean_text("\n\n".join([d.page_content for d in docs]))

                # Create conversational prompt
                conv_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant having a conversation with a user about their documents.

Previous conversation context:
{conversation_context}

Relevant document context:
{document_context}

Current question: {current_question}

Instructions:
- Answer the current question using the document context
- Consider the conversation history to provide a coherent response
- If referencing previous parts of the conversation, be natural about it
- Keep responses conversational but informative
- If you can't answer from the documents, say so

Answer:
""")

                # Generate response
                chain = conv_prompt | llm
                
                response = str(chain.invoke({
                    "conversation_context": conversation_context if len(chat_history) > 1 else "This is the start of our conversation.",
                    "document_context": context,
                    "current_question": data.question
                })).strip()

                # Enhance with duration logic if applicable
                response = enrich_answer_if_duration(data.question, context, response)

                # Stream the response
                for char in response:
                    yield char
                    await asyncio.sleep(0.005)

            # Store assistant response
            sb.table("rag_chat_messages").insert({
                "user_id": user_id,
                "collection_id": data.collection_id,
                "role": "assistant",
                "message": response if 'response' in locals() else extracted
            }).execute()

        except Exception as e:
            error_msg = f"❌ Chat error: {str(e)}"
            yield error_msg
            
            # Store error as assistant message
            sb.table("rag_chat_messages").insert({
                "user_id": user_id,
                "collection_id": data.collection_id,
                "role": "assistant",
                "message": error_msg
            }).execute()

    return StreamingResponse(gen(), media_type="text/plain")


# -------------------------
# Image Test Mode (RAG Vision Accuracy)
# -------------------------
@app.post("/image-test")
async def image_test(
    image: UploadFile = File(...),
    question: str = Form(...),
    collection_id: Optional[str] = Form(None),
    user=Depends(get_current_user)
):
    """
    ✅ Test RAG vision accuracy by uploading an image and asking a question.
    
    Returns:
    - image_signed_url: URL for frontend preview
    - extracted_description: What the vision model saw
    - final_answer: Answer to the user's question
    - confidence_score: 0-10 confidence rating
    - metrics: latency and token usage
    """
    import traceback
    
    try:
        # Validate inputs
        if not question or not question.strip():
            raise HTTPException(status_code=400, detail="Question is required")
        
        if not image:
            raise HTTPException(status_code=400, detail="Image is required")
        
        if image.content_type and image.content_type not in ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {image.content_type}")
        
        access_token = user["access_token"]
        user_id = user["sub"]
        sb = get_supabase_user_client(access_token)
        
        start_total = time.perf_counter()
        
        # ✅ Step 1: Save image locally AND try Supabase Storage
        image_bytes = await image.read()
        
        # Local save as fallback
        os.makedirs("uploads/images", exist_ok=True)
        timestamp = int(time.time() * 1000)
        file_ext = os.path.splitext(image.filename)[1] if image.filename else ".jpg"
        if not file_ext:
            file_ext = ".jpg"
        local_path = f"uploads/images/{user_id}_{timestamp}{file_ext}"
        
        try:
            with open(local_path, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            print(f"⚠️ Local save failed: {e}")
        
        # Try Supabase Storage upload
        image_signed_url = None
        if supabase_admin:
            try:
                storage_path = f"{user_id}/{collection_id or 'standalone'}/{timestamp}_{uuid.uuid4().hex[:8]}{file_ext}"
                
                # Try to upload
                try:
                    supabase_admin.storage.from_("rag-images").upload(
                        storage_path,
                        image_bytes,
                        {"content-type": image.content_type or "image/jpeg"}
                    )
                except Exception as upload_err:
                    # Bucket might not exist, try creating it
                    if "not found" in str(upload_err).lower() or "does not exist" in str(upload_err).lower():
                        try:
                            supabase_admin.storage.create_bucket("rag-images", {"public": False})
                            supabase_admin.storage.from_("rag-images").upload(
                                storage_path,
                                image_bytes,
                                {"content-type": image.content_type or "image/jpeg"}
                            )
                        except Exception as create_err:
                            print(f"⚠️ Bucket creation failed: {create_err}")
                
                # Generate signed URL
                signed_url_res = supabase_admin.storage.from_("rag-images").create_signed_url(
                    storage_path,
                    60 * 60  # 1 hour
                )
                
                if isinstance(signed_url_res, dict):
                    image_signed_url = signed_url_res.get("signedURL") or signed_url_res.get("signedUrl", "")
                else:
                    image_signed_url = getattr(signed_url_res, "signed_url", "") or getattr(signed_url_res, "signedURL", "")
                    
            except Exception as storage_err:
                print(f"⚠️ Supabase Storage failed: {storage_err}")
        
        # Fallback to local path if Supabase failed
        if not image_signed_url:
            image_signed_url = f"local://{local_path}"
        
        # ✅ Step 2: Vision description (try llava, fallback to placeholder)
        start_vision = time.perf_counter()
        extracted_description = None
        
        try:
            # Try using Ollama llava model for vision
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            import requests
            llava_response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava",
                    "prompt": "Describe this image in precise, factual detail. Do not guess missing details. Focus on what you can clearly see.",
                    "images": [image_b64],
                    "stream": False
                },
                timeout=30
            )
            
            if llava_response.status_code == 200:
                extracted_description = llava_response.json().get("response", "")
        except Exception as vision_err:
            print(f"⚠️ Vision model failed: {vision_err}")
        
        # Fallback description
        if not extracted_description or not extracted_description.strip():
            extracted_description = f"[Vision model unavailable] Image uploaded successfully. File: {image.filename or 'unknown'}. To enable vision analysis, install Ollama llava model: 'ollama pull llava'"
        
        vision_ms = int((time.perf_counter() - start_vision) * 1000)
        
        # ✅ Step 3: Answer question using description
        start_llm = time.perf_counter()
        
        try:
            # Use existing LLM to answer
            llm_start = time.time()
            answer_text, retry_meta, token_usage = generate_answer_with_retry(question, extracted_description)
            llm_time = time.time() - llm_start
            
            final_answer = answer_text
            
        except Exception as llm_err:
            print(f"⚠️ LLM failed: {llm_err}")
            final_answer = f"[LLM unavailable] Question received: '{question}'. Description: {extracted_description}"
            token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model": "qwen2.5:3b"}
        
        llm_ms = int((time.perf_counter() - start_llm) * 1000)
        
        # ✅ Step 4: Confidence score
        try:
            uncertainty_markers = ["unavailable", "unsure", "cannot", "don't know", "unclear", "maybe", "possibly", "error"]
            has_uncertainty = any(marker in final_answer.lower() for marker in uncertainty_markers)
            
            if "[Vision model unavailable]" in extracted_description or "[LLM unavailable]" in final_answer:
                confidence_score = 3.0
            elif has_uncertainty:
                confidence_score = 5.0
            elif len(final_answer.strip()) < 20:
                confidence_score = 6.0
            else:
                confidence_score = 8.0
        except Exception:
            confidence_score = 5.0
        
        total_ms = int((time.perf_counter() - start_total) * 1000)
        
        # ✅ Step 5: Build metrics
        metrics = {
            "latency": {
                "vision_ms": vision_ms,
                "llm_ms": llm_ms,
                "total_ms": total_ms
            },
            "tokens": {
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens": token_usage.get("total_tokens", 0),
                "estimated_cost_usd": estimate_cost_usd(token_usage, model=token_usage.get("model", "qwen2.5:3b")),
                "model": token_usage.get("model", "qwen2.5:3b")
            }
        }
        
        # ✅ Optional: Store in Supabase (graceful fail)
        try:
            sb.table("rag_image_tests").insert({
                "user_id": user_id,
                "collection_id": collection_id,
                "image_path": local_path,
                "image_signed_url": image_signed_url,
                "question": question,
                "extracted_description": extracted_description,
                "final_answer": final_answer,
                "confidence_score": confidence_score,
                "metrics": metrics
            }).execute()
        except Exception as db_err:
            print(f"⚠️ Database save failed: {db_err}")
        
        return {
            "ok": True,
            "image_signed_url": image_signed_url,
            "question": question,
            "extracted_description": extracted_description,
            "final_answer": final_answer,
            "confidence_score": round(confidence_score, 1),
            "metrics": metrics
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print("❌ IMAGE TEST ERROR:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Image test failed: {str(e)}")
