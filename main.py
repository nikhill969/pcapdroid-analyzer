"""PCAPdroid CSV Network Traffic Analyzer - Main Application"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.routers import import_router, dashboard_router, apps_router
from app.routers import domains_router, dns_router, privacy_router, search_router
from app.routers import overnight_router, session_router

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="PCAPdroid Analyzer",
    description="Privacy-first, offline network traffic analysis tool",
    version="1.0.0",
)

# Include routers
app.include_router(import_router.router)
app.include_router(dashboard_router.router)
app.include_router(apps_router.router)
app.include_router(domains_router.router)
app.include_router(dns_router.router)
app.include_router(privacy_router.router)
app.include_router(search_router.router)
app.include_router(overnight_router.router)
app.include_router(session_router.router)

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    """Serve the main dashboard."""
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(os.path.dirname(__file__), "templates", "index.html"))


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "offline": True}
