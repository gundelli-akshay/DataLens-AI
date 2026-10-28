"""
api/health.py - Health check endpoint.

Separated from main.py so that as the project grows,
each feature area has its own router file.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(request: Request):
    """
    Returns the current health status of the API and its database connection.

    HTTP 200  - API is up; database initialised successfully.
    HTTP 503  - API is up but database is not yet reachable.
                Render/load-balancer health checks will see this as unhealthy
                and restart the container, rather than routing traffic to a
                broken instance.
    """
    db_ready = getattr(request.app.state, "db_ready", lambda: True)()
    db_error = getattr(request.app.state, "db_error", lambda: "")()

    if db_ready:
        return {
            "status": "ok",
            "database": "connected",
            "message": "DataLens AI API is healthy",
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "database": "unavailable",
            "message": "DataLens AI API is running but the database is not reachable.",
            "detail": db_error or "Database init failed.",
        },
    )
