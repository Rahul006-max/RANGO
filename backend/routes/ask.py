"""
Ask routes - endpoints for fast/compare mode question answering.
"""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from models import AskRequest
from services import ask_service, model_service


router = APIRouter()


@router.post("/ask")
def ask_question(data: AskRequest, user=Depends(get_current_user)):
    """Answer a question using fast or compare mode."""
    # Resolve the model to use
    model_to_use = data.model_name
    if not model_to_use:
        # No model specified in request — fetch user's active model
        active_model_info = model_service.get_active_model(user["sub"], user["access_token"])
        model_to_use = active_model_info.get("id")
    
    # Get full model details including credentials for LLM calls
    model_info = model_service.get_model_for_routing(user["sub"], user["access_token"]) if model_to_use else None
    
    result = ask_service.ask_question(
        data=data,
        user_id=user["sub"],
        access_token=user["access_token"],
        model_name=model_info.get("model_name") if model_info else None,
        api_key=model_info.get("api_key") if model_info else None,
        temperature=model_info.get("temperature") if model_info else None,
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    
    return result
