from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
