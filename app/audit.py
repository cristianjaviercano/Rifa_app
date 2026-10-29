import hashlib
import json


def write_audit(conn, actor_id, action, entity, entity_id, diff):
    """Inserta en audit_log encadenando el hash con el registro previo."""
    conn.execute("LOCK TABLE audit_log IN SHARE ROW EXCLUSIVE MODE")
    prev = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = prev["hash"] if prev else ""
    body = json.dumps([str(actor_id), action, entity, str(entity_id), diff],
                      sort_keys=True, default=str)
    h = hashlib.sha256((prev_hash + body).encode()).hexdigest()
    conn.execute(
        "INSERT INTO audit_log (actor_id, action, entity, entity_id, diff, prev_hash, hash)"
        " VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)",
        (actor_id, action, entity, entity_id, json.dumps(diff, default=str), prev_hash, h))
