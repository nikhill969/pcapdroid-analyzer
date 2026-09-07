"""Privacy metrics API endpoints."""

from fastapi import APIRouter
from app.database import get_connection
from app.services.analytics import get_privacy_metrics

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.get("/metrics")
def privacy_metrics():
    """Get privacy-relevant metrics."""
    conn = get_connection()
    try:
        return get_privacy_metrics(conn)
    finally:
        conn.close()
