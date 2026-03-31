"""
Chat routes - endpoints for conversational chat mode.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dependencies import get_current_user
from models import ChatRequest
from services import chat_service, model_service


router = APIRouter()


@router.get("/collections/{collection_id}/chat")
def get_chat(collection_id: str, user=Depends(get_current_user)):
    """Get chat history for a collection."""
    return chat_service.get_chat_history(
        collection_id, user["sub"], user["access_token"]
    )


@router.delete("/collections/{collection_id}/chat")
def clear_chat(collection_id: str, user=Depends(get_current_user)):
    """Clear chat history for a collection."""
    return chat_service.clear_chat_history(
        collection_id, user["sub"], user["access_token"]
    )


@router.post("/chat-stream")
async def chat_stream(data: ChatRequest, user=Depends(get_current_user)):
    """Stream chat responses."""
    # Resolve the model to use
    model_to_use = data.model_name
    if not model_to_use:
        # No model specified in request — fetch user's active model
        active_model_info = model_service.get_active_model(user["sub"], user["access_token"])
        model_to_use = active_model_info.get("id")
    
    # Get full model details including credentials for LLM calls
    model_info = model_service.get_model_for_routing(user["sub"], user["access_token"]) if model_to_use else None
    
    async def gen():
        try:
            async for chunk in chat_service.chat_stream_generator(
                data=data,
                user_id=user["sub"],
                access_token=user["access_token"],
                model_name=model_info.get("model_name") if model_info else None,
                api_key=model_info.get("api_key") if model_info else None,
                temperature=model_info.get("temperature") if model_info else None,
            ):
                yield chunk
        except Exception as exc:
            # Yield a clean error token so the chunked response closes properly
            # instead of letting uvicorn drop the connection mid-stream
            yield f"\n\n[Stream error: {exc}]"

    return StreamingResponse(
        gen(),
        media_type="text/plain",
        headers={"X-Accel-Buffering": "no"},  # disable proxy buffering
    )
