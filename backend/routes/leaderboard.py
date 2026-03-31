"""
Leaderboard routes - endpoints for pipeline performance statistics.
"""
from fastapi import APIRouter, Depends

from dependencies import get_current_user
from services import leaderboard_service


router = APIRouter()


@router.get("/leaderboard/global")
def get_global_leaderboard(
    mode: str = "all",
    range: str = "30d",
    user=Depends(get_current_user)
):
    """
    Global leaderboard across ALL collections for the authenticated user.
    
    Query params:
    - mode: all|fast|compare|chat (default: all)
    - range: 7d|30d|all (default: 30d)
    """
    return leaderboard_service.get_global_leaderboard(
        user_id=user["sub"],
        access_token=user["access_token"],
        mode=mode,
        range_filter=range
    )


@router.get("/collections/{collection_id}/leaderboard")
def get_leaderboard(
    collection_id: str,
    mode: str = "all",
    range: str = "30d",
    user=Depends(get_current_user)
):
    """
    Get leaderboard with mode and time range filters.
    
    Query params:
    - mode: all|fast|compare|chat (default: all)
    - range: 7d|30d|all (default: 30d)
    """
    return leaderboard_service.get_leaderboard(
        collection_id=collection_id,
        user_id=user["sub"],
        access_token=user["access_token"],
        mode=mode,
        range_filter=range
    )
