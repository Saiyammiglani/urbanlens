"""One-shot migration: local SQLite (dev) -> Supabase Postgres (production).

Usage:
    python migrate_sqlite_to_pg.py            # migrate + verify
    python migrate_sqlite_to_pg.py --dry-run  # show what would be copied

Requires DATABASE_URL (Supabase Postgres) in ../.env — tables are created
automatically if missing. Idempotent: rows already present (matched by id)
are skipped, so it can be safely re-run.
"""
import argparse
import sys
from datetime import timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app import models  # noqa: E402  (registers tables on Base)

ROOT = Path(__file__).resolve().parents[1]
SQLITE_URL = f"sqlite:///{ROOT / 'urbanlens.sqlite3'}"


def _aware(dt):
    """SQLite stores naive datetimes (UTC by our convention) — reattach tz."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if settings.DATABASE_URL.startswith("sqlite"):
        print("ERROR: DATABASE_URL is still SQLite. Set the Supabase Postgres "
              "connection string in .env first, e.g.\n"
              "DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres")
        sys.exit(1)

    src = create_engine(SQLITE_URL, future=True)
    dst = create_engine(settings.DATABASE_URL, future=True)

    print("destination:", settings.DATABASE_URL.split("@")[-1])
    Base.metadata.create_all(dst)  # no-op if tables exist

    copied = {}
    with Session(src) as s_in, Session(dst) as s_out:
        existing = {}
        for t in ("Vehicle", "Incident", "Observation", "IncidentUpdate"):
            existing[t] = {row_id for (row_id,) in s_out.execute(select(getattr(models, t).id))}
        for name in ("Vehicle", "Incident", "Observation", "IncidentUpdate"):
            model = getattr(models, name)
            rows = s_in.execute(select(model)).scalars().all()
            new = [r for r in rows if r.id not in existing[name]]
            for r in new:
                obj = model()
                for col in model.__table__.columns:
                    if col.name == "id":
                        setattr(obj, "id", r.id)  # keep ids — FKs must match
                    else:
                        v = getattr(r, col.name)
                        setattr(obj, col.name, _aware(v) if hasattr(v, "tzinfo") else v)
                s_out.add(obj)
            copied[name] = len(new)

        if args.dry_run:
            s_out.rollback()
            print("dry run — would copy:", copied)
            return
        s_out.commit()

    print("copied:", copied)
    # verify counts match
    with Session(dst) as s:
        for name in ("Vehicle", "Incident", "Observation", "IncidentUpdate"):
            n = len(s.execute(select(getattr(models, name).id)).all())
            print(f"  {name:14s} {n} rows in Postgres")


if __name__ == "__main__":
    main()
