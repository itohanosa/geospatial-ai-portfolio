from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

settings = get_settings()

engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)


def check_database() -> dict[str, Any]:
    """Confirm PostgreSQL and PostGIS are reachable."""

    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        PostGIS_Version() AS postgis_version
                    """
                )
            ).mappings().one()

        return {
            "ready": True,
            "database_name": row["database_name"],
            "database_user": row["database_user"],
            "postgis_version": row["postgis_version"],
        }
    except SQLAlchemyError as exc:
        return {
            "ready": False,
            "error": str(exc),
        }
