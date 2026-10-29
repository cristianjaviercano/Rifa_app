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


def verify_chain(conn, last=None) -> bool:
    """Recalcula la cadena de hashes; False si algún registro fue alterado.
    last=N verifica solo los N más recientes (la ventana arranca confiando en el enlace de su primer registro)."""
    if last:
        rows = conn.execute("SELECT * FROM (SELECT * FROM audit_log ORDER BY id DESC LIMIT %s) t ORDER BY id", (last,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    prev = rows[0]["prev_hash"] if rows and last else ""
    for r in rows:
        body = json.dumps([str(r["actor_id"]), r["action"], r["entity"], str(r["entity_id"]), r["diff"]],
                          sort_keys=True, default=str)
        if r["prev_hash"] != prev or r["hash"] != hashlib.sha256((prev + body).encode()).hexdigest():
            return False
        prev = r["hash"]
    return True
