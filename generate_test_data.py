"""Generate synthetic PCAPdroid CSV dataset for testing."""

import csv
import random
import os
from datetime import datetime, timedelta

# Configuration
NUM_RECORDS = 5000
OUTPUT_FILE = "test_data.csv"

# App definitions
APPS = [
    {"app": "Chrome", "package": "com.android.chrome", "uids": ["u0_a100"]},
    {"app": "YouTube", "package": "com.google.android.youtube", "uids": ["u0_a101"]},
    {"app": "Instagram", "package": "com.instagram.android", "uids": ["u0_a102"]},
    {"app": "WhatsApp", "package": "com.whatsapp", "uids": ["u0_a103"]},
    {"app": "Gmail", "package": "com.google.android.gm", "uids": ["u0_a104"]},
    {"app": "Facebook", "package": "com.facebook.katana", "uids": ["u0_a105"]},
    {"app": "Twitter", "package": "com.twitter.android", "uids": ["u0_a106"]},
    {"app": "Spotify", "package": "com.spotify.music", "uids": ["u0_a107"]},
    {"app": "Netflix", "package": "com.netflix.mediaclient", "uids": ["u0_a108"]},
    {"app": "Google Maps", "package": "com.google.android.apps.maps", "uids": ["u0_a109"]},
    {"app": "Amazon", "package": "com.amazon.mShop.android", "uids": ["u0_a110"]},
    {"app": "Play Store", "package": "com.android.vending", "uids": ["u0_a111"]},
    {"app": "System Update", "package": "com.android.providers.downloads", "uids": ["u0_a112"]},
    {"app": "Weather", "package": "com.google.android.apps.weather", "uids": ["u0_a113"]},
    {"app": "Telegram", "package": "org.telegram.messenger", "uids": ["u0_a114"]},
]

# Destination IPs and domains
DOMAINS = [
    {"ip": "142.250.80.46", "domain": "googleapis.com"},
    {"ip": "157.240.1.35", "domain": "facebook.com"},
    {"ip": "157.240.1.37", "domain": "fbcdn.net"},
    {"ip": "103.99.56.35", "domain": "graph.facebook.com"},
    {"ip": "142.250.185.78", "domain": "youtube.com"},
    {"ip": "35.186.224.43", "domain": "mtalk.google.com"},
    {"ip": "52.94.236.248", "domain": "s3.amazonaws.com"},
    {"ip": "54.231.196.244", "domain": "d1-an-2.akamai.net"},
    {"ip": "199.232.69.194", "domain": "user-images.githubusercontent.com"},
    {"ip": "151.101.1.69", "domain": "cdn.jsdelivr.net"},
    {"ip": "104.16.85.20", "domain": "cloudflare.com"},
    {"ip": "172.217.14.206", "domain": "google.com"},
    {"ip": "31.13.65.36", "domain": "instagram.com"},
    {"ip": "198.252.206.16", "domain": "cdn.whatsapp.net"},
    {"ip": "91.198.174.192", "domain": "wikipedia.org"},
    {"ip": "203.192.5.163", "domain": "weather-api.example.com"},
    {"ip": "185.199.108.153", "domain": "api.github.com"},
    {"ip": "52.84.150.33", "domain": "d1.awsstatic.com"},
    {"ip": "13.107.42.14", "domain": "microsoft.com"},
    {"ip": "20.190.128.35", "domain": "officecdn.microsoft.com"},
]

# DNS servers
DNS_SERVERS = ["8.8.8.8", "8.8.4.4", "1.1.1.1"]

# Protocols
PROTOCOLS = ["TCP", "UDP"]

# Statuses
STATUSES = ["success", "failed", "timeout"]


def generate_csv():
    """Generate synthetic PCAPdroid CSV file."""
    random.seed(42)  # Reproducible

    start_time = datetime(2026, 9, 6, 0, 0, 0)
    end_time = start_time + timedelta(hours=24)
    time_range_seconds = int((end_time - start_time).total_seconds())

    rows = []

    for i in range(NUM_RECORDS):
        app = random.choice(APPS)
        domain_info = random.choice(DOMAINS)
        protocol = random.choice(PROTOCOLS)

        # Generate timestamp
        offset = random.randint(0, time_range_seconds)
        first_seen = start_time + timedelta(seconds=offset)
        last_offset = random.randint(0, 3600)
        last_seen = first_seen + timedelta(seconds=last_offset)

        # Bytes (realistic ranges)
        bytes_sent = random.randint(100, 500000)
        bytes_received = random.randint(1000, 10000000)
        pkts_sent = random.randint(1, 100)
        pkts_received = random.randint(1, 500)

        # Destination port
        if protocol == "TCP":
            dst_port = random.choice([80, 443, 8080, 8443, 5228, 5222])
        else:
            dst_port = random.choice([53, 443, 5222, 8080])

        # Status
        status = random.choices(STATUSES, weights=[85, 10, 5])[0]

        # Info field
        info = ""
        if dst_port == 53 and protocol == "UDP":
            info = f"query A {domain_info['domain']} IN"
        else:
            info = random.choice([
                "",
                "TLS1.2",
                "HTTP/1.1",
                "TCP Keep-Alive",
                "ACK",
                f"GET /api/data HTTP/1.1",
                f"POST /upload HTTP/1.1",
            ])

        row = {
            "SrcIp": f"192.168.1.{random.randint(1, 254)}",
            "SrcPort": random.randint(1024, 65535),
            "DstIp": domain_info["ip"],
            "DstPort": dst_port,
            "UID": random.choice(app["uids"]),
            "App": app["app"],
            "PackageName": app["package"],
            "Proto": protocol,
            "Status": status,
            "Info": info,
            "BytesSent": bytes_sent,
            "BytesRcvd": bytes_received,
            "PktsSent": pkts_sent,
            "PktsRcvd": pkts_received,
            "FirstSeen": first_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "LastSeen": last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(row)

    # Add some DNS-specific records
    for _ in range(500):
        app = random.choice(APPS)
        domain_info = random.choice(DOMAINS)
        offset = random.randint(0, time_range_seconds)
        first_seen = start_time + timedelta(seconds=offset)
        last_seen = first_seen + timedelta(seconds=random.randint(0, 60))

        row = {
            "SrcIp": f"192.168.1.{random.randint(1, 254)}",
            "SrcPort": random.randint(1024, 65535),
            "DstIp": random.choice(DNS_SERVERS),
            "DstPort": 53,
            "UID": random.choice(app["uids"]),
            "App": app["app"],
            "PackageName": app["package"],
            "Proto": "UDP",
            "Status": "success",
            "Info": f"query A {domain_info['domain']} IN",
            "BytesSent": random.randint(50, 200),
            "BytesRcvd": random.randint(100, 500),
            "PktsSent": 1,
            "PktsRcvd": 1,
            "FirstSeen": first_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "LastSeen": last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(row)

    # Add some malformed rows for testing
    rows.append({
        "SrcIp": "",
        "SrcPort": "",
        "DstIp": "",
        "DstPort": "",
        "UID": "",
        "App": "",
        "PackageName": "",
        "Proto": "",
        "Status": "",
        "Info": "",
        "BytesSent": "",
        "BytesRcvd": "",
        "PktsSent": "",
        "PktsRcvd": "",
        "FirstSeen": "",
        "LastSeen": "",
    })

    # Add a duplicate row
    rows.append(rows[0].copy())

    # Add some IPv6 records
    for _ in range(50):
        app = random.choice(APPS)
        domain_info = random.choice(DOMAINS)
        offset = random.randint(0, time_range_seconds)
        first_seen = start_time + timedelta(seconds=offset)

        row = {
            "SrcIp": "fe80::1",
            "SrcPort": random.randint(1024, 65535),
            "DstIp": "2607:f8b0:4004:800::200e",
            "DstPort": 443,
            "UID": random.choice(app["uids"]),
            "App": app["app"],
            "PackageName": app["package"],
            "Proto": "TCP",
            "Status": "success",
            "Info": "TLS1.2",
            "BytesSent": random.randint(100, 10000),
            "BytesRcvd": random.randint(1000, 1000000),
            "PktsSent": random.randint(1, 50),
            "PktsRcvd": random.randint(1, 200),
            "FirstSeen": first_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "LastSeen": first_seen.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(row)

    # Shuffle
    random.shuffle(rows)

    # Write CSV
    fieldnames = [
        "SrcIp", "SrcPort", "DstIp", "DstPort", "UID", "App", "PackageName",
        "Proto", "Status", "Info", "BytesSent", "BytesRcvd", "PktsSent",
        "PktsRcvd", "FirstSeen", "LastSeen"
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} rows (including {len(rows) - NUM_RECORDS - 500 - 50 - 2} edge cases)")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_csv()
