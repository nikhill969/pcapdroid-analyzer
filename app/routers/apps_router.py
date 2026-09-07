"""App analysis API endpoints."""

from fastapi import APIRouter, Query
from app.database import get_connection
from app.services.analytics import get_app_details

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.get("/list")
def list_apps(
    sort_by: str = Query("total_bytes", regex="^(total_bytes|bytes_sent|bytes_received|connections|destinations)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List all apps with their statistics."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        sort_map = {
            "total_bytes": "total_bytes_sent + total_bytes_received",
            "bytes_sent": "total_bytes_sent",
            "bytes_received": "total_bytes_received",
            "connections": "total_connections",
            "destinations": "unique_destinations",
        }
        sort_col = sort_map.get(sort_by, "total_bytes_sent + total_bytes_received")
        order_dir = "DESC" if order == "desc" else "ASC"

        offset = (page - 1) * per_page

        cursor.execute(f"""
            SELECT * FROM app_stats
            ORDER BY {sort_col} {order_dir}
            LIMIT ? OFFSET ?
        """, (per_page, offset))

        apps = [dict(row) for row in cursor.fetchall()]

        # Total count
        cursor.execute("SELECT COUNT(*) as cnt FROM app_stats")
        total = cursor.fetchone()["cnt"]

        return {
            "apps": apps,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "sort_by": sort_by,
            "order": order,
        }
    finally:
        conn.close()


@router.get("/details")
def app_details(
    app: str = Query(..., description="App name to get details for"),
    package: str = Query("", description="Package name filter (optional)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Get detailed statistics for a specific app."""
    conn = get_connection()
    try:
        result = get_app_details(conn, app, package, page, per_page)
        if "error" in result:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    finally:
        conn.close()
