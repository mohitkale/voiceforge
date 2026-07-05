"""SQLite engine/session setup via SQLModel."""

from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)

# check_same_thread=False is safe here: FastAPI's default threadpool may hand
# requests to different threads, but we only ever use short-lived sessions
# (one per request) and SQLite itself serializes writes.
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
