"""SQLAlchemy engine / session setup (SQLite by default)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# check_same_thread=False so the scheduler thread and request threads can share
# the SQLite connection pool.
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    from . import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


# Lightweight additive migrations: SQLAlchemy's create_all won't ALTER existing
# tables, so add any new nullable columns by hand. Idempotent and SQLite-only.
_ADDED_COLUMNS = {
    "recommendations": {
        "conviction": "FLOAT",
        "rank_score": "FLOAT",
        "regime": "VARCHAR(16)",
    },
}


def _migrate_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            if not existing:
                continue  # table not created yet (shouldn't happen post create_all)
            for name, decl in cols.items():
                if name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                    )
