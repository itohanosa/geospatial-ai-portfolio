from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.database.session import check_database

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Production-oriented API foundation for the GeoRiskOS multimodal "
        "geospatial risk intelligence platform."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@app.get("/", tags=["system"])
def root() -> dict[str, object]:
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
        "documentation": "/docs",
        "endpoints": ["/health", "/ready", "/version"],
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    """Liveness check: confirms that the API process is running."""

    return {
        "status": "healthy",
        "service": settings.app_name,
        "timestamp": utc_now(),
    }


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, object]:
    """Readiness check: confirms that PostgreSQL and PostGIS are available."""

    database_status = check_database()

    if not database_status["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "database": database_status,
                "timestamp": utc_now(),
            },
        )

    return {
        "status": "ready",
        "service": settings.app_name,
        "database": database_status,
        "timestamp": utc_now(),
    }


@app.get("/version", tags=["system"])
def version() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "timestamp": utc_now(),
    }
