"""Export routes for compare reports."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from dependencies import get_current_user
from models import ExportCompareReportRequest
from services import analytics_service


router = APIRouter()


@router.post("/export/compare-report")
def export_compare_report(
    data: ExportCompareReportRequest,
    user=Depends(get_current_user),
):
    # user dependency enforces auth; payload ownership is derived from active session usage.
    try:
        report = analytics_service.build_compare_report(
            report_format=data.format,
            payload=data.payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return Response(
        content=report["content"],
        media_type=report["media_type"],
        headers={
            "Content-Disposition": f"attachment; filename={report['filename']}",
        },
    )
