import logging

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import create_engine, pool

from app.db.models import Base

logging.basicConfig(level=logging.INFO)
target_metadata = Base.metadata


def include_name(
    name: str | None, type_: NameFilterType, parent_names: NameFilterParentNames
) -> bool:
    # PostGIS owns this table. Autogeneration must never suggest dropping it.
    return not (type_ == "table" and name == "spatial_ref_sys")


if context.is_offline_mode():
    context.configure(
        url="postgresql+psycopg://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # libpq reads PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD, as in the health check.
    # Credentials never enter alembic.ini or an interpolated SQLAlchemy URL.
    engine = create_engine(
        "postgresql+psycopg://", poolclass=pool.NullPool, connect_args={"connect_timeout": 5}
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
