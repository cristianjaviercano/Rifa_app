"""Worker: expira reservas vencidas y cierra rifas cuya fecha_cierre_ventas ya pasó."""
import logging
import time

import psycopg
from psycopg.rows import dict_row

from .db import DSN
from .main import expire_holds
from .raffles import auto_close

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sgrs.worker")


def tick():
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        e = expire_holds(conn)
        c = auto_close(conn)
    if e or c:
        log.info("expiradas=%s cerradas=%s", e, c)


if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception:
            log.exception("tick falló")
        time.sleep(30)
