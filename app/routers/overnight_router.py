"""Overnight analysis API endpoints."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.services import overnight

router = APIRouter(prefix="/api/overnight", tags=["overnight"])


def _parse_hhmm(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be HH:MM (24h), got '{value}'")
    return value


def _parse_night(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid night date '{value}', expected YYYY-MM-DD")


@router.get("/config")
def get_config():
    """Get the current sleep window configuration."""
    conn = get_connection()
    try:
        return overnight.get_sleep_config(conn)
    finally:
        conn.close()


@router.post("/config")
def set_config(sleep_start: str = Query(...), sleep_end: str = Query(...)):
    """Set the sleep window (24h HH:MM). The window may span midnight."""
    _parse_hhmm(sleep_start, "sleep_start")
    _parse_hhmm(sleep_end, "sleep_end")
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sleep_start', ?)", (sleep_start,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sleep_end', ?)", (sleep_end,))
        conn.commit()
    finally:
        conn.close()
    return {"sleep_start": sleep_start, "sleep_end": sleep_end}


@router.get("/nights")
def list_nights(days: int = Query(7, ge=1, le=365)):
    """Enumerate the last N nights and whether overnight data exists for each."""
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        nights = overnight.enumerate_nights(conn, days, cfg["sleep_start"], cfg["sleep_end"])
        return {"config": cfg, "days": days, "nights": nights}
    finally:
        conn.close()


@router.get("/night/{night}")
def night_detail(night: str, days_context: int = Query(7, ge=1, le=365)):
    """Full overnight picture for one night: summary, apps, bursts, insights."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        start, end = cfg["sleep_start"], cfg["sleep_end"]
        summary = overnight.night_summary(conn, d, start, end)
        apps = overnight.night_apps(conn, d, start, end, page=1, per_page=200)
        bursts = overnight.detect_bursts(conn, d, start, end)
        insights = overnight.privacy_insights(conn, d, start, end)

        # Baseline status per app (needs >= 3 prior nights; computed from all data)
        baselines = {}
        for app in apps["apps"][:20]:
            nights_hist = overnight._app_night_traffic(conn, app["app_name"], app["package_name"], start, end)
            baselines[app["app_name"]] = _summarize_baseline(nights_hist, d)

        return {
            "config": cfg,
            "summary": summary,
            "apps": apps,
            "bursts": bursts,
            "insights": insights,
            "baselines": baselines,
        }
    finally:
        conn.close()


def _summarize_baseline(nights_hist: list, current_night: date) -> dict:
    """Baseline status of one app for a specific night, based on other nights."""
    values = [n["total_traffic"] for n in nights_hist if n["night"] != current_night.strftime("%Y-%m-%d")]
    last = next((n["total_traffic"] for n in nights_hist if n["night"] == current_night.strftime("%Y-%m-%d")), 0)
    if len(values) < 2:
        return {"baseline_available": False, "last_night": last,
                "status": "Not enough data"}
    mean = sum(values) / len(values)
    stddev = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    if stddev > 0 and last > mean + 2 * stddev:
        status = "Higher than baseline"
    elif stddev > 0 and last < mean - 2 * stddev:
        status = "Lower than baseline"
    else:
        status = "Normal"
    return {
        "baseline_available": True,
        "nights_observed": len(values),
        "mean": round(mean),
        "stddev": round(stddev),
        "typical_range": {"low": min(values), "high": max(values)},
        "last_night": last,
        "status": status,
    }


@router.get("/night/{night}/timeline")
def night_timeline(night: str, bucket_minutes: int = Query(15, ge=1, le=60), import_id: int = None):
    """Overnight timeline in fixed time buckets (traffic / connections / active apps)."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        timeline = overnight.night_timeline(conn, d, cfg["sleep_start"], cfg["sleep_end"],
                                            bucket_minutes, import_id)
        return {"night": night, "bucket_minutes": bucket_minutes, "buckets": timeline}
    finally:
        conn.close()


@router.get("/night/{night}/apps")
def night_apps(night: str, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
               sort: str = Query("traffic"), import_id: int = None):
    """Per-app overnight breakdown for one night."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        return overnight.night_apps(conn, d, cfg["sleep_start"], cfg["sleep_end"],
                                    page, per_page, sort, import_id)
    finally:
        conn.close()


@router.get("/night/{night}/apps/{app_name}/destinations")
def app_destinations(night: str, app_name: str, import_id: int = None):
    """Destinations contacted by one app overnight."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        return {"night": night, "app_name": app_name,
                "destinations": overnight.night_app_destinations(conn, d, cfg["sleep_start"], cfg["sleep_end"],
                                                                 app_name, import_id)}
    finally:
        conn.close()


@router.get("/night/{night}/apps/{app_name}/connections")
def app_connections(night: str, app_name: str, page: int = Query(1, ge=1),
                    per_page: int = Query(50, ge=1, le=200), destination: str = None,
                    import_id: int = None):
    """Drill-down: raw connections behind an overnight app aggregate."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        return overnight.app_overnight_connections(conn, d, cfg["sleep_start"], cfg["sleep_end"],
                                                   app_name, page, per_page, import_id, destination)
    finally:
        conn.close()


@router.get("/night/{night}/bursts")
def night_bursts(night: str, bucket_minutes: int = Query(5, ge=1, le=30),
                 threshold_sigma: float = Query(3.0, ge=1.0, le=10.0), import_id: int = None):
    """Per-app activity bursts for one night (statistical, neutral labels)."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        bursts = overnight.detect_bursts(conn, d, cfg["sleep_start"], cfg["sleep_end"],
                                         bucket_minutes, threshold_sigma, import_id)
        return {"night": night, "bucket_minutes": bucket_minutes, "threshold_sigma": threshold_sigma,
                "note": "A burst is a volume observation, not a judgment about the app.",
                "bursts": bursts}
    finally:
        conn.close()


@router.get("/compare")
def compare_nights(nights: str = Query(..., description="Comma-separated YYYY-MM-DD night dates")):
    """Multi-night comparison with averages and % difference vs average."""
    night_list = [n.strip() for n in nights.split(",") if n.strip()]
    if not night_list:
        raise HTTPException(status_code=400, detail="Provide at least one night, e.g. ?nights=2026-09-06,2026-09-07")
    for n in night_list:
        _parse_night(n)
    conn = get_connection()
    try:
        return overnight.multi_night_comparison(conn, night_list)
    finally:
        conn.close()


@router.get("/baseline/{app_name}")
def app_baseline(app_name: str, package_name: str = None):
    """Statistical overnight baseline for one app across all nights."""
    conn = get_connection()
    try:
        return overnight.baseline_stats(conn, app_name, package_name)
    finally:
        conn.close()


@router.get("/insights/{night}")
def night_insights(night: str):
    """F factual privacy observations for one night."""
    d = _parse_night(night)
    conn = get_connection()
    try:
        cfg = overnight.get_sleep_config(conn)
        return {"night": night, "insights": overnight.privacy_insights(conn, d, cfg["sleep_start"], cfg["sleep_end"])}
    finally:
        conn.close()
