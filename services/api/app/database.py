from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_options(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _upgrade_legacy_schema()


def _upgrade_legacy_schema() -> None:
    """Small additive migration bridge for existing local MVP databases.

    Production deployments should use the versioned Alembic migration included
    with the deployment configuration; this bridge keeps users' current SQLite
    demo data readable while the project moves to that migration path.
    """

    inspector = inspect(engine)
    if "knowledge_chunks" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
        with engine.begin() as connection:
            if "embedding_json" not in columns:
                connection.execute(
                    text("ALTER TABLE knowledge_chunks ADD COLUMN embedding_json TEXT")
                )
            if "embedding_model" not in columns:
                connection.execute(
                    text("ALTER TABLE knowledge_chunks ADD COLUMN embedding_model VARCHAR(120)")
                )
    inspector = inspect(engine)
    if "voice_profiles" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("voice_profiles")}
        if "sample_media_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE voice_profiles ADD COLUMN sample_media_id VARCHAR(32)")
                )
