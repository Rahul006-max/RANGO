"""Pydantic models used across the backend."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CustomPipelineConfig(BaseModel):
    enabled: bool = False
    preset_name: str = "Custom"
    chunk_size: int = 800
    overlap: int = 120
    top_k: int = 6
    search_type: str = "mmr"


class AskRequest(BaseModel):
    question: str
    collection_id: str
    mode: str = "fast"
    custom_pipeline: Optional[CustomPipelineConfig] = None
    model_name: Optional[str] = None  # User's active model (None = system default)


class RenameRequest(BaseModel):
    name: str


class ChatRequest(BaseModel):
    question: str
    collection_id: str
    model_name: Optional[str] = None  # User's active model (None = system default)


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
    model_name: Optional[str] = None  # User's active model (None = system default)


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
    latency_stats: Optional[dict] = None
    items: List[BatchEvalItemResult]


class ApplyPresetRequest(BaseModel):
    preset_key: str


class ExportCompareReportRequest(BaseModel):
    format: str = "json"
    payload: Dict[str, Any] = Field(default_factory=dict)
