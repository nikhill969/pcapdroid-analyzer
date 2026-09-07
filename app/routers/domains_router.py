"""Domain analysis API endpoints."""

from fastapi import APIRouter, Query
from app.database import get_connection
from app.services.analytics import get_domain_details, refresh_all_stats

router = APIRouter(prefix="/api/domains", tags=["domains"])


@router.get("/list")
def list_domains(
    sort_by: str = Query("connections", regex="^(connections|total_bytes|bytes_sent|bytes_received)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    search: str = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List all domains with their statistics."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        sort_map = {
            "connections": "connection_count",
            "total_bytes": "total_bytes_sent + total_bytes_received",
            "bytes_sent": "total_bytes_sent",
            "bytes_received": "total_bytes_received",
        }
        sort_col = sort_map.get(sort_by, "connection_count")
        order_dir = "DESC" if order == "desc" else "ASC"

        where = ""
        params = []
        if search:
            where = "WHERE domain LIKE ?"
            params.append(f"%{search}%")

        offset = (page - 1) * per_page

        query = f"""
            SELECT * FROM domain_stats
            {where}
            ORDER BY {sort_col} {order_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        cursor.execute(query, params)
        domains = [dict(row) for row in cursor.fetchall()]

        # Total count
        count_query = f"SELECT COUNT(*) as cnt FROM domain_stats {where}"
        cursor.execute(count_query, params[:-2] if params else [])
        total = cursor.fetchone()["cnt"]

        return {
            "domains": domains,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }
    finally:
        conn.close()


@router.get("/details")
def domain_details(domain: str = Query(..., description="Domain name")):
    """Get detailed statistics for a specific domain."""
    conn = get_connection()
    try:
        result = get_domain_details(conn, domain)
        if "error" in result:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    finally:
        conn.close()


@router.post("/refresh")
def refresh_domain_stats():
    """Refresh domain statistics from raw data."""
    conn = get_connection()
    try:
        from app.services.analytics import refresh_all_stats
        refresh_all_stats(conn)
        return {"status": "ok", "message": "Statistics refreshed"}
    finally:
        conn.close()
