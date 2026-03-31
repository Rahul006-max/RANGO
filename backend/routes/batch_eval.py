"""
Batch evaluation routes.
POST /collections/{id}/batch-eval  — processes all questions and returns full results inline.
"""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from models import BatchEvalRequest, BatchEvalRunResponse
from services import batch_eval_service, model_service


router = APIRouter()


@router.post("/collections/{collection_id}/batch-eval")
async def batch_eval(
    collection_id: str,
    data: BatchEvalRequest,
    user=Depends(get_current_user),
):
    """Run batch evaluation synchronously and return full results in one response."""
    # Resolve the model to use
    model_to_use = data.model_name
    if not model_to_use:
        # No model specified in request — fetch user's active model
        active_model_info = model_service.get_active_model(user["sub"], user["access_token"])
        model_to_use = active_model_info.get("id")
    
    # Get full model details including credentials for LLM calls
    model_info = model_service.get_model_for_routing(user["sub"], user["access_token"]) if model_to_use else None
    
    result = await batch_eval_service.create_batch_eval_run(
        collection_id=collection_id,
        user_id=user["sub"],
        access_token=user["access_token"],
        data=data,
        model_name=model_info.get("model_name") if model_info else None,
        api_key=model_info.get("api_key") if model_info else None,
        temperature=model_info.get("temperature") if model_info else None,
    )

    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])

    return BatchEvalRunResponse(
        run_id=result["run_id"],
        status=result["status"],
        total_questions=result["total_questions"],
        completed_questions=result["completed_questions"],
        avg_final_score=result["avg_final_score"],
        latency_stats=result.get("latency_stats"),
        items=result["items"],
    )
