"""Cola de notificaciones (outbox): se encola dentro de la transacción de negocio y un worker la envía."""
import json
import logging
import os

import psycopg
from psycopg.rows import dict_row

from . import whatsapp

log = logging.getLogger("sgrs.notify")
MAX_ATTEMPTS = 5


def public_url(raffle_id) -> str:
    return f"{os.environ.get('SGRS_PUBLIC_URL', 'http://localhost:8000').rstrip('/')}/#/r/{raffle_id}"


def enqueue(conn, user_id, raffle_id, kind, ref_id, params):
    conn.execute(
        "INSERT INTO notifications (user_id, raffle_id, type, ref_id, payload) VALUES (%s,%s,%s,%s,%s::jsonb)"
        " ON CONFLICT (user_id, type, ref_id) DO NOTHING",
        (user_id, raffle_id, kind, ref_id, json.dumps({"params": [str(p) for p in params]})))


def enqueue_draw_reminders(conn) -> int:
    """Recordatorio único a quienes tienen boletas pagadas, 24 h antes de `draw_at`."""
    tz = os.environ.get("SGRS_TZ", "America/Bogota")
    url_base = os.environ.get("SGRS_PUBLIC_URL", "http://localhost:8000").rstrip("/") + "/#/r/"
    rows = conn.execute(
        "INSERT INTO notifications (user_id, raffle_id, type, ref_id, payload)"
        " SELECT DISTINCT t.owner_id, r.id, 'DRAW_REMINDER', r.id, jsonb_build_object('params', jsonb_build_array("
        "   r.title, to_char(r.draw_at AT TIME ZONE %s, 'DD/MM/YYYY HH24:MI'), %s || r.id::text))"
        " FROM raffles r JOIN tickets t ON t.raffle_id = r.id AND t.status = 'PAGADO' AND t.owner_id IS NOT NULL"
        " WHERE r.status IN ('OPEN','CLOSED') AND r.draw_at BETWEEN now() AND now() + interval '24 hours'"
        " ON CONFLICT (user_id, type, ref_id) DO NOTHING RETURNING id", (tz, url_base)).fetchall()
    return len(rows)


def _backoff(attempts: int) -> int:
    return 30 * 2 ** attempts  # 30 s, 1 min, 2 min, 4 min…


def process_one(conn, raffle_id=None) -> bool:
    """Envía una notificación pendiente (opcionalmente solo de una rifa). False si no hay nada que hacer."""
    row = conn.execute(
        "SELECT n.id, n.type, n.payload, n.attempts, u.phone_e164, u.notify_optout FROM notifications n"
        " JOIN users u ON u.id = n.user_id WHERE n.status='QUEUED' AND n.scheduled_at <= now()"
        " AND (%s::uuid IS NULL OR n.raffle_id = %s) ORDER BY n.id FOR UPDATE OF n SKIP LOCKED LIMIT 1",
        (raffle_id, raffle_id)).fetchone()
    if not row:
        return False
    if row["notify_optout"]:
        conn.execute("UPDATE notifications SET status='SKIPPED', last_error='baja voluntaria' WHERE id=%s", (row["id"],))
        return True
    if row["type"] not in whatsapp.TYPES:
        conn.execute("UPDATE notifications SET status='FAILED', last_error='tipo desconocido' WHERE id=%s", (row["id"],))
        return True
    res = whatsapp.send_template(row["phone_e164"], row["type"], row["payload"].get("params", []))
    if res.ok:
        conn.execute("UPDATE notifications SET status='SENT', provider_msg_id=%s, sent_at=now(), attempts=attempts+1,"
                     " last_error=NULL WHERE id=%s", (res.msg_id, row["id"]))
    elif res.retryable and row["attempts"] + 1 < MAX_ATTEMPTS:
        conn.execute("UPDATE notifications SET attempts=attempts+1, last_error=%s,"
                     " scheduled_at = now() + make_interval(secs => %s) WHERE id=%s",
                     (res.error, _backoff(row["attempts"]), row["id"]))
    else:
        log.error("notificación %s fallida: %s", row["id"], res.error)
        conn.execute("UPDATE notifications SET status='FAILED', attempts=attempts+1, last_error=%s WHERE id=%s",
                     (res.error, row["id"]))
    return True


def process_queue(dsn, limit=50, raffle_id=None) -> int:
    """Una transacción por mensaje: un fallo no revierte los ya enviados."""
    if not whatsapp.config():
        log.warning("WhatsApp no configurado: las notificaciones permanecen en cola")
        return 0
    sent = 0
    for _ in range(limit):
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            if not process_one(conn, raffle_id):
                break
        sent += 1
    return sent


def flush_after_commit(conn, limit=3, raffle_id=None) -> int:
    """Envía de inmediato (sin esperar al cron) lo que acaba de encolarse. Confirma antes la transacción
    actual para que el worker vea las filas nuevas; cualquier fallo queda en la cola para reintento."""
    if os.environ.get("SGRS_FLUSH_ON_COMMIT", "1") == "0" or not whatsapp.config():
        return 0
    conn.commit()
    try:
        from . import db
        return process_queue(db.DSN, limit, raffle_id)
    except Exception:
        log.exception("envío inmediato falló (queda en cola)")
        return 0
