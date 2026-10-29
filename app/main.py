from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .audit import write_audit
from .db import get_conn
from .images import router as images_router
from .notify import enqueue, public_url
from .ops import router as ops_router
from .auth import router as auth_router
from .raffles import router as raffles_router
from .uploads import router as uploads_router
from .webhooks import router as webhooks_router
from .views import router as views_router
from .rooms import router as rooms_router
from .security import current_user
from .share import router as share_router

app = FastAPI(title="SGRS API", version="1.0")
app.include_router(raffles_router)
app.include_router(auth_router)
app.include_router(uploads_router)
app.include_router(images_router)
app.include_router(views_router)
app.include_router(rooms_router)
app.include_router(webhooks_router)
app.include_router(ops_router)
app.include_router(share_router)


class ReservationIn(BaseModel):
    ticket_ids: list[UUID] = Field(min_length=1, max_length=50)
    platform: str
    external_ref: Optional[str] = Field(default=None, max_length=64)
    proof_id: Optional[UUID] = None
    amount_declared: Decimal


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _err(http, code, **extra):
    return HTTPException(http, {"code": code, **extra})


def _tx_response(conn, tx):
    rows = conn.execute(
        "SELECT t.id, t.status FROM tickets t JOIN transaction_tickets tt ON tt.ticket_id=t.id"
        " WHERE tt.transaction_id=%s ORDER BY t.serial", (tx["id"],)).fetchall()
    return {"transaction_id": tx["id"], "status": tx["status"], "expires_at": tx["expires_at"],
            "tickets": [{"id": r["id"], "status": r["status"]} for r in rows]}


@app.post("/api/v1/raffles/{raffle_id}/reservations", status_code=201)
def reserve(raffle_id: UUID, body: ReservationIn, user=Depends(current_user),
            conn=Depends(get_conn), idempotency_key: str = Header(...)):
    # Idempotencia: misma clave del mismo comprador devuelve la transacción original.
    prev = conn.execute("SELECT * FROM payment_transactions WHERE buyer_id=%s AND idempotency_key=%s",
                        (user["id"], idempotency_key)).fetchone()
    if prev:
        return _tx_response(conn, prev)

    raffle = conn.execute("SELECT * FROM raffles WHERE id=%s", (raffle_id,)).fetchone()
    if not raffle:
        raise _err(404, "RAFFLE_NOT_FOUND")
    now = conn.execute("SELECT now() AS n").fetchone()["n"]
    if raffle["status"] != "OPEN" or now >= raffle["sales_close_at"]:
        raise _err(423, "SALES_CLOSED")
    if body.platform not in ("NEQUI", "DAVIPLATA", "BREVE", "PAYPAL", "OTRO"):
        raise _err(422, "PLATFORM_INVALID")
    if not (body.external_ref or body.proof_id):
        raise _err(422, "PROOF_REQUIRED")
    ids = list(dict.fromkeys(body.ticket_ids))
    expected = raffle["ticket_price"] * len(ids)
    if body.amount_declared != expected:
        raise _err(422, "AMOUNT_MISMATCH", expected=str(expected))

    proof = None
    if body.proof_id:
        proof = conn.execute("SELECT * FROM proofs WHERE id=%s AND uploader_id=%s",
                             (body.proof_id, user["id"])).fetchone()
        if not proof:
            raise _err(422, "PROOF_NOT_FOUND")
        if conn.execute(  # el mismo archivo no puede respaldar dos pagos activos de la misma rifa
                "SELECT 1 FROM payment_transactions pt JOIN proofs p ON p.id=pt.proof_id"
                " WHERE pt.raffle_id=%s AND p.sha256=%s AND pt.status IN ('PENDING','APPROVED')",
                (raffle_id, proof["sha256"])).fetchone():
            raise _err(409, "DUPLICATE_PROOF")

    if body.external_ref and conn.execute(
            "SELECT 1 FROM payment_transactions WHERE raffle_id=%s AND platform=%s AND external_ref=%s"
            " AND status IN ('PENDING','APPROVED')",
            (raffle_id, body.platform, body.external_ref)).fetchone():
        raise _err(409, "DUPLICATE_EXTERNAL_REF")

    # Congelamiento atómico: UPDATE condicional (sin carreras).
    frozen = conn.execute(
        "UPDATE tickets SET status='CONGELADO', owner_id=%s,"
        " hold_expires_at = now() + make_interval(mins => %s)"
        " WHERE raffle_id=%s AND id = ANY(%s) AND status='DISPONIBLE' RETURNING id",
        (user["id"], raffle["hold_minutes"], raffle_id, ids)).fetchall()
    if len(frozen) != len(ids):
        conn.rollback()
        got = {r["id"] for r in frozen}
        raise _err(409, "TICKET_UNAVAILABLE", conflicts=[str(i) for i in ids if i not in got])

    tx = conn.execute(
        "INSERT INTO payment_transactions (raffle_id,buyer_id,platform,external_ref,proof_id,proof_sha256,"
        " amount_declared,expires_at,idempotency_key)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s, now() + make_interval(mins => %s), %s) RETURNING *",
        (raffle_id, user["id"], body.platform, body.external_ref,
         proof["id"] if proof else None, proof["sha256"] if proof else None,
         body.amount_declared, raffle["hold_minutes"], idempotency_key)).fetchone()
    conn.cursor().executemany(
        "INSERT INTO transaction_tickets VALUES (%s,%s,%s)",
        [(tx["id"], i, raffle["ticket_price"]) for i in ids])
    write_audit(conn, user["id"], "RESERVE", "payment_transaction", tx["id"], {"tickets": ids})
    return _tx_response(conn, tx)


def _load_tx_for_review(conn, tid, user):
    """Bloquea la transacción y verifica que el usuario administre la rifa."""
    tx = conn.execute("SELECT * FROM payment_transactions WHERE id=%s FOR UPDATE", (tid,)).fetchone()
    if not tx:
        raise _err(404, "TX_NOT_FOUND")
    owner = conn.execute("SELECT owner_id FROM raffles WHERE id=%s", (tx["raffle_id"],)).fetchone()["owner_id"]
    if user["role"] != "SUPERUSER" and owner != user["id"]:
        raise _err(403, "FORBIDDEN")
    if tx["status"] != "PENDING":
        raise _err(409, "INVALID_STATE", status=tx["status"])
    return tx


@app.post("/api/v1/transactions/{tid}/approve")
def approve(tid: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    tx = _load_tx_for_review(conn, tid, user)
    if conn.execute("SELECT now() >= %s AS e", (tx["expires_at"],)).fetchone()["e"]:
        raise _err(410, "EXPIRED")
    conn.execute(
        "UPDATE tickets SET status='PAGADO', hold_expires_at=NULL WHERE id IN"
        " (SELECT ticket_id FROM transaction_tickets WHERE transaction_id=%s)", (tid,))
    tx = conn.execute(
        "UPDATE payment_transactions SET status='APPROVED', reviewed_by=%s, reviewed_at=now()"
        " WHERE id=%s RETURNING *", (user["id"], tid)).fetchone()
    # Outbox: se confirma o revierte junto con la aprobación.
    info = conn.execute(
        "SELECT r.title, (SELECT string_agg(lpad(n.number::text, length((r.total_numbers-1)::text), '0'), ', ' ORDER BY n.number)"
        " FROM transaction_tickets tt JOIN ticket_numbers n ON n.ticket_id = tt.ticket_id WHERE tt.transaction_id = %s) AS nums"
        " FROM raffles r WHERE r.id = %s", (tid, tx["raffle_id"])).fetchone()
    enqueue(conn, tx["buyer_id"], tx["raffle_id"], "PAYMENT_APPROVED", tid,
            [info["title"], info["nums"], public_url(tx["raffle_id"])])
    write_audit(conn, user["id"], "APPROVE", "payment_transaction", tid, {})
    return _tx_response(conn, tx)


@app.post("/api/v1/transactions/{tid}/reject")
def reject(tid: UUID, body: RejectIn, user=Depends(current_user), conn=Depends(get_conn)):
    tx = _load_tx_for_review(conn, tid, user)
    release_tickets(conn, tid)
    tx = conn.execute(
        "UPDATE payment_transactions SET status='REJECTED', reject_reason=%s, reviewed_by=%s,"
        " reviewed_at=now() WHERE id=%s RETURNING *", (body.reason, user["id"], tid)).fetchone()
    write_audit(conn, user["id"], "REJECT", "payment_transaction", tid, {"reason": body.reason})
    return _tx_response(conn, tx)


def release_tickets(conn, tid):
    conn.execute(
        "UPDATE tickets SET status='DISPONIBLE', owner_id=NULL, hold_expires_at=NULL WHERE id IN"
        " (SELECT ticket_id FROM transaction_tickets WHERE transaction_id=%s)", (tid,))


def expire_holds(conn) -> int:
    """Job periódico: vence reservas PENDING caducadas. Seguro ante ejecución concurrente."""
    rows = conn.execute(
        "SELECT id FROM payment_transactions WHERE status='PENDING' AND expires_at <= now()"
        " FOR UPDATE SKIP LOCKED").fetchall()
    for r in rows:
        release_tickets(conn, r["id"])
        conn.execute("UPDATE payment_transactions SET status='EXPIRED' WHERE id=%s", (r["id"],))
        write_audit(conn, None, "EXPIRE", "payment_transaction", r["id"], {})
    return len(rows)


# --- Interfaz web (PWA estática) y cabeceras de seguridad -------------------------------------
import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles

CSP = ("default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
    if request.url.path in ("/", "/sw.js", "/index.html", "/manifest.webmanifest"):
        resp.headers["Cache-Control"] = "no-cache"  # el service worker versiona el resto
    return resp


WEB = Path(os.environ.get("SGRS_WEB_DIR", Path(__file__).resolve().parent.parent / "public"))
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")  # al final: la API tiene prioridad
