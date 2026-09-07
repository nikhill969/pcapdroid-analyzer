"""Analytics engine: computes aggregates from parsed data and stores in SQLite."""

import sqlite3
from datetime import datetime
from typing import Optional


def store_records(conn: sqlite3.Connection, records: list[dict], import_id: int) -> int:
    """Bulk insert parsed records into connections table."""
    cursor = conn.cursor()
    batch_size = 1000

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        # Add import_id to each record and convert is_dns to int
        for record in batch:
            record["import_id"] = import_id
            record["is_dns"] = 1 if record.get("is_dns") else 0
        cursor.executemany("""
            INSERT INTO connections (
                src_ip, src_port, dst_ip, dst_port, uid, app_name, package_name,
                protocol, status, info, bytes_sent, bytes_received,
                pkts_sent, pkts_received, first_seen, last_seen,
                direction, domain, is_dns, import_id
            ) VALUES (
                :src_ip, :src_port, :dst_ip, :dst_port, :uid, :app_name, :package_name,
                :protocol, :status, :info, :bytes_sent, :bytes_received,
                :pkts_sent, :pkts_received, :first_seen, :last_seen,
                :direction, :domain, :is_dns, :import_id
            )
        """, batch)

    conn.commit()
    return len(records)


def track_import(conn: sqlite3.Connection, filename: str, row_count: int, file_size: int,
                 first_packet: str = None, last_packet: str = None,
                 total_traffic_bytes: int = 0) -> int:
    """Record an import event (recording session)."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO imports (filename, row_count, imported_at, file_size_bytes,
                             first_packet, last_packet, total_traffic_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (filename, row_count, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), file_size,
          first_packet, last_packet, total_traffic_bytes))
    conn.commit()
    return cursor.lastrowid


def refresh_app_stats(conn: sqlite3.Connection) -> None:
    """Rebuild materialized app_stats table from connections."""
    conn.execute("DELETE FROM app_stats")
    conn.execute("""
        INSERT INTO app_stats (
            app_name, package_name, total_bytes_sent, total_bytes_received,
            total_connections, unique_destinations, dns_count, first_seen, last_seen
        )
        SELECT
            COALESCE(app_name, 'Unknown') as app_name,
            COALESCE(package_name, 'Unknown') as package_name,
            SUM(bytes_sent) as total_bytes_sent,
            SUM(bytes_received) as total_bytes_received,
            COUNT(*) as total_connections,
            COUNT(DISTINCT dst_ip) as unique_destinations,
            SUM(CASE WHEN is_dns = 1 THEN 1 ELSE 0 END) as dns_count,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM connections
        GROUP BY COALESCE(app_name, 'Unknown'), COALESCE(package_name, 'Unknown')
    """)
    conn.commit()


def refresh_domain_stats(conn: sqlite3.Connection) -> None:
    """Rebuild materialized domain_stats table from connections."""
    conn.execute("DELETE FROM domain_stats")
    conn.execute("""
        INSERT INTO domain_stats (
            domain, apps_contacting, connection_count,
            total_bytes_sent, total_bytes_received, first_seen, last_seen
        )
        SELECT
            COALESCE(domain, 'Unidentified') as domain,
            GROUP_CONCAT(DISTINCT COALESCE(app_name, 'Unknown')) as apps_contacting,
            COUNT(*) as connection_count,
            SUM(bytes_sent) as total_bytes_sent,
            SUM(bytes_received) as total_bytes_received,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM connections
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
    """)
    conn.commit()


def refresh_all_stats(conn: sqlite3.Connection) -> None:
    """Refresh all materialized views."""
    refresh_app_stats(conn)
    refresh_domain_stats(conn)


def get_dashboard_stats(conn: sqlite3.Connection) -> dict:
    """Get dashboard overview statistics."""
    cursor = conn.cursor()

    # Total bytes
    cursor.execute("""
        SELECT
            COALESCE(SUM(bytes_sent), 0) as total_bytes_sent,
            COALESCE(SUM(bytes_received), 0) as total_bytes_received,
            COUNT(*) as total_connections
        FROM connections
    """)
    totals = cursor.fetchone()

    # Unique apps
    cursor.execute("""
        SELECT COUNT(DISTINCT COALESCE(app_name, 'Unknown')) as unique_apps
        FROM connections
    """)
    unique_apps = cursor.fetchone()["unique_apps"]

    # Unique destinations
    cursor.execute("""
        SELECT COUNT(DISTINCT COALESCE(dst_ip, '')) as unique_ips
        FROM connections
        WHERE dst_ip IS NOT NULL
    """)
    unique_ips = cursor.fetchone()["unique_ips"]

    # Time range
    cursor.execute("""
        SELECT MIN(first_seen) as earliest, MAX(last_seen) as latest
        FROM connections
        WHERE first_seen IS NOT NULL
    """)
    time_range = cursor.fetchone()

    # Traffic by app (top 20)
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            COUNT(*) as connections
        FROM connections
        GROUP BY app_name, package_name
        ORDER BY (bytes_sent + bytes_received) DESC
        LIMIT 20
    """)
    traffic_by_app = [dict(row) for row in cursor.fetchall()]

    # Connections by app (top 20)
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            COUNT(*) as connections
        FROM connections
        GROUP BY app_name, package_name
        ORDER BY connections DESC
        LIMIT 20
    """)
    connections_by_app = [dict(row) for row in cursor.fetchall()]

    # Traffic over time (by hour)
    cursor.execute("""
        SELECT
            strftime('%Y-%m-%d %H:00', first_seen) as hour,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received
        FROM connections
        WHERE first_seen IS NOT NULL
        GROUP BY hour
        ORDER BY hour
    """)
    traffic_over_time = [dict(row) for row in cursor.fetchall()]

    # Sent vs received by protocol
    cursor.execute("""
        SELECT
            COALESCE(protocol, 'Unknown') as protocol,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received
        FROM connections
        GROUP BY protocol
    """)
    traffic_by_protocol = [dict(row) for row in cursor.fetchall()]

    return {
        "total_bytes_sent": totals["total_bytes_sent"],
        "total_bytes_received": totals["total_bytes_received"],
        "total_bytes": totals["total_bytes_sent"] + totals["total_bytes_received"],
        "total_connections": totals["total_connections"],
        "unique_apps": unique_apps,
        "unique_destinations": unique_ips,
        "earliest": time_range["earliest"],
        "latest": time_range["latest"],
        "traffic_by_app": traffic_by_app,
        "connections_by_app": connections_by_app,
        "traffic_over_time": traffic_over_time,
        "traffic_by_protocol": traffic_by_protocol,
    }


def get_app_details(conn: sqlite3.Connection, app_name: str, package_name: str = "",
                    page: int = 1, per_page: int = 50) -> dict:
    """Get detailed statistics for a specific app."""
    cursor = conn.cursor()

    # App summary
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app_name,
            COALESCE(package_name, 'Unknown') as package_name,
            SUM(bytes_sent) as total_bytes_sent,
            SUM(bytes_received) as total_bytes_received,
            COUNT(*) as total_connections,
            COUNT(DISTINCT dst_ip) as unique_destinations,
            SUM(CASE WHEN is_dns = 1 THEN 1 ELSE 0 END) as dns_count,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM connections
        WHERE COALESCE(app_name, 'Unknown') = ?
          AND (package_name = ? OR ? = '')
        GROUP BY app_name, package_name
    """, (app_name, package_name if package_name else app_name, package_name if package_name else ""))

    summary = cursor.fetchone()
    if not summary:
        return {"error": "App not found"}

    result = dict(summary)
    result["total_bytes"] = result["total_bytes_sent"] + result["total_bytes_received"]

    # Destinations for this app
    offset = (page - 1) * per_page
    cursor.execute("""
        SELECT
            COALESCE(dst_ip, 'Unknown') as dst_ip,
            COALESCE(domain, 'Unidentified') as domain,
            dst_port,
            protocol,
            COUNT(*) as connections,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM connections
        WHERE COALESCE(app_name, 'Unknown') = ?
          AND (package_name = ? OR ? = '')
        GROUP BY dst_ip, dst_port, protocol
        ORDER BY (bytes_sent + bytes_received) DESC
        LIMIT ? OFFSET ?
    """, (app_name, package_name if package_name else app_name, package_name if package_name else "", per_page, offset))

    result["destinations"] = [dict(row) for row in cursor.fetchall()]

    # Total destination count for pagination
    cursor.execute("""
        SELECT COUNT(DISTINCT dst_ip) as cnt
        FROM connections
        WHERE COALESCE(app_name, 'Unknown') = ?
          AND (package_name = ? OR ? = '')
    """, (app_name, package_name if package_name else app_name, package_name if package_name else ""))

    result["total_destinations"] = cursor.fetchone()["cnt"]
    result["page"] = page
    result["per_page"] = per_page
    result["total_pages"] = (result["total_destinations"] + per_page - 1) // per_page

    return result


def get_domain_details(conn: sqlite3.Connection, domain: str) -> dict:
    """Get detailed statistics for a specific domain."""
    cursor = conn.cursor()

    # Domain summary
    cursor.execute("""
        SELECT * FROM domain_stats WHERE domain = ?
    """, (domain,))
    summary = cursor.fetchone()
    if not summary:
        return {"error": "Domain not found"}

    result = dict(summary)
    result["total_bytes"] = result["total_bytes_sent"] + result["total_bytes_received"]
    result["apps_list"] = result["apps_contacting"].split(",") if result["apps_contacting"] else []

    # Connections to this domain
    cursor.execute("""
        SELECT
            app_name, package_name,
            dst_ip, dst_port, protocol,
            COUNT(*) as connections,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received
        FROM connections
        WHERE domain = ?
        GROUP BY app_name, package_name, dst_ip, dst_port, protocol
        ORDER BY (bytes_sent + bytes_received) DESC
    """, (domain,))

    result["connections"] = [dict(row) for row in cursor.fetchall()]
    return result


def get_dns_analysis(conn: sqlite3.Connection, page: int = 1, per_page: int = 50) -> dict:
    """Get DNS analysis results."""
    cursor = conn.cursor()

    # DNS traffic grouped by domain
    offset = (page - 1) * per_page
    cursor.execute("""
        SELECT
            COALESCE(domain, 'Unidentified') as domain,
            GROUP_CONCAT(DISTINCT COALESCE(app_name, 'Unknown')) as apps,
            COUNT(*) as connection_count,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM connections
        WHERE is_dns = 1 AND domain IS NOT NULL AND domain != ''
        GROUP BY domain
        ORDER BY connection_count DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))

    dns_domains = [dict(row) for row in cursor.fetchall()]

    # Total count for pagination
    cursor.execute("""
        SELECT COUNT(DISTINCT COALESCE(domain, 'Unidentified')) as cnt
        FROM connections
        WHERE is_dns = 1 AND domain IS NOT NULL AND domain != ''
    """)
    total = cursor.fetchone()["cnt"]

    # App -> DNS domain mapping
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            COALESCE(domain, 'Unidentified') as domain,
            COUNT(*) as queries
        FROM connections
        WHERE is_dns = 1 AND domain IS NOT NULL AND domain != ''
        GROUP BY app_name, domain
        ORDER BY app, queries DESC
    """)
    app_dns_mapping = [dict(row) for row in cursor.fetchall()]

    return {
        "dns_domains": dns_domains,
        "total_domains": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "app_dns_mapping": app_dns_mapping,
    }


def get_privacy_metrics(conn: sqlite3.Connection) -> dict:
    """Generate privacy-relevant metrics."""
    cursor = conn.cursor()

    # Apps contacting most unique domains
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            COUNT(DISTINCT COALESCE(domain, 'Unidentified')) as unique_domains,
            COUNT(DISTINCT dst_ip) as unique_ips,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received
        FROM connections
        GROUP BY app_name
        ORDER BY unique_domains DESC
        LIMIT 10
    """)
    apps_most_domains = [dict(row) for row in cursor.fetchall()]

    # Apps sending most data
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            COUNT(*) as connections
        FROM connections
        GROUP BY app_name
        ORDER BY bytes_sent DESC
        LIMIT 10
    """)
    apps_most_sent = [dict(row) for row in cursor.fetchall()]

    # Apps receiving most data
    cursor.execute("""
        SELECT
            COALESCE(app_name, 'Unknown') as app,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            COUNT(*) as connections
        FROM connections
        GROUP BY app_name
        ORDER BY bytes_received DESC
        LIMIT 10
    """)
    apps_most_received = [dict(row) for row in cursor.fetchall()]

    # Most contacted third-party domains
    cursor.execute("""
        SELECT
            domain,
            COUNT(*) as connection_count,
            GROUP_CONCAT(DISTINCT COALESCE(app_name, 'Unknown')) as apps
        FROM connections
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
        ORDER BY connection_count DESC
        LIMIT 20
    """)
    top_domains = [dict(row) for row in cursor.fetchall()]

    # Domains contacted by multiple apps
    cursor.execute("""
        SELECT
            domain,
            COUNT(DISTINCT COALESCE(app_name, 'Unknown')) as app_count,
            GROUP_CONCAT(DISTINCT COALESCE(app_name, 'Unknown')) as apps
        FROM connections
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
        HAVING app_count > 1
        ORDER BY app_count DESC
        LIMIT 20
    """)
    shared_domains = [dict(row) for row in cursor.fetchall()]

    # Unidentified destinations (no domain mapped)
    cursor.execute("""
        SELECT
            dst_ip,
            COUNT(*) as connection_count,
            GROUP_CONCAT(DISTINCT COALESCE(app_name, 'Unknown')) as apps,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received
        FROM connections
        WHERE domain IS NULL OR domain = ''
        GROUP BY dst_ip
        ORDER BY connection_count DESC
        LIMIT 20
    """)
    unidentified = [dict(row) for row in cursor.fetchall()]

    return {
        "apps_most_domains": apps_most_domains,
        "apps_most_sent": apps_most_sent,
        "apps_most_received": apps_most_received,
        "top_domains": top_domains,
        "shared_domains": shared_domains,
        "unidentified_destinations": unidentified,
    }


def search_connections(conn: sqlite3.Connection, query: str,
                       app: str = "", domain: str = "", protocol: str = "",
                       start_date: str = "", end_date: str = "",
                       page: int = 1, per_page: int = 50) -> dict:
    """Search connections by various criteria."""
    cursor = conn.cursor()

    conditions = []
    params = []

    if query:
        conditions.append("""(
            COALESCE(app_name, '') LIKE ? OR
            COALESCE(package_name, '') LIKE ? OR
            COALESCE(domain, '') LIKE ? OR
            COALESCE(dst_ip, '') LIKE ? OR
            COALESCE(src_ip, '') LIKE ?
        )""")
        like_query = f"%{query}%"
        params.extend([like_query, like_query, like_query, like_query, like_query])

    if app:
        conditions.append("COALESCE(app_name, '') LIKE ?")
        params.append(f"%{app}%")

    if domain:
        conditions.append("COALESCE(domain, '') LIKE ?")
        params.append(f"%{domain}%")

    if protocol:
        conditions.append("protocol = ?")
        params.append(protocol.upper())

    if start_date:
        conditions.append("first_seen >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("first_seen <= ?")
        params.append(end_date)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Get total count
    count_query = f"SELECT COUNT(*) as cnt FROM connections {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()["cnt"]

    # Get results
    offset = (page - 1) * per_page
    result_query = f"""
        SELECT
            src_ip, src_port, dst_ip, dst_port,
            COALESCE(app_name, 'Unknown') as app_name,
            COALESCE(package_name, 'Unknown') as package_name,
            protocol, status, info,
            bytes_sent, bytes_received,
            first_seen, last_seen,
            COALESCE(domain, 'Unidentified') as domain
        FROM connections
        {where_clause}
        ORDER BY first_seen DESC
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    cursor.execute(result_query, params)
    results = [dict(row) for row in cursor.fetchall()]

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


def get_timeline_data(conn: sqlite3.Connection, interval: str = "hour",
                      app: str = "", domain: str = "") -> list[dict]:
    """Get timeline data for charting."""
    cursor = conn.cursor()

    if interval == "hour":
        time_fmt = "%Y-%m-%d %H:00"
    elif interval == "day":
        time_fmt = "%Y-%m-%d"
    else:
        time_fmt = "%Y-%m-%d %H:00"

    where_conditions = []
    params = []

    if app:
        where_conditions.append("COALESCE(app_name, '') LIKE ?")
        params.append(f"%{app}%")

    if domain:
        where_conditions.append("COALESCE(domain, '') LIKE ?")
        params.append(f"%{domain}%")

    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)

    cursor.execute(f"""
        SELECT
            strftime('{time_fmt}', first_seen) as time_bucket,
            SUM(bytes_sent) as bytes_sent,
            SUM(bytes_received) as bytes_received,
            COUNT(*) as connections
        FROM connections
        WHERE first_seen IS NOT NULL
        {where_clause}
        GROUP BY time_bucket
        ORDER BY time_bucket
    """, params)

    return [dict(row) for row in cursor.fetchall()]
