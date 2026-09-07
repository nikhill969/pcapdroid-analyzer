"""Dashboard API endpoints."""

from fastapi import APIRouter, Query
from app.database import get_connection
from app.services.analytics import get_dashboard_stats, get_timeline_data

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
def dashboard_stats():
    """Get dashboard overview statistics."""
    conn = get_connection()
    try:
        return get_dashboard_stats(conn)
    finally:
        conn.close()


@router.get("/timeline")
def timeline(
    interval: str = Query("hour", regex="^(hour|day)$"),
    app: str = "",
    domain: str = "",
):
    """Get timeline data for charting."""
    conn = get_connection()
    try:
        data = get_timeline_data(conn, interval, app, domain)
        return {"interval": interval, "data": data}
    finally:
        conn.close()
