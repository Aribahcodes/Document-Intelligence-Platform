"""
SQLAlchemy engine/session setup. SQLite by default (see Config), but
DATABASE_URL can point at Postgres/MySQL without code changes elsewhere.
"""
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

connect_args = {"check_same_thread": False} if Config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(Config.DATABASE_URL, connect_args=connect_args)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))

Base = declarative_base()


def init_db():
    """
    Create tables if they don't exist. Called once at app startup.

    Defensively tolerates a "table already exists" race: SQLAlchemy's
    create_all() checks-then-creates non-atomically, so if two app
    processes ever start at nearly the same instant against the same
    database file (e.g. during a platform's deploy-transition restart),
    one can lose a race to the other. That's a harmless outcome - the
    table exists either way - so we log it and continue rather than
    crash the whole worker over it.
    """
    from app.models import document  # noqa: F401 - ensure models are registered
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        if "already exists" in str(exc).lower():
            logger.warning("init_db(): table(s) already existed (likely a concurrent-startup race) - continuing")
        else:
            raise


def get_session():
    return SessionLocal()
