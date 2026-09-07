"""CSV import API endpoint."""

import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.database import get_connection
from app.services.csv_parser import parse_csv_file
from app.services.analytics import store_records, track_import, refresh_all_stats

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/csv")
async def import_csv(file: UploadFile = File(...)):
    """Import a PCAPdroid CSV file."""
    # Read file content
    content = await file.read()

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    # Check file size (limit to 500MB)
    if len(content) > 500 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")

    # Parse CSV
    result = parse_csv_file(content, filename=file.filename)

    if result["valid_rows"] == 0 and result["total_rows"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No valid rows found. Malformed: {result['malformed_rows']}, Errors: {len(result['errors'])}"
        )

    # Store in database
    conn = get_connection()
    try:
        # Compute session metadata from parsed rows
        first_packet = min((r["first_seen"] for r in result["rows"] if r["first_seen"]), default=None)
        last_packet = max((r["last_seen"] for r in result["rows"] if r["last_seen"]), default=None)
        total_traffic = sum(r["bytes_sent"] + r["bytes_received"] for r in result["rows"])

        # Track import
        import_id = track_import(conn, file.filename, result["total_rows"], len(content),
                                 first_packet, last_packet, total_traffic)

        # Store records
        stored = store_records(conn, result["rows"], import_id)

        # Refresh aggregates
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
        "errors": result["errors"][:10],  # Limit error messages in response
    }


@router.get("/status")
def get_import_status():
    """Get import status and database info."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Total records
        cursor.execute("SELECT COUNT(*) as cnt FROM connections")
        total_records = cursor.fetchone()["cnt"]

        # Import history
        cursor.execute("""
            SELECT id, filename, row_count, imported_at, file_size_bytes
            FROM imports
            ORDER BY imported_at DESC
            LIMIT 50
        """)
        imports = [dict(row) for row in cursor.fetchall()]

        # Database size
        db_path = os.environ.get("PCAP_DB_DIR", "data")
        db_file = os.path.join(db_path, "pcap_analyzer.db")
        db_size = os.path.getsize(db_file) if os.path.exists(db_file) else 0

        return {
            "total_records": total_records,
            "import_count": len(imports),
            "database_size_bytes": db_size,
            "imports": imports,
        }
    finally:
        conn.close()
