"""
SQLAlchemy engine/session setup. SQLite by default (see Config), but
DATABASE_URL can point at Postgres/MySQL without code changes elsewhere.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from app.core.config import Config

connect_args = {"check_same_thread": False} if Config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(Config.DATABASE_URL, connect_args=connect_args)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))

Base = declarative_base()


def init_db():
    from app.models import document  # noqa: F401 - ensure models are registered
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
