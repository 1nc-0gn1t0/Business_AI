import logging
from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        "postgresql+psycopg://",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
    )


def get_session() -> Iterator[Session]:
    try:
        with Session(get_engine(), expire_on_commit=False) as session, session.begin():
            yield session
    except SQLAlchemyError:
        logger.warning("Conversation database operation failed")
        raise HTTPException(503, detail={"code": "database_unavailable"}) from None


def get_session_factory() -> sessionmaker[Session]:
    # No Session/connection is opened by this dependency. Each message phase owns one.
    return sessionmaker(get_engine(), expire_on_commit=False)
