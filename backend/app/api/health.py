"""
api/health.py - Health check endpoint.

Always returns HTTP 200 so that:
  - The frontend health-check never shows "API Offline" just because the
    database had a transient hiccup on startup.
  - Render's HTTP health-check probe keeps the container alive even when
    Supabase is temporarily unreachable (the container itself is healthy).

The JSON body carries a "database" field so dashboards / logs can distinguish
a fully-healthy response from a degraded-but-running one without treating the
API as down.
"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(request: Request):
    """
    Returns HTTP 200 in all cases where the API process is running.

    JSON body:
      status   : "ok" | "degraded"
      database : "connected" | "unavailable"
      message  : human-readable summary
    """
    db_ready = getattr(request.app.state, "db_ready", lambda: True)()
    db_error = getattr(request.app.state, "db_error", lambda: "")()

    if db_ready:
        return {
            "status": "ok",
            "database": "connected",
            "message": "DataLens AI API is healthy",
        }

    # API process is running fine — only the DB is temporarily unavailable.
    # Return 200 so the frontend shows "API Online" and Render does not restart.
    return {
        "status": "degraded",
        "database": "unavailable",
        "message": "DataLens AI API is running. Database connection is temporarily unavailable.",
        "detail": db_error or "Database init failed.",
    }
