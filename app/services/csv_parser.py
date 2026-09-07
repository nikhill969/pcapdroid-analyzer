"""Robust CSV parser for PCAPdroid exports. Handles missing fields, malformed rows, duplicates."""

import csv
import hashlib
import io
import re
from datetime import datetime
from typing import Iterator, Optional


# DNS port detection
DNS_PORTS = {53, 853}
# Common ports that indicate DNS-like traffic
DNS_INFO_PATTERNS = [
    re.compile(r"query.*\.", re.IGNORECASE),
    re.compile(r"DNS", re.IGNORECASE),
    re.compile(r"resolve", re.IGNORECASE),
]


def is_dns_traffic(row: dict) -> bool:
    """Detect if a row represents DNS traffic."""
    dst_port = _safe_int(row.get("DstPort"))
    if dst_port and dst_port in DNS_PORTS:
        return True
    info = row.get("Info", "") or ""
    for pattern in DNS_INFO_PATTERNS:
        if pattern.search(info):
            return True
    proto = (row.get("Proto") or "").upper()
    if proto in ("UDP", "DNS"):
        dst_port = _safe_int(row.get("DstPort"))
        if dst_port and dst_port in DNS_PORTS:
            return True
    return False


def extract_domain_from_info(info: Optional[str]) -> Optional[str]:
    """Extract domain name from Info field if present."""
    if not info:
        return None
    info = info.strip()
    if not info:
        return None

    # Try to extract domain from DNS query patterns
    # Pattern: "query [type] [domain] IN ..."
    match = re.search(r'query\s+\S+\s+([a-zA-Z0-9][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,})\s+IN', info, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    # Pattern: just a domain-like string
    match = re.search(r'([a-zA-Z0-9][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,})', info)
    if match:
        candidate = match.group(1).lower()
        # Filter out obvious non-domains
        if candidate not in ("tcp", "udp", "in", "no", "yes", "null"):
            return candidate

    return None


def determine_direction(row: dict) -> str:
    """Determine connection direction (uplink/downlink)."""
    src_ip = (row.get("SrcIp") or "").lower()
    # Simple heuristic: if source is local IP range, it's uplink (sent)
    local_prefixes = ("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                      "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                      "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                      "172.29.", "172.30.", "172.31.", "127.")
    if any(src_ip.startswith(p) for p in local_prefixes):
        return "uplink"
    return "downlink"


def _safe_int(value: Optional[str]) -> Optional[int]:
    """Safely convert to int, returning None for invalid values."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _safe_float(value: Optional[str]) -> Optional[float]:
    """Safely convert to float, returning None for invalid values."""
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def normalize_timestamp(ts: Optional[str]) -> Optional[str]:
    """Normalize timestamp to ISO format."""
    if not ts:
        return None
    ts = ts.strip()
    if not ts:
        return None

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

    # Return as-is if no format matches
    return ts


def _make_record_hash(row: dict) -> str:
    """Create a hash for duplicate detection."""
    key_parts = [
        row.get("SrcIp", "") or "",
        row.get("SrcPort", "") or "",
        row.get("DstIp", "") or "",
        row.get("DstPort", "") or "",
        row.get("Proto", "") or "",
        row.get("FirstSeen", "") or "",
    ]
    key = "|".join(key_parts)
    return hashlib.md5(key.encode()).hexdigest()


def parse_csv_file(file_content: bytes, filename: str = "") -> dict:
    """
    Parse a PCAPdroid CSV file.

    Returns:
        dict with keys:
        - rows: list of normalized row dicts
        - total_rows: total rows in file
        - valid_rows: rows successfully parsed
        - duplicate_rows: rows detected as duplicates
        - malformed_rows: rows that couldn't be parsed
        - errors: list of error messages
    """
    result = {
        "filename": filename,
        "total_rows": 0,
        "valid_rows": 0,
        "duplicate_rows": 0,
        "malformed_rows": 0,
        "errors": [],
        "rows": [],
    }

    try:
        text = file_content.decode("utf-8", errors="replace")
    except Exception as e:
        result["errors"].append(f"Failed to decode file: {e}")
        return result

    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        result["errors"].append(f"Failed to parse CSV: {e}")
        return result

    seen_hashes = set()

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        result["total_rows"] += 1

        try:
            # Skip completely empty rows
            if not any(v and str(v).strip() for v in row.values()):
                result["malformed_rows"] += 1
                continue

            # Normalize keys (strip whitespace)
            normalized = {k.strip(): v for k, v in row.items() if k is not None}

            # Extract and validate fields
            record = {
                "src_ip": (normalized.get("SrcIp") or "").strip() or None,
                "src_port": _safe_int(normalized.get("SrcPort")),
                "dst_ip": (normalized.get("DstIp") or "").strip() or None,
                "dst_port": _safe_int(normalized.get("DstPort")),
                "uid": (normalized.get("UID") or "").strip() or None,
                "app_name": (normalized.get("App") or "").strip() or None,
                "package_name": (normalized.get("PackageName") or "").strip() or None,
                "protocol": (normalized.get("Proto") or "").strip().upper() or None,
                "status": (normalized.get("Status") or "").strip() or None,
                "info": (normalized.get("Info") or "").strip() or None,
                "bytes_sent": max(0, _safe_int(normalized.get("BytesSent")) or 0),
                "bytes_received": max(0, _safe_int(normalized.get("BytesRcvd")) or 0),
                "pkts_sent": max(0, _safe_int(normalized.get("PktsSent")) or 0),
                "pkts_received": max(0, _safe_int(normalized.get("PktsRcvd")) or 0),
                "first_seen": normalize_timestamp(normalized.get("FirstSeen")),
                "last_seen": normalize_timestamp(normalized.get("LastSeen")),
            }

            # Skip rows with no meaningful data
            if not any([
                record["src_ip"], record["dst_ip"],
                record["app_name"], record["package_name"],
            ]):
                result["malformed_rows"] += 1
                continue

            # Detect DNS
            record["is_dns"] = is_dns_traffic(normalized)
            record["direction"] = determine_direction(normalized)

            # Extract domain from Info field
            if record["is_dns"]:
                record["domain"] = extract_domain_from_info(record["info"])
            else:
                # Also try to extract domain from non-DNS info
                record["domain"] = extract_domain_from_info(record["info"])

            # Duplicate detection
            record_hash = _make_record_hash(normalized)
            if record_hash in seen_hashes:
                result["duplicate_rows"] += 1
                continue
            seen_hashes.add(record_hash)

            result["rows"].append(record)
            result["valid_rows"] += 1

        except Exception as e:
            result["malformed_rows"] += 1
            if len(result["errors"]) < 100:  # Limit error messages
                result["errors"].append(f"Row {row_num}: {e}")

    return result
