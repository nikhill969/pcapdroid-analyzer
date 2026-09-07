"""Recording session management and data retention endpoints."""

import os
import shutil
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from app.database import get_connection, DB_PATH

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
def list_sessions():
    """List all recording sessions (imports) with packet-time metadata."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, filename, row_count, imported_at, file_size_bytes,
                   first_packet, last_packet, total_traffic_bytes,
                   (SELECT COUNT(*) FROM connections c WHERE c.import_id = imports.id) AS stored_rows
            FROM imports
            ORDER BY COALESCE(first_packet, imported_at) DESC
        """).fetchall()
        sessions = [dict(r) for r in rows]
        return {"sessions": sessions, "count": len(sessions)}
    finally:
        conn.close()


@router.delete("/{import_id}")
def delete_session(import_id: int):
    """Delete one recording session and all of its raw connection rows."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, filename FROM imports WHERE id = ?", (import_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Recording session {import_id} not found")
        conn.execute("DELETE FROM connections WHERE import_id = ?", (import_id,))
        conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))
        conn.commit()
        # Refresh materialized aggregates so they reflect the remaining data
        from app.services.analytics import refresh_all_stats
        refresh_all_stats(conn)
        return {"deleted": import_id, "filename": row["filename"]}
    finally:
        conn.close()


@router.delete("")
def delete_all_data(confirm: str = Query(..., description="Must be the literal string 'DELETE ALL'")):
    """Delete ALL imported data (raw connections and recording sessions)."""
    if confirm != "DELETE ALL":
        raise HTTPException(status_code=400, detail="Pass confirm='DELETE ALL' to wipe all data")
    conn = get_connection()
    try:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM imports")
        conn.commit()
        from app.services.analytics import refresh_all_stats
        refresh_all_stats(conn)
        return {"deleted": "all"}
    finally:
        conn.close()


@router.get("/export/database")
def export_database():
    """Export the raw SQLite database file (RAW DATA)."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    # Copy to a temp snapshot so WAL contents are included
    snapshot = str(DB_PATH) + ".export"
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(snapshot)
    src.backup(dst)
    dst.close()
    src.close()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(snapshot, media_type="application/octet-stream",
                        filename=f"pcap_analyzer_{ts}.db")


@router.get("/export/analysis")
def export_analysis(night: str = None):
    """
    Export derived aggregates as JSON (DERIVED DATA).

    With no night parameter, exports per-night summaries for all nights.
    """
    from app.services import overnight
    import json

    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        if night:
            d = datetime.strptime(night, "%Y-%m-%d").date()
            payload = {
                "type": "DERIVED AGGREGATES",
                "night": night,
                "config": cfg,
                "summary": overnight.night_summary(conn, d, cfg["sleep_start"], cfg["sleep_end"]),
                "apps": overnight.night_apps(conn, d, cfg["sleep_start"], cfg["sleep_end"], per_page=200),
            }
        else:
            nights = overnight.enumerate_nights(conn, 365, cfg["sleep_start"], cfg["sleep_end"])
            summaries = []
            for n in nights:
                if n["connection_count"] > 0:
                    d = datetime.strptime(n["night"], "%Y-%m-%d").date()
                    summaries.append(overnight.night_summary(conn, d, cfg["sleep_start"], cfg["sleep_end"]))
            payload = {
                "type": "DERIVED AGGREGATES",
                "config": cfg,
                "nights": summaries,
            }
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"overnight_analysis_{ts}.json"
        return PlainTextResponse(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()
