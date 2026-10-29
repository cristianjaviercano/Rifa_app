"""Worker: expira reservas, cierra rifas vencidas, programa recordatorios y envía notificaciones."""
import logging
import time

import psycopg
from psycopg.rows import dict_row

from .db import DSN
from .main import expire_holds
from .notify import enqueue_draw_reminders, process_queue
from .raffles import auto_close

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sgrs.worker")


def tick():
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        e = expire_holds(conn)
        c = auto_close(conn)
        r = enqueue_draw_reminders(conn)
    n = process_queue(DSN)
    if e or c or r or n:
        log.info("expiradas=%s cerradas=%s recordatorios=%s enviadas=%s", e, c, r, n)


if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception:
            log.exception("tick falló")
        time.sleep(30)
