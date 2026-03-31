"""Analytics routes for cost trends and retrieval visualization."""

from fastapi import APIRouter, Depends

from dependencies import get_current_user
from services import analytics_service


router = APIRouter()


@router.get("/analytics/costs")
def get_costs(
    collection_id: str | None = None,
    days: int = 30,
    user=Depends(get_current_user),
):
    return analytics_service.get_cost_analytics(
        user_id=user["sub"],
        access_token=user["access_token"],
        collection_id=collection_id,
        days=days,
    )


@router.get("/collections/{collection_id}/retrieval-logs")
def get_retrieval_logs(
    collection_id: str,
    limit: int = 20,
    user=Depends(get_current_user),
):
    return analytics_service.get_retrieval_logs(
        user_id=user["sub"],
        access_token=user["access_token"],
        collection_id=collection_id,
        limit=limit,
    )
