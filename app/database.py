"""SQLite database initialization and connection management."""

import sqlite3
import os
from pathlib import Path

DB_DIR = Path(os.environ.get("PCAP_DB_DIR", "data"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "pcap_analyzer.db"


def get_connection() -> sqlite3.Connection:
    """Get a new database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Raw connections table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src_ip TEXT,
            src_port INTEGER,
            dst_ip TEXT,
            dst_port INTEGER,
            uid TEXT,
            app_name TEXT,
            package_name TEXT,
            protocol TEXT,
            status TEXT,
            info TEXT,
            bytes_sent INTEGER DEFAULT 0,
            bytes_received INTEGER DEFAULT 0,
            pkts_sent INTEGER DEFAULT 0,
            pkts_received INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            direction TEXT,
            domain TEXT,
            is_dns INTEGER DEFAULT 0,
            import_id INTEGER
        )
    """)

    # Materialized app stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT,
            package_name TEXT,
            total_bytes_sent INTEGER DEFAULT 0,
            total_bytes_received INTEGER DEFAULT 0,
            total_connections INTEGER DEFAULT 0,
            unique_destinations INTEGER DEFAULT 0,
            dns_count INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            UNIQUE(app_name, package_name)
        )
    """)

    # Materialized domain stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS domain_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE,
            apps_contacting TEXT,
            connection_count INTEGER DEFAULT 0,
            total_bytes_sent INTEGER DEFAULT 0,
            total_bytes_received INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        )
    """)

    # Import tracking / recording sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            row_count INTEGER,
            imported_at TEXT,
            file_size_bytes INTEGER,
            first_packet TEXT,
            last_packet TEXT,
            total_traffic_bytes INTEGER DEFAULT 0
        )
    """)

    # User settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_connections_app ON connections(app_name)",
        "CREATE INDEX IF NOT EXISTS idx_connections_package ON connections(package_name)",
        "CREATE INDEX IF NOT EXISTS idx_connections_domain ON connections(domain)",
        "CREATE INDEX IF NOT EXISTS idx_connections_dst_ip ON connections(dst_ip)",
        "CREATE INDEX IF NOT EXISTS idx_connections_protocol ON connections(protocol)",
        "CREATE INDEX IF NOT EXISTS idx_connections_first_seen ON connections(first_seen)",
        "CREATE INDEX IF NOT EXISTS idx_connections_import ON connections(import_id)",
        "CREATE INDEX IF NOT EXISTS idx_connections_dst_port ON connections(dst_port)",
        "CREATE INDEX IF NOT EXISTS idx_imports_first_packet ON imports(first_packet)",
        "CREATE INDEX IF NOT EXISTS idx_imports_last_packet ON imports(last_packet)",
    ]
    for idx in indexes:
        cursor.execute(idx)

    # Migration: add session columns to pre-existing imports table
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(imports)").fetchall()}
    for col, decl in [
        ("first_packet", "TEXT"),
        ("last_packet", "TEXT"),
        ("total_traffic_bytes", "INTEGER DEFAULT 0"),
    ]:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE imports ADD COLUMN {col} {decl}")

    conn.commit()
    conn.close()


def get_setting(key: str, default=None):
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Generator for database connection context."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
