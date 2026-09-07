"""Generate multi-night PCAPdroid CSV test data with known activity patterns.

Produces one CSV per night so each file imports as a separate recording
session. Patterns are deterministic (seeded) so overnight statistics can
be mathematically verified:

  Night +2 (oldest): quiet baseline
  Night +1:          normal baseline
  Night 0 (latest):  includes a deliberate Instagram burst 02:14-02:19
                     (~18 MB received) and higher overall volume
"""

import csv
import os
import random
from datetime import datetime, timedelta

OUTPUT_DIR = "test_data"
SLEEP_START = 23  # 23:00
SLEEP_END = 7     # 07:00 next day

random.seed(1234)

# (app, package) -> list of (domain, ip)
APPS = {
    "WhatsApp":  ("com.whatsapp", [("cdn.whatsapp.net", "198.252.206.16"),
                                   ("graph.facebook.com", "103.99.56.35")]),
    "Instagram": ("com.instagram.android", [("instagram.com", "31.13.65.36"),
                                            ("graph.facebook.com", "103.99.56.35"),
                                            ("fbcdn.net", "157.240.1.37")]),
    "Play Services": ("com.google.android.gms", [("googleapis.com", "142.250.80.46"),
                                                 ("googleusercontent.com", "142.250.185.78"),
                                                 ("mtalk.google.com", "35.186.224.43")]),
    "Chrome":    ("com.android.chrome", [("google.com", "172.217.14.206"),
                                         ("googleapis.com", "142.250.80.46")]),
    "Weather":   ("com.google.android.apps.weather", [("weather-api.example.com", "203.192.5.163")]),
    "System Update": ("com.android.providers.downloads", [("googleapis.com", "142.250.80.46")]),
}

DNS_SERVERS = ["8.8.8.8", "1.1.1.1"]


def _conn_row(app, dest, ts, sent, rcvd, burst=False):
    proto = "TCP"
    return {
        "SrcIp": "192.168.1.100",
        "SrcPort": random.randint(1024, 65000),
        "DstIp": dest[1],
        "DstPort": 443,
        "UID": "u0_a1",
        "App": app,
        "PackageName": APPS[app][0],
        "Proto": proto,
        "Status": "success",
        "Info": "TLS1.2",
        "BytesSent": sent,
        "BytesRcvd": rcvd,
        "PktsSent": max(1, sent // 600),
        "PktsRcvd": max(1, rcvd // 1400),
        "FirstSeen": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "LastSeen": (ts + timedelta(seconds=random.randint(5, 60))).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _dns_row(app, domain, ts):
    return {
        "SrcIp": "192.168.1.100",
        "SrcPort": random.randint(1024, 65000),
        "DstIp": random.choice(DNS_SERVERS),
        "DstPort": 53,
        "UID": "u0_a1",
        "App": app,
        "PackageName": APPS[app][0],
        "Proto": "UDP",
        "Status": "success",
        "Info": f"query A {domain} IN",
        "BytesSent": random.randint(50, 120),
        "BytesRcvd": random.randint(80, 300),
        "PktsSent": 1,
        "PktsRcvd": 2,
        "FirstSeen": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "LastSeen": ts.strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_night(night_date: datetime, burst: bool) -> list:
    """Generate overnight rows for one night (23:00 -> 07:00 next day)."""
    rows = []

    def rand_ts(hour_lo, hour_hi, minutes=True):
        h = random.randint(hour_lo, hour_hi - 1)
        m = random.randint(0, 59) if minutes else 0
        return night_date.replace(hour=h, minute=m, second=random.randint(0, 59))

    # Baseline apps: small periodic keep-alive traffic all night
    baseline_apps = ["WhatsApp", "Play Services", "Weather"]
    for app in baseline_apps:
        n_conns = {"WhatsApp": 40, "Play Services": 60, "Weather": 10}[app]
        for _ in range(n_conns):
            ts = rand_ts(23, 24) if random.random() < 0.5 else rand_ts(0, 7)
            if ts.hour >= 7:
                ts = ts.replace(hour=random.randint(0, 6))
            dest = random.choice(APPS[app][1])
            rows.append(_conn_row(app, dest, ts,
                                  random.randint(200, 2000),          # sent
                                  random.randint(500, 12000)))        # received

    # Chrome: occasional activity early in the night (23:00-01:00)
    for _ in range(random.randint(3, 6)):
        ts = rand_ts(23, 24) if random.random() < 0.7 else rand_ts(0, 1)
        dest = random.choice(APPS["Chrome"][1])
        rows.append(_conn_row("Chrome", dest, ts,
                              random.randint(1000, 50000),
                              random.randint(5000, 300000)))

    # DNS queries for each app
    for app, (_, dests) in APPS.items():
        for domain, _ip in dests:
            for _ in range(random.randint(1, 4)):
                ts = rand_ts(23, 24) if random.random() < 0.5 else rand_ts(0, 7)
                if ts.hour >= 7:
                    ts = ts.replace(hour=random.randint(0, 6))
                rows.append(_dns_row(app, domain, ts))

    if burst:
        # Deliberate Instagram burst 02:14-02:19: ~18 MB received total
        n_burst_conns = 37
        per_conn_rcvd = 18 * 1024 * 1024 // n_burst_conns
        burst_start = night_date.replace(hour=2, minute=14)
        for i in range(n_burst_conns):
            ts = burst_start + timedelta(seconds=i * 7)
            dest = random.choice(APPS["Instagram"][1])
            rows.append(_conn_row("Instagram", dest, ts,
                                  random.randint(500, 5000),
                                  per_conn_rcvd + random.randint(-50000, 50000)))
        # Plus normal low-level Instagram keep-alives elsewhere in the night
        for _ in range(12):
            ts = rand_ts(23, 24) if random.random() < 0.5 else rand_ts(0, 2)
            if ts.hour == 2 and ts.minute >= 10 and ts.minute <= 25:
                ts = ts.replace(hour=1)
            if ts.hour >= 7:
                ts = ts.replace(hour=random.randint(0, 1))
            dest = random.choice(APPS["Instagram"][1])
            rows.append(_conn_row("Instagram", dest, ts,
                                  random.randint(200, 1500),
                                  random.randint(400, 9000)))

    return rows


def write_csv(path, rows):
    fieldnames = ["SrcIp", "SrcPort", "DstIp", "DstPort", "UID", "App", "PackageName",
                  "Proto", "Status", "Info", "BytesSent", "BytesRcvd", "PktsSent",
                  "PktsRcvd", "FirstSeen", "LastSeen"]
    random.shuffle(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # latest night = today, so the app lists it first
    latest = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    nights = [
        (latest - timedelta(days=2), False, "quiet baseline"),
        (latest - timedelta(days=1), False, "normal baseline"),
        (latest, True, "Instagram burst 02:14 + higher volume"),
    ]

    for night_date, burst, desc in nights:
        fname = f"night_{night_date.strftime('%Y%m%d')}.csv"
        rows = generate_night(night_date, burst)
        write_csv(os.path.join(OUTPUT_DIR, fname), rows)
        total = sum(r["BytesSent"] + r["BytesRcvd"] for r in rows)
        print(f"{fname}: {len(rows)} rows, {total / 1024 / 1024:.1f} MB overnight - {desc}")


if __name__ == "__main__":
    main()
