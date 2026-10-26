import logging
import os
import re

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import create_engine, pool, text

from app.db.models import Base

logging.basicConfig(level=logging.INFO)
target_metadata = Base.metadata
extension_tables: set[str] = set()

# Operator CLI safety, not a DB privilege boundary. Programmatic Alembic callers
# must implement the same policy; production rollback uses a new restored DB.
command = getattr(context.config.cmd_opts, "cmd", ()) or ()
if command and getattr(command[0], "__name__", "") == "downgrade":
    if context.get_x_argument(as_dictionary=True).get(
        "allow_test_downgrade"
    ) != "true" or not re.fullmatch(
        r"(?:business_ai_test_|ba003_test_)[a-f0-9]{32}", os.getenv("PGDATABASE", "")
    ):
        raise RuntimeError(
            "Downgrade refused: only explicit disposable UUID test databases allowed"
        )


def include_name(
    name: str | None, type_: NameFilterType, parent_names: NameFilterParentNames
) -> bool:
    # Exclude extension members, not all tables missing from ORM metadata:
    # an unexpected application table must still be reported as schema drift.
    return not (type_ == "table" and name in extension_tables)


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
        # All application migrations/ORM tables are in public. PostgreSQL reflection
        # otherwise includes visible TIGER relations from an inherited search_path.
        connection.execute(text("SET search_path TO public"))
        connection.dialect.default_schema_name = "public"
        extension_tables.update(
            connection.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "JOIN pg_depend d ON d.classid='pg_class'::regclass "
                    "AND d.objid=c.oid AND d.deptype='e' "
                    "JOIN pg_extension e ON e.oid=d.refobjid "
                    "WHERE n.nspname='public'"
                )
            ).scalars()
        )
        connection.commit()  # Do not wrap Alembic's transaction in an implicit read.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
