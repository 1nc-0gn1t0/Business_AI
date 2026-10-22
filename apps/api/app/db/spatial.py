from typing import Any

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Geometry(UserDefinedType[str]):
    """Small PostGIS type for SQL-only geometry operations, including Alembic reflection."""

    cache_ok = True

    def __init__(self, kind: str = "POINT", srid: int = 4326):
        self.kind = kind.upper()
        self.srid = int(srid)

    def get_col_spec(self, **kwargs: Any) -> str:
        if self.kind not in {"POINT", "MULTIPOLYGON"} or self.srid != 4326:
            raise ValueError("Unsupported geometry type")
        return f"geometry({self.kind},{self.srid})"


ischema_names.setdefault("geometry", Geometry)
