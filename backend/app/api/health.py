"""
api/health.py — Health check endpoint.

Separated from main.py so that as the project grows,
each feature area has its own router file.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """
    Returns the current health status of the API.

    Use this endpoint to confirm the server is reachable
    (e.g., from a load balancer, Docker health check, or CI pipeline).
    """
    return {
        "status": "ok",
        "message": "DataLens AI API is healthy",
    }
