"""
Database engine and session factory.

Uses SQLite by default (path from DATABASE_URL env var, defaults to /data/reviq.db).
run_migrations() applies additive ALTER TABLE statements idempotently on startup.
"""
import os
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/reviq.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def run_migrations():
    """Apply additive schema changes to existing databases."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE inclusioncriterion ADD COLUMN short_label VARCHAR",
        "ALTER TABLE exclusioncriterion ADD COLUMN short_label VARCHAR",
    ]
    with Session(engine) as session:
        for stmt in migrations:
            try:
                session.exec(text(stmt))
                session.commit()
            except Exception:
                session.rollback()


def get_session():
    with Session(engine) as session:
        yield session
