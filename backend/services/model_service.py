"""
Model service - handles per-user model selection, CRUD of custom models, and model routing.
"""
from typing import Optional, Dict, Any, List
from groq import Groq
import uuid

from config import get_settings
from dependencies import get_supabase_user_client, get_supabase_admin


settings = get_settings()
SYSTEM_MODEL_ID = "system_default"


class ModelNotFoundError(Exception):
    """Raised when a model cannot be found or accessed."""
    pass


class ModelValidationError(Exception):
    """Raised when model validation fails."""
    pass


def get_user_models(user_id: str, access_token: str) -> Dict[str, Any]:
    """
    List all models available to the user:
    - System default model (always available)
    - User's custom models from rag_user_models table
    """
    try:
        sb = get_supabase_user_client(access_token)
        
        # Fetch user's custom models
        custom_models_res = sb.table("rag_user_models") \
            .select("id,model_name,provider,api_url,temperature,created_at") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()
        
        custom_models = custom_models_res.data or []
        
        # Format system default model
        system_model = {
            "id": SYSTEM_MODEL_ID,
            "model_name": settings.groq_model,
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1",
            "temperature": 0.5,
            "is_system": True,
            "is_custom": False,
            "created_at": None,
        }
        
        # Format custom models
        formatted_custom = [format_model_response(m) for m in custom_models]
        
        all_models = [system_model] + formatted_custom
        
        return {
            "models": all_models,
            "user_id": user_id,
        }
    except Exception as e:
        return {"error": str(e), "status_code": 500}


def add_user_model(
    user_id: str,
    model_name: str,
    provider: str,
    api_url: str,
    api_key: str,
    temperature: float = 0.5,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add a new custom model for the user.
    - Validates connectivity with a test API call
    - Stores model in rag_user_models table
    """
    if not model_name or not model_name.strip():
        return {"error": "model_name cannot be empty", "status_code": 400}
    
    if provider.lower() not in ["groq", "openai"]:
        return {"error": "provider must be 'groq' or 'openai'", "status_code": 400}
    
    if temperature < 0 or temperature > 2:
        return {"error": "temperature must be between 0 and 2", "status_code": 400}
    
    # Validate connectivity
    validation_result = validate_model_connectivity(
        model_name=model_name,
        provider=provider,
        api_url=api_url,
        api_key=api_key,
    )
    
    if "error" in validation_result:
        return validation_result
    
    try:
        model_id = str(uuid.uuid4())
        sb = get_supabase_user_client(access_token)
        
        model_data = {
            "id": model_id,
            "user_id": user_id,
            "model_name": model_name.strip(),
            "provider": provider.lower(),
            "api_url": api_url.strip(),
            "api_key": api_key.strip(),
            "temperature": temperature,
        }
        
        sb.table("rag_user_models").insert(model_data).execute()
        
        return {
            "model_id": model_id,
            "model_name": model_name,
            "provider": provider,
            "status": "created",
        }
    except Exception as e:
        return {"error": f"Failed to save model: {str(e)}", "status_code": 500}


def get_active_model(user_id: str, access_token: str) -> Dict[str, Any]:
    """
    Resolve the user's active model:
    1. Check rag_user_settings.active_model_id
    2. If present and valid, return that model's full details
    3. If not set or invalid, return system default
    """
    try:
        sb = get_supabase_user_client(access_token)
        
        # Check user settings for active model
        settings_res = sb.table("rag_user_settings") \
            .select("active_model_id") \
            .eq("user_id", user_id) \
            .execute()
        
        active_model_id = None
        if settings_res.data:
            active_model_id = settings_res.data[0].get("active_model_id")
        
        # If no active model set, return system default
        if not active_model_id or active_model_id == SYSTEM_MODEL_ID:
            return {
                "id": SYSTEM_MODEL_ID,
                "model_name": settings.groq_model,
                "provider": "groq",
                "api_url": "https://api.groq.com/openai/v1",
                "temperature": 0.5,
                "is_system": True,
            }
        
        # Try to fetch the user's custom model
        model_res = sb.table("rag_user_models") \
            .select("id,model_name,provider,api_url,temperature") \
            .eq("id", active_model_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if model_res.data:
            return format_model_response(model_res.data[0])
        
        # If model not found, fall back to system default
        return {
            "id": SYSTEM_MODEL_ID,
            "model_name": settings.groq_model,
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1",
            "temperature": 0.5,
            "is_system": True,
        }
    except Exception as e:
        # Safety fallback: return system default on error
        return {
            "id": SYSTEM_MODEL_ID,
            "model_name": settings.groq_model,
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1",
            "temperature": 0.5,
            "is_system": True,
            "warning": f"Error resolving active model, using system default: {str(e)}",
        }


def set_active_model(user_id: str, model_id: str, access_token: str) -> Dict[str, Any]:
    """
    Set the user's active model.
    - Validates that the model belongs to the user (or is system default)
    - Updates rag_user_settings.active_model_id
    """
    # Validate that model exists and belongs to user
    if model_id != SYSTEM_MODEL_ID:
        try:
            sb = get_supabase_user_client(access_token)
            model_res = sb.table("rag_user_models") \
                .select("id") \
                .eq("id", model_id) \
                .eq("user_id", user_id) \
                .execute()
            
            if not model_res.data:
                return {
                    "error": f"Model {model_id} not found or does not belong to user",
                    "status_code": 404,
                }
        except Exception as e:
            return {"error": f"Failed to validate model: {str(e)}", "status_code": 500}
    
    try:
        sb = get_supabase_user_client(access_token)
        
        # Check if settings row exists
        settings_res = sb.table("rag_user_settings") \
            .select("user_id") \
            .eq("user_id", user_id) \
            .execute()
        
        if not settings_res.data:
            # Create new settings row
            sb.table("rag_user_settings").insert({
                "user_id": user_id,
                "active_model_id": model_id,
            }).execute()
        else:
            # Update existing settings row
            sb.table("rag_user_settings").update({
                "active_model_id": model_id,
            }).eq("user_id", user_id).execute()
        
        return {
            "status": "active model set",
            "model_id": model_id,
            "user_id": user_id,
        }
    except Exception as e:
        return {"error": f"Failed to set active model: {str(e)}", "status_code": 500}


def delete_user_model(user_id: str, model_id: str, access_token: str) -> Dict[str, Any]:
    """
    Delete a user's custom model.
    - Validates ownership
    - If model was active, reset to system default
    - Permission check: only user who created the model can delete it
    """
    if model_id == SYSTEM_MODEL_ID:
        return {"error": "Cannot delete system default model", "status_code": 403}
    
    try:
        sb = get_supabase_user_client(access_token)
        
        # Verify model belongs to user
        model_res = sb.table("rag_user_models") \
            .select("id,user_id") \
            .eq("id", model_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if not model_res.data:
            return {"error": "Model not found or does not belong to user", "status_code": 404}
        
        # Delete the model
        sb.table("rag_user_models").delete().eq("id", model_id).eq("user_id", user_id).execute()
        
        # If this was the active model, reset to system default
        settings_res = sb.table("rag_user_settings") \
            .select("active_model_id") \
            .eq("user_id", user_id) \
            .execute()
        
        if settings_res.data and settings_res.data[0].get("active_model_id") == model_id:
            sb.table("rag_user_settings").update({
                "active_model_id": SYSTEM_MODEL_ID,
            }).eq("user_id", user_id).execute()
        
        return {"status": "deleted", "model_id": model_id}
    except Exception as e:
        return {"error": f"Failed to delete model: {str(e)}", "status_code": 500}


def update_user_model(
    user_id: str,
    model_id: str,
    model_name: str,
    provider: str,
    api_url: str,
    api_key: str,
    temperature: float = 0.5,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update an existing custom model for the user.
    - Validates ownership
    - Validates connectivity with updated credentials
    - Updates rag_user_models entry
    - Cannot update system default model
    """
    if model_id == SYSTEM_MODEL_ID:
        return {"error": "Cannot update system default model", "status_code": 403}
    
    if not model_name or not model_name.strip():
        return {"error": "model_name cannot be empty", "status_code": 400}
    
    if temperature < 0 or temperature > 2:
        return {"error": "temperature must be between 0 and 2", "status_code": 400}
    
    try:
        sb = get_supabase_user_client(access_token)
        
        # Verify model belongs to user
        model_res = sb.table("rag_user_models") \
            .select("id,user_id") \
            .eq("id", model_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if not model_res.data:
            return {"error": "Model not found or does not belong to user", "status_code": 404}
        
        # Validate connectivity with new credentials
        validation_result = validate_model_connectivity(
            model_name=model_name,
            provider=provider,
            api_url=api_url,
            api_key=api_key,
        )
        
        if "error" in validation_result:
            return validation_result
        
        # Update the model
        model_data = {
            "model_name": model_name.strip(),
            "provider": provider.lower(),
            "api_url": api_url.strip(),
            "api_key": api_key.strip(),
            "temperature": temperature,
        }
        
        sb.table("rag_user_models").update(model_data).eq("id", model_id).eq("user_id", user_id).execute()
        
        return {
            "model_id": model_id,
            "model_name": model_name,
            "provider": provider,
            "status": "updated",
        }
    except Exception as e:
        return {"error": f"Failed to update model: {str(e)}", "status_code": 500}


def validate_model_connectivity(
    model_name: str,
    provider: str,
    api_url: str,
    api_key: str,
) -> Dict[str, Any]:
    """Test basic API connectivity without requiring model to exist."""
    import requests
    provider = provider.lower()
    if provider == "groq":
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=5)
            return {"status": "connected", "model_name": model_name} if response.status_code == 200 else {"error": f"Groq API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to Groq: {str(e)}", "status_code": 400}
    elif provider == "openai":
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=5)
            return {"status": "connected", "model_name": model_name} if response.status_code == 200 else {"error": f"OpenAI API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to OpenAI: {str(e)}", "status_code": 400}
    elif provider == "anthropic":
        try:
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            data = {"model": "claude-3-sonnet-20240229", "max_tokens": 10, "messages": [{"role": "user", "content": "test"}]}
            response = requests.post(f"{api_url.rstrip('/')}/messages", headers=headers, json=data, timeout=5)
            return {"status": "connected", "model_name": model_name} if response.status_code in [200, 201] else {"error": f"Anthropic API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to Anthropic: {str(e)}", "status_code": 400}
    return {"error": f"Provider {provider} not supported", "status_code": 400}


def format_model_response(model_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a model object for API response (exclude sensitive api_key).
    """
    return {
        "id": model_obj.get("id"),
        "model_name": model_obj.get("model_name"),
        "provider": model_obj.get("provider"),
        "api_url": model_obj.get("api_url"),
        "temperature": model_obj.get("temperature", 0.5),
        "created_at": model_obj.get("created_at"),
        "is_custom": True,
    }


def get_model_for_routing(user_id: str, access_token: str) -> Dict[str, Any]:
    """
    Get the model to use for LLM calls (used by ask/chat/batch/etc services).
    Returns model with credentials (api_key included for actual API calls).
    """
    try:
        sb = get_supabase_user_client(access_token)
        
        # Get active model ID
        settings_res = sb.table("rag_user_settings") \
            .select("active_model_id") \
            .eq("user_id", user_id) \
            .execute()
        
        active_model_id = None
        if settings_res.data:
            active_model_id = settings_res.data[0].get("active_model_id")
        
        # If system default or not set, return system model
        if not active_model_id or active_model_id == SYSTEM_MODEL_ID:
            return {
                "id": SYSTEM_MODEL_ID,
                "model_name": settings.groq_model,
                "provider": "groq",
                "api_url": "https://api.groq.com/openai/v1",
                "api_key": settings.groq_api_key,
                "temperature": 0.5,
                "is_system": True,
            }
        
        # Fetch custom model with credentials
        model_res = sb.table("rag_user_models") \
            .select("id,model_name,provider,api_url,api_key,temperature") \
            .eq("id", active_model_id) \
            .eq("user_id", user_id) \
            .execute()
        
        if model_res.data:
            return {
                "id": model_res.data[0].get("id"),
                "model_name": model_res.data[0].get("model_name"),
                "provider": model_res.data[0].get("provider"),
                "api_url": model_res.data[0].get("api_url"),
                "api_key": model_res.data[0].get("api_key"),
                "temperature": model_res.data[0].get("temperature", 0.5),
            }
        
        # Fallback to system default if not found
        return {
            "id": SYSTEM_MODEL_ID,
            "model_name": settings.groq_model,
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1",
            "api_key": settings.groq_api_key,
            "temperature": 0.5,
            "is_system": True,
        }
    except Exception as e:
        # Safety fallback: always return system default on error
        return {
            "id": SYSTEM_MODEL_ID,
            "model_name": settings.groq_model,
            "provider": "groq",
            "api_url": "https://api.groq.com/openai/v1",
            "api_key": settings.groq_api_key,
            "temperature": 0.5,
            "is_system": True,
        }


def test_model_connectivity(
    provider: str,
    api_url: str,
    api_key: str,
) -> Dict[str, Any]:
    """Test connectivity to a model API endpoint."""
    import requests
    provider = provider.lower()
    if provider == "groq":
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=5)
            return {"status": "connected", "provider": provider} if response.status_code == 200 else {"error": f"Groq API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to Groq: {str(e)}", "status_code": 400}
    elif provider == "openai":
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=5)
            return {"status": "connected", "provider": provider} if response.status_code == 200 else {"error": f"OpenAI API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to OpenAI: {str(e)}", "status_code": 400}
    elif provider == "anthropic":
        try:
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            data = {"model": "claude-3-sonnet-20240229", "max_tokens": 10, "messages": [{"role": "user", "content": "test"}]}
            response = requests.post(f"{api_url.rstrip('/')}/messages", headers=headers, json=data, timeout=5)
            return {"status": "connected", "provider": provider} if response.status_code in [200, 201] else {"error": f"Anthropic API error: {response.status_code}", "status_code": 400}
        except Exception as e:
            return {"error": f"Failed to connect to Anthropic: {str(e)}", "status_code": 400}
    return {"error": f"Provider {provider} not supported", "status_code": 400}
