import os
import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("SGRS_DSN", "postgresql://postgres@localhost:5433/sgrs")


def get_conn():
    """Una conexión por petición; commit al terminar, rollback ante excepción."""
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        yield conn
