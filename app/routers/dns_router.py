"""DNS analysis API endpoints."""

from fastapi import APIRouter, Query
from app.database import get_connection
from app.services.analytics import get_dns_analysis

router = APIRouter(prefix="/api/dns", tags=["dns"])


@router.get("/analysis")
def dns_analysis(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Get DNS analysis results."""
    conn = get_connection()
    try:
        result = get_dns_analysis(conn, page, per_page)
        return result
    finally:
        conn.close()
