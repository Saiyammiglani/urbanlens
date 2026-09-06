"""SQLAlchemy engine/session setup. Postgres in docker, SQLite fallback locally."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
elif ":6543" in settings.DATABASE_URL:
    # Transaction-mode pooler (free tier): disable prepared statements —
    # pgbouncer tx mode can't cache them per-session, and psycopg caching
    # collides across multiplexed server sessions (DuplicatePreparedStatement).
    # prepare_threshold=None disables client-side preparing entirely.
    engine = create_engine(
        settings.DATABASE_URL, future=True,
        connect_args={"prepare_threshold": None},
        poolclass=NullPool,
    )
else:
    # session-mode pooler / direct: normal pool with idle-connection recycling
    engine = create_engine(
        settings.DATABASE_URL, future=True,
        pool_pre_ping=True, pool_recycle=300,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)
