import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bcn_housing.db")
_engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure_sqlite_engine(target_engine: Engine) -> None:
    if target_engine.dialect.name != "sqlite":
        return

    @event.listens_for(target_engine, "connect")
    def enable_sqlite_integrity(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


configure_sqlite_engine(engine)


class Base(DeclarativeBase):
    pass


def initialize_database() -> None:
    from bcn_housing import models  # noqa: F401

    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            version = connection.execute(text("PRAGMA user_version")).scalar_one()
            if version > 1:
                raise RuntimeError(f"Database schema version {version} is newer than this application")
        Base.metadata.create_all(bind=connection)
        if connection.dialect.name == "sqlite":
            connection.execute(text("PRAGMA user_version = 1"))
    if engine.dialect.name == "sqlite" and engine.url.database not in (None, "", ":memory:"):
        database_path = Path(engine.url.database)
        if database_path.is_file():
            os.chmod(database_path, 0o600)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
