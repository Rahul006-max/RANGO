"""
Model management routes - endpoints for per-user model selection and CRUD.
"""
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from services import model_service


class AddModelRequest(BaseModel):
    model_name: str
    provider: str
    api_url: str
    api_key: str
    temperature: Optional[float] = 0.5


class TestConnectivityRequest(BaseModel):
    provider: str
    api_url: str
    api_key: str


class SetActiveModelRequest(BaseModel):
    model_id: str


class UpdateModelRequest(BaseModel):
    model_name: str
    provider: str
    api_url: str
    api_key: str
    temperature: Optional[float] = 0.5


router = APIRouter()


@router.get("/models")
def list_user_models(user=Depends(get_current_user)):
    """
    List all models available to the user:
    - System default model (always available)
    - User's custom models
    """
    result = model_service.get_user_models(user["sub"], user["access_token"])
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.post("/models")
def add_custom_model(
    request: AddModelRequest,
    user=Depends(get_current_user),
):
    """
    Add a new custom model for the user.
    - Validates connectivity with test API call
    - Stores in rag_user_models table
    """
    result = model_service.add_user_model(
        user_id=user["sub"],
        model_name=request.model_name,
        provider=request.provider,
        api_url=request.api_url,
        api_key=request.api_key,
        temperature=request.temperature or 0.5,
        access_token=user["access_token"],
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.post("/models/test")
def test_model_connectivity(
    request: TestConnectivityRequest,
    user=Depends(get_current_user),
):
    """
    Test connectivity to a model API endpoint.
    - Validates that credentials and endpoint are reachable
    - Does not create a model, just tests the connection
    """
    result = model_service.test_model_connectivity(
        provider=request.provider,
        api_url=request.api_url,
        api_key=request.api_key,
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.get("/models/active")
def get_active_model(user=Depends(get_current_user)):
    """
    Get the user's currently active model.
    - Returns system default if not set
    - Falls back to system default if active model is invalid/deleted
    """
    result = model_service.get_active_model(user["sub"], user["access_token"])
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.put("/models/active")
def set_active_model(
    request: SetActiveModelRequest,
    user=Depends(get_current_user),
):
    """
    Set the user's active model.
    - Validates ownership (must be user's model or system default)
    - Updates rag_user_settings.active_model_id
    """
    result = model_service.set_active_model(
        user_id=user["sub"],
        model_id=request.model_id,
        access_token=user["access_token"],
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.put("/models/{model_id}")
def update_custom_model(
    model_id: str,
    request: UpdateModelRequest,
    user=Depends(get_current_user),
):
    """
    Update a user's custom model.
    - Validates connectivity with test API call
    - Updates rag_user_models entry
    - Cannot update system default
    """
    result = model_service.update_user_model(
        user_id=user["sub"],
        model_id=model_id,
        model_name=request.model_name,
        provider=request.provider,
        api_url=request.api_url,
        api_key=request.api_key,
        temperature=request.temperature or 0.5,
        access_token=user["access_token"],
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result


@router.delete("/models/{model_id}")
def delete_custom_model(
    model_id: str,
    user=Depends(get_current_user),
):
    """
    Delete a user's custom model.
    - Cannot delete system default
    - Validates ownership
    - Resets to system default if was active
    """
    result = model_service.delete_user_model(
        user_id=user["sub"],
        model_id=model_id,
        access_token=user["access_token"],
    )
    
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
    return result
