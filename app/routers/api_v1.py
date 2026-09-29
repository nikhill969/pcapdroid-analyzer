"""v1 API namespace for PCAPdroid Analyzer."""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from app.database import get_connection
from app.services.analytics import get_dashboard_stats, store_records, track_import, refresh_all_stats
from app.services.csv_parser import parse_csv_file

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@router.get("/health")
def health():
    """Health check for the centralized v1 API namespace."""
    return {"status": "ok", "namespace": "v1"}


@router.get("/dashboard/stats")
def dashboard_stats():
    """Overview statistics for the dashboard (v1)."""
    conn = get_connection()
    try:
        return get_dashboard_stats(conn)
    finally:
        conn.close()


@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...)):
    """Import a PCAPdroid CSV file (v1)."""
    content = await file.read()

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    if len(content) > 500 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")

    result = parse_csv_file(content, filename=file.filename)

    if result["valid_rows"] == 0 and result["total_rows"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No valid rows found. Malformed: {result['malformed_rows']}, Errors: {len(result['errors'])}"
        )

    conn = get_connection()
    try:
        first_packet = min((r["first_seen"] for r in result["rows"] if r["first_seen"]), default=None)
        last_packet = max((r["last_seen"] for r in result["rows"] if r["last_seen"]), default=None)
        total_traffic = sum(r["bytes_sent"] + r["bytes_received"] for r in result["rows"])

        import_id = track_import(conn, file.filename, result["total_rows"], len(content),
                                 first_packet, last_packet, total_traffic)

        stored = store_records(conn, result["rows"], import_id)

        refresh_all_stats(conn)
    finally:
        conn.close()

    return {
        "filename": file.filename,
        "import_id": import_id,
        "total_rows": result["total_rows"],
        "valid_rows": stored,
        "duplicate_rows": result["duplicate_rows"],
        "malformed_rows": result["malformed_rows"],
        "errors": result["errors"][:10],
    }


@router.get("/apps/list")
def list_apps(
    sort_by: str = Query("total_bytes", regex="^(total_bytes|bytes_sent|bytes_received|connections|destinations)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List all apps with their statistics (v1)."""
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
