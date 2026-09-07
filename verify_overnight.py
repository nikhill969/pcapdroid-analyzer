"""Mathematical verification of overnight statistics (Phase 2 acceptance).

Recomputes every overnight figure directly from the raw connections rows
with an independent Python calculation and compares against the values
returned by the application's SQL engine and API.

Run:  python verify_overnight.py
"""

import json
import sqlite3
import sys
import urllib.request
from datetime import date, datetime, timedelta

BASE = "http://127.0.0.1:8765"
DB = "data/pcap_analyzer.db"

failures = []
checks = 0


def check(label, expected, actual, tol=0):
    global checks
    checks += 1
    ok = (expected == actual) if tol == 0 else abs(expected - actual) <= tol
    if ok:
        print(f"  PASS  {label}: {expected}")
    else:
        print(f"  FAIL  {label}: expected {expected}, got {actual}")
        failures.append(label)


def api(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def raw_rows(db=DB):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM connections")]
    conn.close()
    return rows


def ts(v):
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")


def in_window(row, night, start_hm, end_hm):
    """Independent window logic: 23:00 on `night` -> 07:00 next day."""
    s_h, s_m = map(int, start_hm.split(":"))
    e_h, e_m = map(int, end_hm.split(":"))
    start = datetime.combine(night, datetime.min.time()).replace(hour=s_h, minute=s_m)
    end = datetime.combine(night, datetime.min.time()).replace(hour=e_h, minute=e_m)
    if end <= start:
        end += timedelta(days=1)
    return start <= ts(row["first_seen"]) < end


def main():
    print("=" * 64)
    print("PHASE 2 MATH VERIFICATION - overnight statistics")
    print("=" * 64)

    rows = raw_rows()
    print(f"\nRaw connections in DB: {len(rows)}")

    # Known CSV totals per import (what the generator wrote to disk)
    import csv, glob, os
    csv_totals = {}
    for f in glob.glob("test_data/night_*.csv"):
        with open(f, encoding="utf-8") as fh:
            r = list(csv.DictReader(fh))
        total = sum(int(x["BytesSent"]) + int(x["BytesRcvd"]) for x in r)
        csv_totals[os.path.basename(f)] = (len(r), total)
    print("CSV files on disk (rows, total bytes):")
    for k, (n, b) in sorted(csv_totals.items()):
        print(f"  {k}: {n} rows, {b:,} bytes ({b/1024/1024:.1f} MB)")

    # ---- 1. Import metadata matches CSVs (recording sessions) ----
    print("\n[1] Recording sessions match CSV files")
    sessions = api("/api/sessions")["sessions"]
    for s in sessions:
        fn = s["filename"]
        if fn in csv_totals:
            n, b = csv_totals[fn]
            check(f"{fn} row_count", n, s["row_count"])
            check(f"{fn} total_traffic", b, s["total_traffic_bytes"])

    # ---- 2. Night summary vs independent recomputation ----
    print("\n[2] Night summaries (API) vs independent recomputation")
    nights = sorted({r["first_seen"][:10] for r in rows})
    cfg = api("/api/overnight/config")
    ss, se = cfg["sleep_start"], cfg["sleep_end"]
    print(f"  sleep window: {ss} -> {se}")

    per_night = {}
    for n in nights:
        d = datetime.strptime(n, "%Y-%m-%d").date()
        # window spans midnight when end <= start: rows from d 23:00 -> d+1 07:00
        if se <= ss:
            win_night = d - timedelta(days=1)  # a window starting on d-1 covers d 00:00-07:00
        else:
            win_night = d
        sel = [r for r in rows if in_window(r, win_night, ss, se)]
        sent = sum(r["bytes_sent"] for r in sel)
        rcvd = sum(r["bytes_received"] for r in sel)
        per_night[win_night.strftime("%Y-%m-%d")] = {
            "rows": len(sel), "sent": sent, "rcvd": rcvd, "total": sent + rcvd,
            "apps": len({r["app_name"] for r in sel}),
            "domains": len({r["domain"] for r in sel if r["domain"]}),
            "dests": len({r["dst_ip"] for r in sel}),
            "dns": sum(1 for r in sel if r["is_dns"]),
        }

    detail = api("/api/overnight/night/" + max(per_night))
    for night, exp in per_night.items():
        s = api(f"/api/overnight/night/{night}")["summary"]
        check(f"{night} sent", exp["sent"], s["bytes_sent"])
        check(f"{night} received", exp["rcvd"], s["bytes_received"])
        check(f"{night} total", exp["total"], s["total_traffic"])
        check(f"{night} connections", exp["rows"], s["connections"])
        check(f"{night} unique_apps", exp["apps"], s["unique_apps"])
        check(f"{night} unique_domains", exp["domains"], s["unique_domains"])
        check(f"{night} unique_destinations", exp["dests"], s["unique_destinations"])
        check(f"{night} dns_requests", exp["dns"], s["dns_requests"])

    # ---- 3. Per-app breakdown for the latest night ----
    print("\n[3] Per-app breakdown (latest night)")
    latest = max(per_night)
    exp_apps = {}
    # per_night keys are already window-start nights: window = latest 23:00 -> latest+1 07:00
    win_d = date.fromisoformat(latest)
    for r in rows:
        if in_window(r, win_d, ss, se):
            a = exp_apps.setdefault(r["app_name"], {"sent": 0, "rcvd": 0, "n": 0, "domains": set()})
            a["sent"] += r["bytes_sent"]
            a["rcvd"] += r["bytes_received"]
            a["n"] += 1
            if r["domain"]:
                a["domains"].add(r["domain"])
    api_apps = {a["app_name"]: a for a in detail["apps"]["apps"]}
    for app, exp in exp_apps.items():
        got = api_apps.get(app)
        if got is None:
            check(f"{app} present in API", True, False)
            continue
        check(f"{app} sent", exp["sent"], got["bytes_sent"])
        check(f"{app} received", exp["rcvd"], got["bytes_received"])
        check(f"{app} total", exp["sent"] + exp["rcvd"], got["total_traffic"])
        check(f"{app} connections", exp["n"], got["connections"])
        check(f"{app} unique_domains", len(exp["domains"]), got["unique_domains"])
    # sorted by total traffic desc
    totals = [a["total_traffic"] for a in detail["apps"]["apps"]]
    check("apps sorted by traffic desc", totals, sorted(totals, reverse=True))

    # ---- 4. Bursts: the deliberate Instagram burst 02:14-02:19 ----
    print("\n[4] Activity bursts (latest night)")
    bursts = api(f"/api/overnight/night/{latest}/bursts?bucket_minutes=5")["bursts"]
    ig = [b for b in bursts if b["app_name"] == "Instagram"]
    if ig:
        biggest = max(ig, key=lambda b: b["traffic"])
        print(f"  largest Instagram burst: {biggest['start']} traffic={biggest['traffic']:,} "
              f"conns={biggest['connections']} ratio={biggest['ratio_to_mean']}")
        check("burst in 02:10-02:20 window", True, 1 if "T02:1" in biggest["start"] else 0)
        labels = {b["label"] for b in bursts}
        neutral = labels <= {"Activity burst", "High traffic period", "Unusually high activity"}
        check("burst labels neutral", True, 1 if neutral else 0)
    else:
        check("Instagram burst detected", True, 0)

    # ---- 5. Multi-night comparison math ----
    print("\n[5] Multi-night comparison")
    all_nights = sorted(per_night)
    if len(all_nights) >= 2:
        comp = api("/api/overnight/compare?nights=" + ",".join(all_nights))
        complete = [n for n in comp["nights"] if n["connections"] > 0]
        exp_avg_traffic = sum(n["total_traffic"] for n in complete) / len(complete)
        check("avg total_traffic", round(exp_avg_traffic), comp["average"]["total_traffic"])
        exp_avg_conns = sum(n["connections"] for n in complete) / len(complete)
        check("avg connections", round(exp_avg_conns), comp["average"]["connections"])
        last = complete[-1]
        others = complete[:-1]
        exp_pct = round((last["total_traffic"] - sum(o["total_traffic"] for o in others) / len(others))
                        / (sum(o["total_traffic"] for o in others) / len(others)) * 100, 1)
        got_pct = [n["vs_avg_total_traffic_pct"] for n in comp["nights"] if n["night"] == last["night"]][0]
        check("last night vs-avg %", exp_pct, got_pct)
        print(f"  nights: {[ (n['night'], n['total_traffic']) for n in complete ]}")
        print(f"  avg traffic {exp_avg_traffic:,.0f}, last night {last['total_traffic']:,} ({exp_pct:+.1f}%)")

    # ---- 6. Baseline: independent median/MAD for Instagram ----
    print("\n[6] Overnight baseline (Instagram)")
    base = api("/api/overnight/baseline/Instagram")
    if base.get("baseline_available"):
        nights_hist = base["nights"]
        prior = [n["total_traffic"] for n in nights_hist[:-1]]
        last = nights_hist[-1]["total_traffic"]
        prior_sorted = sorted(prior)
        m = len(prior_sorted)
        median = prior_sorted[m // 2] if m % 2 else (prior_sorted[m // 2 - 1] + prior_sorted[m // 2]) / 2
        devs = sorted(abs(v - median) for v in prior)
        mad = devs[m // 2] if m % 2 else (devs[m // 2 - 1] + devs[m // 2]) / 2
        upper = median + 3 * 1.4826 * mad
        lower = max(median - 3 * 1.4826 * mad, 0)
        exp_status = ("Higher than baseline" if last > upper
                      else "Lower than baseline" if last < lower else "Normal")
        check("baseline median", round(median), base["median"])
        check("baseline MAD", round(mad, 1), base["mad"])
        check("baseline threshold_upper", round(upper), base["threshold_upper"])
        check("baseline status", exp_status, base["status"])
        print(f"  median={median:,.0f} MAD={mad:,.1f} last={last:,} -> {exp_status}")
    else:
        print(f"  baseline not available: {base.get('message')}")

    # ---- 7. Drill-down traceability: app totals = sum of raw rows ----
    print("\n[7] Drill-down traceability")
    app = "Instagram"
    page = api(f"/api/overnight/night/{latest}/apps/{app}/connections?per_page=200")
    raw_sel = [r for r in rows if r["app_name"] == app
               and in_window(r, date.fromisoformat(latest), ss, se)]
    check("drill-down total", len(raw_sel), page["total"])
    s_api = sum(c["bytes_sent"] + c["bytes_received"] for c in page["connections"])
    s_raw = sum(r["bytes_sent"] + r["bytes_received"] for r in raw_sel)
    check("drill-down bytes sum matches raw", s_raw, s_api)

    # ---- 8. Destination analysis ----
    print("\n[8] Destination analysis (Instagram)")
    dests = api(f"/api/overnight/night/{latest}/apps/Instagram/destinations")["destinations"]
    exp_dest = {}
    for r in raw_sel:
        key = r["domain"] if r["domain"] else r["dst_ip"]
        e = exp_dest.setdefault(key, {"n": 0, "t": 0})
        e["n"] += 1
        e["t"] += r["bytes_sent"] + r["bytes_received"]
    got_dest = {d["destination"]: d for d in dests}
    for key, e in exp_dest.items():
        g = got_dest.get(key)
        if g is None:
            check(f"dest {key} present", True, False)
            continue
        check(f"dest {key} connections", e["n"], g["connections"])
        check(f"dest {key} traffic", e["t"], g["total_traffic"])

    print("\n" + "=" * 64)
    print(f"RESULT: {checks - len(failures)}/{checks} checks passed")
    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL OVERNIGHT MATH VERIFIED")


if __name__ == "__main__":
    main()
