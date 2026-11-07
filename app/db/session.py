import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

# Attempt to configure the production-grade PostgreSQL connection pool
# (pool_size=20, max_overflow=80 to handle up to 100 concurrent connections).
# Falls back to an in-memory SQLite engine if DBAPI drivers are not installed in the local environment.
try:
    engine = create_engine(
        settings.sync_database_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        echo=settings.DEBUG,
        connect_args={"connect_timeout": 3},
    )
except Exception as exc:
    logger.warning(
        "PostgreSQL DBAPI driver not detected (%s). Falling back to SQLite for local development/testing.",
        exc,
    )
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a scoped database session.
    Guarantees proper teardown upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
