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
- **Overnight Analysis** — Per-night breakdown of app activity during sleep windows, burst detection, statistical baselines
- **Session Management** — Import history, per-session deletion, raw database and derived-analysis export
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
3. View results in Dashboard, Apps, Domains, DNS, Privacy, Timeline, Overnight, Search, and Sessions pages

### Configuration

The application can be configured via an optional environment variable:

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `PCAP_DB_DIR` | Directory where the SQLite database is stored | `data/` | No |

Example — store the database in a custom directory:

```bash
PCAP_DB_DIR=/custom/path python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

When unset, the database is created at `data/pcap_analyzer.db` relative to the working directory. The directory is auto-created on startup if it does not exist.

## Architecture

```
CSV upload → auto-detect parser → bulk INSERT → refresh aggregates → REST API → Chart.js render
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
Analytics Engine (aggregated queries, overnight analysis, search)
    ↓
REST API (legacy /api/* routes + centralized /api/v1/* boundary)
    ↓
UI (Dashboard, Apps, Domains, DNS, Privacy, Timeline, Search, Overnight, Sessions)
```

### Database Schema

- **connections** — Raw parsed CSV rows with all fields
- **app_stats** — Materialized aggregates per app
- **domain_stats** — Materialized aggregates per domain
- **imports** — Import tracking (file, row count, timestamp)
- **settings** — User settings (e.g., sleep window start/end times)

## API Endpoints

The public API boundary is `/api/v1/`. Existing endpoints under `/api/` remain available for backwards compatibility during migration.

### `/api/v1/` — Public API Boundary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Namespace health check |
| GET | `/api/v1/dashboard/stats` | Dashboard overview statistics |
| POST | `/api/v1/import/csv` | Import a PCAPdroid CSV file |
| GET | `/api/v1/apps/list` | List all apps with statistics (paginated, sortable) |

### Legacy `/api/*` Endpoints

#### Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/import/csv` | Import a PCAPdroid CSV file |
| GET | `/api/import/status` | Get import status and history |

#### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/stats` | Dashboard overview statistics |
| GET | `/api/dashboard/timeline` | Timeline data for charting |

#### Apps

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/apps/list` | List all apps with stats |
| GET | `/api/apps/details` | Detailed app statistics |

#### Domains

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/domains/list` | List all domains with stats |
| GET | `/api/domains/details` | Detailed domain statistics |
| POST | `/api/domains/refresh` | Refresh domain statistics from raw data |

#### DNS

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dns/analysis` | DNS traffic analysis |

#### Privacy

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/privacy/metrics` | Privacy-relevant metrics |

#### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search/connections` | Search and filter connections |
| GET | `/api/search/timeline` | Filtered timeline data |

#### Overnight

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/overnight/config` | Get/set sleep window configuration |
| GET | `/api/overnight/nights` | List candidate nights with data presence flags |
| GET | `/api/overnight/night/{night}` | Full overnight picture (summary, apps, bursts, insights, baselines) |
| GET | `/api/overnight/night/{night}/timeline` | Night timeline with fixed time buckets |
| GET | `/api/overnight/night/{night}/apps` | Per-app overnight breakdown |
| GET | `/api/overnight/night/{night}/apps/{app}/destinations` | Destinations contacted by one app overnight |
| GET | `/api/overnight/night/{night}/apps/{app}/connections` | Raw connections drill-down for an app |
| GET | `/api/overnight/night/{night}/bursts` | Statistical activity burst detection |
| GET | `/api/overnight/compare` | Multi-night side-by-side comparison |
| GET | `/api/overnight/baseline/{app_name}` | Statistical baseline for one app across all nights |
| GET | `/api/overnight/insights/{night}` | Factual privacy observations for one night |

#### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sessions` | List recording sessions with metadata |
| DELETE | `/api/sessions/{id}` | Delete one session and its raw connections |
| DELETE | `/api/sessions?confirm=DELETE ALL` | Delete all imported data |
| GET | `/api/sessions/export/database` | Download raw SQLite database snapshot |
| GET | `/api/sessions/export/analysis` | Download derived aggregates as JSON |

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

```bash
python generate_multinight_test_data.py
```

Generates multi-night CSV files in `test_data/night_YYYYMMDD.csv`.

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
