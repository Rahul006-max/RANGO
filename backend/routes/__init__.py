"""
Routes package - API endpoints for RAG Pipeline Optimizer.
"""
from . import analytics, collections, upload, ask, chat, leaderboard, batch_eval, image_test, export, page_index

__all__ = [
	"analytics",
	"collections",
	"upload",
	"ask",
	"chat",
	"leaderboard",
	"batch_eval",
	"image_test",
	"export",
	"page_index",
]
