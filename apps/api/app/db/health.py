import psycopg


def check_postgis() -> str:
    """Check the configured database, including the required PostGIS extension."""
    with psycopg.connect(connect_timeout=3, options="-c statement_timeout=3000") as connection:
        row = connection.execute("SELECT PostGIS_Version()").fetchone()
    if row is None or not row[0]:
        raise psycopg.OperationalError("PostGIS version is unavailable")
    return str(row[0])
