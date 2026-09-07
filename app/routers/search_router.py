"""Search and filter API endpoints."""

from fastapi import APIRouter, Query
from app.database import get_connection
from app.services.analytics import search_connections, get_timeline_data

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/connections")
def search(
    q: str = Query("", description="Global search query"),
    app: str = Query("", description="Filter by app name"),
    domain: str = Query("", description="Filter by domain"),
    protocol: str = Query("", description="Filter by protocol"),
    start_date: str = Query("", description="Start date (ISO format)"),
    end_date: str = Query("", description="End date (ISO format)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Search and filter connections."""
    conn = get_connection()
    try:
        result = search_connections(conn, q, app, domain, protocol, start_date, end_date, page, per_page)
        return result
    finally:
        conn.close()


@router.get("/timeline")
def search_timeline(
    interval: str = Query("hour", regex="^(hour|day)$"),
    app: str = "",
    domain: str = "",
):
    """Get timeline data with filters applied."""
    conn = get_connection()
    try:
        data = get_timeline_data(conn, interval, app, domain)
        return {"interval": interval, "data": data}
    finally:
        conn.close()
