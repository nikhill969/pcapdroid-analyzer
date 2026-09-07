"""Overnight traffic analysis engine.

All overnight figures are derived by SQL aggregation over the raw
connections table (no dataset is loaded into memory). An "overnight
period" is a user-configured window (default 23:00-07:00) that may span
midnight. Terminology is deliberately neutral: "overnight traffic" is
not evidence that the device was idle, and deviations from baseline are
not evidence of anything malicious.
"""

import sqlite3
from datetime import date, datetime, timedelta

from app.database import get_setting


DEFAULT_SLEEP_START = "23:00"
DEFAULT_SLEEP_END = "07:00"


def get_sleep_config(conn: sqlite3.Connection) -> dict:
    """Read sleep window settings with defaults."""
    row = conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('sleep_start', 'sleep_end')"
    ).fetchall()
    values = {r["key"]: r["value"] for r in row}
    return {
        "sleep_start": values.get("sleep_start", DEFAULT_SLEEP_START),
        "sleep_end": values.get("sleep_end", DEFAULT_SLEEP_END),
    }


def _validate_hhmm(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except (ValueError, TypeError):
        return False


def _window_bounds(night_date: date, sleep_start: str, sleep_end: str) -> tuple:
    """(start_dt, end_dt) of the overnight window for one night."""
    start_dt = datetime.combine(night_date, datetime.strptime(sleep_start, "%H:%M").time())
    if datetime.strptime(sleep_end, "%H:%M").time() <= datetime.strptime(sleep_start, "%H:%M").time():
        end_date = night_date + timedelta(days=1)
    else:
        end_date = night_date
    end_dt = datetime.combine(end_date, datetime.strptime(sleep_end, "%H:%M").time())
    return start_dt, end_dt


def _sql_str(value: str) -> str:
    """Escape a value into a safe SQL string literal (internal use only)."""
    return "'" + value.replace("'", "''") + "'"


def _overnight_where(night_date: date, sleep_start: str, sleep_end: str) -> tuple:
    """
    Build WHERE clause for the overnight window of a given night.

    The window runs from sleep_start on night_date to sleep_end on the
    next day. If sleep_end > sleep_start (no midnight crossing) the
    window stays within night_date.
    """
    start_dt, end_dt = _window_bounds(night_date, sleep_start, sleep_end)
    start_s = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_s = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    return f"first_seen >= '{start_s}' AND first_seen < '{end_s}'", []


def enumerate_nights(conn: sqlite3.Connection, days: int, sleep_start: str, sleep_end: str) -> list[dict]:
    """List candidate nights, with a flag for whether data exists."""
    start_str, params = _overnight_where(date.today() - timedelta(days=days), sleep_start, sleep_end)
    end_str, end_params = _overnight_where(date.today(), sleep_start, sleep_end)
    cursor = conn.execute(
        f"""
        SELECT MIN(first_seen) AS first_data, MAX(first_seen) AS last_data
        FROM connections
        WHERE ({start_str}) OR ({end_str})
        """,
        list(params) + list(end_params),
    )
    row = cursor.fetchone()
    if not row or not row["first_data"]:
        return []
    first_data = datetime.strptime(row["first_data"][:10], "%Y-%m-%d").date()
    last_data = datetime.strptime(row["last_data"][:10], "%Y-%m-%d").date()
    # Earliest possible first night = day before first data (window may start late on that day)
    cursor = conn.execute("SELECT MIN(date(first_seen)) AS d FROM connections")
    first_day = cursor.fetchone()["d"]
    if first_day:
        first_day = datetime.strptime(first_day, "%Y-%m-%d").date() - timedelta(days=1)
    else:
        first_day = first_data

    nights = []
    night = last_data
    while night >= first_day:
        start_dt = datetime.combine(night, datetime.strptime(sleep_start, "%H:%M").time())
        if datetime.strptime(sleep_end, "%H:%M").time() <= datetime.strptime(sleep_start, "%H:%M").time():
            end_night = night + timedelta(days=1)
        else:
            end_night = night
        end_dt = datetime.combine(end_night, datetime.strptime(sleep_end, "%H:%M").time())
        s = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        e = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM connections WHERE first_seen >= ? AND first_seen < ?",
            (s, e),
        ).fetchone()["c"]
        nights.append({
            "night": night.strftime("%Y-%m-%d"),
            "window_start": s,
            "window_end": e,
            "connection_count": cnt,
        })
        if len(nights) >= days:
            break
        night -= timedelta(days=1)
    return nights


def night_summary(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str) -> dict:
    """Compute the overnight summary for one night entirely in SQL."""
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    start_dt, end_dt = _window_bounds(night_date, sleep_start, sleep_end)

    cursor = conn.execute(f"""
        SELECT
            COALESCE(SUM(bytes_sent), 0)      AS bytes_sent,
            COALESCE(SUM(bytes_received), 0)  AS bytes_received,
            COUNT(*)                          AS connections,
            COUNT(DISTINCT app_name)          AS unique_apps,
            COUNT(DISTINCT dst_ip)            AS unique_destinations,
            COUNT(DISTINCT domain)            AS unique_domains,
            SUM(is_dns)                       AS dns_requests,
            MIN(first_seen)                   AS first_activity,
            MAX(last_seen)                    AS last_activity
        FROM connections
        WHERE {where}
    """, params)
    row = cursor.fetchone()

    cursor = conn.execute(f"""
        SELECT COUNT(DISTINCT substr(first_seen, 1, 13) || '-' || printf('%02d', CAST(substr(first_seen, 15, 2) AS INTEGER)))
        FROM connections WHERE {where}
    """, params)
    active_hours = cursor.fetchone()[0]

    return {
        "night": night_date.strftime("%Y-%m-%d"),
        "window_start": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "window_end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "bytes_sent": row["bytes_sent"],
        "bytes_received": row["bytes_received"],
        "total_traffic": row["bytes_sent"] + row["bytes_received"],
        "connections": row["connections"],
        "unique_apps": row["unique_apps"],
        "unique_destinations": row["unique_destinations"],
        "unique_domains": row["unique_domains"],
        "dns_requests": row["dns_requests"] or 0,
        "active_periods": active_hours,
        "first_activity": row["first_activity"],
        "last_activity": row["last_activity"],
    }


def night_apps(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str,
               page: int = 1, per_page: int = 50, sort: str = "traffic",
               import_id: int = None) -> dict:
    """Per-app overnight breakdown for one night (paginated)."""
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    if import_id is not None:
        where += f" AND import_id = {int(import_id)}"

    sort_cols = {
        "traffic": "total_traffic DESC",
        "connections": "connections DESC",
        "sent": "bytes_sent DESC",
        "received": "bytes_received DESC",
        "app": "app_name ASC",
    }
    order = sort_cols.get(sort, "total_traffic DESC")

    total = conn.execute(f"""
        SELECT COUNT(*) AS c FROM (
            SELECT app_name FROM connections WHERE {where} GROUP BY app_name, package_name
        )
    """, params).fetchone()["c"]

    cursor = conn.execute(f"""
        SELECT
            app_name,
            package_name,
            SUM(bytes_sent)                  AS bytes_sent,
            SUM(bytes_received)              AS bytes_received,
            SUM(bytes_sent + bytes_received) AS total_traffic,
            COUNT(*)                         AS connections,
            COUNT(DISTINCT domain)           AS unique_domains,
            MIN(first_seen)                  AS first_activity,
            MAX(last_seen)                   AS last_activity
        FROM connections
        WHERE {where}
        GROUP BY app_name, package_name
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page])
    apps = [dict(r) for r in cursor.fetchall()]

    return {"total": total, "page": page, "per_page": per_page, "apps": apps}


def night_timeline(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str,
                   bucket_minutes: int = 15, import_id: int = None) -> list[dict]:
    """
    Timeline of overnight activity in fixed buckets.

    Buckets are computed in SQL from first_seen so no rows are loaded
    into the client; only the aggregates (one per bucket) are returned.
    """
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    if import_id is not None:
        where += " AND import_id = ?"
        params = params + [import_id]

    start_dt, end_dt = _window_bounds(night_date, sleep_start, sleep_end)
    bucket_seconds = bucket_minutes * 60
    total_buckets = int((end_dt - start_dt).total_seconds() // bucket_seconds) + 1

    # Bucket index relative to window start, computed with epoch seconds.
    cursor = conn.execute(f"""
        WITH b AS (
            SELECT
                (CAST(strftime('%s', first_seen) AS INTEGER) - CAST(strftime('%s', ?) AS INTEGER))
                    / {bucket_seconds} AS bucket_idx,
                bytes_sent + bytes_received AS traffic,
                app_name
            FROM connections
            WHERE {where}
        )
        SELECT
            bucket_idx,
            SUM(traffic)                       AS traffic,
            COUNT(*)                           AS connections,
            COUNT(DISTINCT app_name)           AS active_apps
        FROM b
        GROUP BY bucket_idx
        ORDER BY bucket_idx
    """, [start_dt.strftime("%Y-%m-%dT%H:%M:%S")])
    rows = cursor.fetchall()

    timeline = []
    for r in rows:
        idx = r["bucket_idx"]
        bucket_start = start_dt + timedelta(seconds=idx * bucket_seconds)
        timeline.append({
            "bucket_start": bucket_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "traffic": r["traffic"],
            "connections": r["connections"],
            "active_apps": r["active_apps"],
        })

    # Fill gaps with zero buckets so idle periods are visible
    filled = []
    by_idx = {int((datetime.strptime(t["bucket_start"], "%Y-%m-%dT%H:%M:%S") - start_dt).total_seconds() // bucket_seconds): t for t in timeline}
    for i in range(total_buckets):
        t = by_idx.get(i)
        if t:
            filled.append(t)
        else:
            gap_start = start_dt + timedelta(seconds=i * bucket_seconds)
            filled.append({
                "bucket_start": gap_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "traffic": 0,
                "connections": 0,
                "active_apps": 0,
            })
    return filled


def night_app_destinations(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str,
                           app_name: str, import_id: int = None) -> list[dict]:
    """Destinations (domain or IP) contacted by one app overnight."""
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    if import_id is not None:
        where += f" AND import_id = {int(import_id)}"

    cursor = conn.execute(f"""
        SELECT
            COALESCE(domain, dst_ip)     AS destination,
            COUNT(*)                     AS connections,
            SUM(bytes_sent)              AS sent,
            SUM(bytes_received)          AS received,
            SUM(bytes_sent + bytes_received) AS total_traffic,
            MIN(first_seen)              AS first_seen,
            MAX(last_seen)               AS last_seen
        FROM connections
        WHERE {where} AND app_name = {_sql_str(app_name)}
        GROUP BY destination
        ORDER BY total_traffic DESC
    """)
    return [dict(r) for r in cursor.fetchall()]


def detect_bursts(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str,
                  bucket_minutes: int = 5, threshold: float = 3.0, import_id: int = None) -> list[dict]:
    """
    Detect per-app activity bursts in overnight traffic.

    For each app, compute its per-bucket traffic statistics across the
    night in SQL, then flag buckets whose traffic exceeds
    mean + threshold * stddev. Labels are neutral: a burst is an
    observation about volume, not a judgment about intent.
    """
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    if import_id is not None:
        where += f" AND import_id = {int(import_id)}"

    start_dt, _ = _window_bounds(night_date, sleep_start, sleep_end)
    bucket_seconds = bucket_minutes * 60

    cursor = conn.execute(f"""
        WITH b AS (
            SELECT
                app_name,
                (CAST(strftime('%s', first_seen) AS INTEGER) - CAST(strftime('%s', {_sql_str(start_dt.strftime("%Y-%m-%dT%H:%M:%S"))}) AS INTEGER))
                    / {bucket_seconds} AS bucket_idx,
                SUM(bytes_sent + bytes_received) AS traffic
            FROM connections
            WHERE {where}
            GROUP BY app_name, bucket_idx
        ),
        stats AS (
            SELECT
                app_name,
                COUNT(*)          AS n,
                AVG(traffic)      AS mean,
                -- sqrt of mean of squared deviations (population stddev)
                CASE WHEN COUNT(*) > 1
                     THEN sqrt(SUM((traffic - sub.mean) * (traffic - sub.mean)) / COUNT(*))
                     ELSE 0 END AS stddev
            FROM b
            JOIN (
                SELECT app_name AS a2, AVG(traffic) AS mean
                FROM b GROUP BY app_name
            ) sub ON sub.a2 = b.app_name
            GROUP BY app_name
        )
        SELECT
            b.app_name,
            b.bucket_idx,
            b.traffic,
            s.mean,
            s.stddev,
            s.n AS buckets
        FROM b
        JOIN stats s ON s.app_name = b.app_name
        WHERE b.traffic > s.mean + {threshold} * s.stddev
          AND s.n >= 3
        ORDER BY b.traffic DESC
    """)

    bursts = []
    for r in cursor.fetchall():
        app_name_for_bursts = r["app_name"]
        bucket_start = start_dt + timedelta(seconds=r["bucket_idx"] * bucket_seconds)
        bucket_end = bucket_start + timedelta(seconds=bucket_seconds)
        b_start_s = bucket_start.strftime("%Y-%m-%dT%H:%M:%S")
        b_end_s = bucket_end.strftime("%Y-%m-%dT%H:%M:%S")
        conn_count = conn.execute(
            f"SELECT COUNT(*) AS c FROM connections WHERE {where} "
            f"AND app_name = {_sql_str(app_name_for_bursts)} "
            f"AND first_seen >= {_sql_str(b_start_s)} AND first_seen < {_sql_str(b_end_s)}",
        ).fetchone()["c"]
        pkts = conn.execute(
            f"SELECT COALESCE(SUM(pkts_sent + pkts_received), 0) AS p FROM connections "
            f"WHERE {where} AND app_name = {_sql_str(app_name_for_bursts)} "
            f"AND first_seen >= {_sql_str(b_start_s)} AND first_seen < {_sql_str(b_end_s)}",
        ).fetchone()["p"]
        ratio = (r["traffic"] / r["mean"]) if r["mean"] else None
        bursts.append({
            "app_name": r["app_name"],
            "start": bucket_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": bucket_end.strftime("%Y-%m-%dT%H:%M:%S"),
            "traffic": r["traffic"],
            "packets": pkts,
            "connections": conn_count,
            "app_mean_bucket_traffic": round(r["mean"], 1),
            "app_stddev_bucket_traffic": round(r["stddev"], 1),
            "ratio_to_mean": round(ratio, 2) if ratio else None,
            "label": "Unusually high activity" if r["traffic"] > r["mean"] + 5 * r["stddev"] else "Activity burst",
        })
    return bursts


def baseline_stats(conn: sqlite3.Connection, app_name: str, package_name: str = None) -> dict:
    """
    Statistical baseline for one app from previous nights.

    For every completed night in the data, compute the app's overnight
    traffic, then summarize the distribution (median, MAD, min, max).
    The last night is compared against the baseline of the *previous*
    nights using a robust threshold (median + 3 * MAD) so a single
    extreme night cannot inflate its own baseline.
    """
    cfg = get_sleep_config_from_conn(conn)
    start, end = cfg["sleep_start"], cfg["sleep_end"]

    nights = _app_night_traffic(conn, app_name, package_name, start, end)
    if len(nights) < 3:
        return {
            "app_name": app_name, "nights_observed": len(nights), "baseline_available": False,
            "message": "Not enough nights of data to compute a baseline (need at least 3).",
            "nights": nights,
        }

    last = nights[-1]
    prior = [n["total_traffic"] for n in nights[:-1]]
    n = len(prior)
    sorted_p = sorted(prior)

    def _median(vals):
        m = len(vals)
        s = sorted(vals)
        return s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2

    median = _median(sorted_p)
    deviations = sorted(abs(v - median) for v in prior)
    mad = _median(deviations)

    if mad == 0:
        spread = max((max(prior) - min(prior)) / 4, 1) if n > 1 else 1
        upper = median + 3 * spread
        lower = max(median - 3 * spread, 0)
        method = "median +/- 3 * quartile-based spread (MAD was zero)"
    else:
        upper = median + 3 * 1.4826 * mad
        lower = max(median - 3 * 1.4826 * mad, 0)
        method = "median +/- 3 * scaled MAD"

    if last["total_traffic"] > upper:
        status = "Higher than baseline"
    elif last["total_traffic"] < lower:
        status = "Lower than baseline"
    else:
        status = "Normal"

    return {
        "app_name": app_name,
        "nights_observed": n + 1,
        "baseline_available": True,
        "baseline_nights_used": n,
        "baseline_method": method,
        "typical_range": {"low": min(prior), "high": max(prior)},
        "median": round(median),
        "mad": round(mad, 1),
        "threshold_upper": round(upper),
        "threshold_lower": round(lower),
        "last_night": last["total_traffic"],
        "last_night_date": last["night"],
        "status": status,
        "note": "Deviation from baseline is a statistical observation only - it does not imply malicious behavior.",
        "nights": nights,
    }


def multi_night_comparison(conn: sqlite3.Connection, nights: list[str],
                           sleep_start: str = None, sleep_end: str = None) -> dict:
    """
    Compare several nights side by side with averages and % difference
    of the most recent night against the average of the others.
    """
    if not sleep_start or not sleep_end:
        cfg = get_sleep_config_from_conn(conn)
        sleep_start = sleep_start or cfg["sleep_start"]
        sleep_end = sleep_end or cfg["sleep_end"]

    summaries = []
    for night in nights:
        try:
            d = datetime.strptime(night, "%Y-%m-%d").date()
        except ValueError:
            continue
        summaries.append(night_summary(conn, d, sleep_start, sleep_end))

    summaries.sort(key=lambda s: s["night"])

    result = {"nights": summaries}
    if len(summaries) >= 2:
        complete = [s for s in summaries if s["connections"] > 0]
        if len(complete) >= 2:
            last = complete[-1]
            others = complete[:-1]
            for field, label in [("total_traffic", "overnight traffic"),
                                 ("connections", "connections"),
                                 ("bytes_received", "received")]:
                avg_others = sum(o[field] for o in others) / len(others)
                diff_pct = ((last[field] - avg_others) / avg_others * 100) if avg_others else None
                last[f"vs_avg_{field}_pct"] = round(diff_pct, 1) if diff_pct is not None else None
            result["average"] = {
                "total_traffic": round(sum(s["total_traffic"] for s in complete) / len(complete)),
                "bytes_sent": round(sum(s["bytes_sent"] for s in complete) / len(complete)),
                "bytes_received": round(sum(s["bytes_received"] for s in complete) / len(complete)),
                "connections": round(sum(s["connections"] for s in complete) / len(complete)),
            }
    return result


def privacy_insights(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str) -> list[dict]:
    """
    Factual, non-judgmental observations about one night.

    Every insight is a statement that the dataset actually supports;
    no claims about what any company does with the data.
    """
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    insights = []

    row = conn.execute(f"""
        SELECT COUNT(*) AS c FROM connections WHERE {where} AND domain IS NOT NULL AND domain != ''
    """, params).fetchone()
    if row["c"] == 0:
        return [{"text": "No overnight traffic found for this night."}]

    # Most active app by connections
    row = conn.execute(f"""
        SELECT app_name, COUNT(*) AS c FROM connections WHERE {where}
        GROUP BY app_name ORDER BY c DESC LIMIT 1
    """, params).fetchone()
    if row and row["app_name"]:
        insights.append({"text": f"{row['app_name']} generated the most overnight connections ({row['c']})."})

    # App with most distinct domains
    row = conn.execute(f"""
        SELECT app_name, COUNT(DISTINCT domain) AS d FROM connections
        WHERE {where} AND domain IS NOT NULL AND domain != ''
        GROUP BY app_name ORDER BY d DESC LIMIT 1
    """, params).fetchone()
    if row and row["app_name"]:
        insights.append({"text": f"{row['app_name']} contacted {row['d']} distinct domains overnight."})

    # App with most data sent
    row = conn.execute(f"""
        SELECT app_name, SUM(bytes_sent) AS s FROM connections WHERE {where}
        GROUP BY app_name ORDER BY s DESC LIMIT 1
    """, params).fetchone()
    if row and row["app_name"] and row["s"]:
        insights.append({"text": f"{row['app_name']} sent {row['s']} bytes overnight."})

    # Apps active in the core-of-night window 01:00-05:00
    row = conn.execute(f"""
        SELECT COUNT(DISTINCT app_name) AS a FROM connections
        WHERE {where} AND time(first_seen) >= '01:00' AND time(first_seen) < '05:00'
    """, params).fetchone()
    if row and row["a"]:
        insights.append({"text": f"{row['a']} apps generated network traffic between 01:00 and 05:00."})

    # Domains contacted by multiple apps
    row = conn.execute(f"""
        SELECT COUNT(*) AS c FROM (
            SELECT COALESCE(domain, dst_ip) AS dest
            FROM connections WHERE {where}
            GROUP BY dest HAVING COUNT(DISTINCT app_name) > 1
        )
    """, params).fetchone()
    if row and row["c"]:
        insights.append({"text": f"{row['c']} destinations were contacted by multiple apps."})

    return insights


def app_overnight_connections(conn: sqlite3.Connection, night_date: date, sleep_start: str, sleep_end: str,
                              app_name: str, page: int = 1, per_page: int = 50,
                              import_id: int = None, destination: str = None) -> dict:
    """
    Drill-down: raw connection rows behind an overnight aggregate.

    This is how any overnight figure can be traced back to the
    underlying PCAPdroid records.
    """
    where, params = _overnight_where(night_date, sleep_start, sleep_end)
    where += f" AND app_name = {_sql_str(app_name)}"
    if destination:
        where += f" AND COALESCE(domain, dst_ip) = {_sql_str(destination)}"
    if import_id is not None:
        where += f" AND import_id = {int(import_id)}"

    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM connections WHERE {where}"
    ).fetchone()["c"]

    cursor = conn.execute(f"""
        SELECT id, first_seen, last_seen, dst_ip, domain, dst_port, protocol,
               status, bytes_sent, bytes_received, pkts_sent, pkts_received, info
        FROM connections
        WHERE {where}
        ORDER BY first_seen
        LIMIT ? OFFSET ?
    """, [per_page, (page - 1) * per_page])
    rows = [dict(r) for r in cursor.fetchall()]
    return {"total": total, "page": page, "per_page": per_page, "connections": rows}


# ---- helpers -------------------------------------------------------------

def get_sleep_config_from_conn(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('sleep_start', 'sleep_end')"
    ).fetchall()
    values = {r["key"]: r["value"] for r in row}
    return {
        "sleep_start": values.get("sleep_start", DEFAULT_SLEEP_START),
        "sleep_end": values.get("sleep_end", DEFAULT_SLEEP_END),
    }


def _app_night_traffic(conn: sqlite3.Connection, app_name: str, package_name: str,
                       sleep_start: str, sleep_end: str) -> list[dict]:
    """Per-night overnight traffic totals for one app (ascending by night)."""
    cursor = conn.execute(
        "SELECT MIN(first_seen) AS f, MAX(last_seen) AS l FROM connections WHERE app_name = ?",
        (app_name,),
    )
    row = cursor.fetchone()
    if not row or not row["f"]:
        return []

    first_day = datetime.strptime(row["f"][:10], "%Y-%m-%d").date() - timedelta(days=1)
    last_day = datetime.strptime(row["l"][:10], "%Y-%m-%d").date()

    app_filter = f"app_name = {_sql_str(app_name)}"
    if package_name:
        app_filter += f" AND package_name = {_sql_str(package_name)}"

    nights = []
    night = first_day
    while night <= last_day:
        where, params = _overnight_where(night, sleep_start, sleep_end)
        r = conn.execute(
            f"""SELECT SUM(bytes_sent + bytes_received) AS t, COUNT(*) AS c
                FROM connections WHERE {where} AND {app_filter}""",
        ).fetchone()
        if r and (r["t"] or 0) > 0:
            nights.append({
                "night": night.strftime("%Y-%m-%d"),
                "total_traffic": r["t"],
                "connections": r["c"],
            })
        night += timedelta(days=1)
    nights.sort(key=lambda n: n["night"])
    return nights