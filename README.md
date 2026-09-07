# PCAPdroid Analyzer

**Privacy-first, offline network traffic analysis tool for PCAPdroid CSV exports.**

> OFFLINE MODE — No data leaves this device

## Features

- **CSV Import** — Drag & drop or browse for PCAPdroid CSV files
- **Overview Dashboard** — Total traffic, connections, apps, charts (traffic over time, by app, by protocol)
- **App Analysis** — Per-app statistics: bytes sent/received, connections, destinations, DNS count
- **App → Destination** — Click any app to see all domains/IPs it communicated with
- **Domain Analysis** — Global domain table with apps, connections, traffic
- **DNS Analysis** — DNS traffic identification, domain extraction, app→domain mapping
- **Privacy Metrics** — Apps contacting most domains, shared third-party domains, unidentified destinations
- **Timeline** — Traffic volume over time (hourly/daily), filterable by app/domain
- **Search & Filter** — Search by app, domain, IP, protocol, date range
- **100% Offline** — No analytics, no telemetry, no cloud sync

## Quick Start

### Prerequisites

- Python 3.10+

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Generate test data (optional)
python generate_test_data.py

# Start the server
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

### Open in Browser

Navigate to: http://127.0.0.1:8765

### Import Your Data

1. Click "Import" in the navigation
2. Drag & drop your PCAPdroid CSV file(s) or click to browse
3. View results in Dashboard, Apps, Domains, DNS, Privacy, Timeline, and Search pages

## Architecture

```
CSV upload → auto-detect parser → bulk INSERT → refresh aggregates → dashboard API → Chart.js render
```

### Tech Stack

- **Backend:** Python, FastAPI, SQLite
- **Frontend:** Vanilla HTML/CSS/JS, Chart.js
- **Database:** SQLite (WAL mode, materialized aggregates)

### Data Flow

```
CSV Import
    ↓
CSV Parser (robust, handles missing fields, duplicates, IPv6)
    ↓
SQLite Database (normalized connections + materialized stats)
    ↓
Analytics Engine (aggregated queries)
    ↓
REST API (15 endpoints, 6 routers)
    ↓
UI (Dashboard, Apps, Domains, DNS, Privacy, Timeline, Search)
```

### Database Schema

- **connections** — Raw parsed CSV rows with all fields
- **app_stats** — Materialized aggregates per app
- **domain_stats** — Materialized aggregates per domain
- **imports** — Import tracking (file, row count, timestamp)

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/import/csv` | Import a PCAPdroid CSV file |
| `GET /api/import/status` | Get import status and history |
| `GET /api/dashboard/stats` | Dashboard overview statistics |
| `GET /api/dashboard/timeline` | Timeline data for charting |
| `GET /api/apps/list` | List all apps with stats |
| `GET /api/apps/details` | Detailed app statistics |
| `GET /api/domains/list` | List all domains with stats |
| `GET /api/domains/details` | Detailed domain statistics |
| `GET /api/dns/analysis` | DNS traffic analysis |
| `GET /api/privacy/metrics` | Privacy-relevant metrics |
| `GET /api/search/connections` | Search and filter connections |
| `GET /api/search/timeline` | Filtered timeline data |

## Testing

A synthetic test dataset is included:

```bash
python generate_test_data.py
```

Generates 5,552 rows including:
- 15 apps with realistic traffic patterns
- 20 domains/IPs
- DNS traffic (port 53)
- TCP and UDP protocols
- IPv4 and IPv6 addresses
- Malformed rows (empty fields)
- Duplicate rows
- 24-hour recording period

## Privacy

This application is designed with privacy as a core principle:

- **No analytics or telemetry**
- **No cloud synchronization**
- **No external API calls**
- **All processing happens locally**
- **Imported CSVs are never uploaded**
- **Data stored in local SQLite database only**

## License

MIT
