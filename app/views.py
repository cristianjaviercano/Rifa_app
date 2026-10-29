"""Lecturas para la interfaz: listados públicos, mis compras y cola de revisión."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from . import codes
from .db import get_conn
from .raffles import _owned_raffle, err
from .security import current_user, optional_user

router = APIRouter(prefix="/api/v1")

COUNTS = (" (SELECT count(*) FROM tickets t WHERE t.raffle_id=r.id) AS tickets_total,"
          " (SELECT count(*) FROM tickets t WHERE t.raffle_id=r.id AND t.status IN ('PAGADO','GANADOR')) AS tickets_sold,"
          " (SELECT count(*) FROM tickets t WHERE t.raffle_id=r.id AND t.status='CONGELADO') AS tickets_held")
PUBLIC = ("r.id, r.title, r.ticket_price, r.currency, r.numbers_per_ticket, r.total_numbers, r.sales_close_at,"
          " r.draw_at, r.draw_method, r.status, r.owner_id,")


@router.get("/me")
def me(user=Depends(current_user), conn=Depends(get_conn)):
    return conn.execute("SELECT id, name, role, phone_e164 AS phone FROM users WHERE id=%s", (user["id"],)).fetchone()


@router.get("/raffles/{rid}")
def detail(rid: UUID, conn=Depends(get_conn), user=Depends(optional_user)):
    r = conn.execute(f"SELECT {PUBLIC} r.terms_md, r.hold_minutes, r.payment_accounts, r.lottery_name, r.visibility, r.share_code,"
                     f" u.name AS owner_name, u.room_code, u.room_name,{COUNTS}"
                     " FROM raffles r JOIN users u ON u.id=r.owner_id WHERE r.id=%s", (rid,)).fetchone()
    if not r or (r["status"] == "DRAFT" and not (user and user["id"] == r["owner_id"])):
        raise err(404, "RAFFLE_NOT_FOUND")
    r["is_owner"] = bool(user and (user["id"] == r["owner_id"] or user["role"] == "SUPERUSER"))
    if r["visibility"] == "PORTFOLIO":
        if user and user["id"] != r["owner_id"]:  # recordar la sala para que el comprador pueda volver
            conn.execute("INSERT INTO memberships (user_id, owner_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user["id"], r["owner_id"]))
        r["room_name"] = r["room_name"] or f"Sala de {r['owner_name']}"
    else:  # rifa independiente: no se revela la sala
        r["room_code"] = None; r["room_name"] = None
    r["prizes"] = conn.execute("SELECT id, kind, rank, description FROM prizes WHERE raffle_id=%s ORDER BY rank", (rid,)).fetchall()
    if r["status"] == "DRAWN":
        r["draw"] = conn.execute("SELECT method, winning_number, source_url, executed_at FROM draws WHERE raffle_id=%s", (rid,)).fetchone()
        r["winners"] = conn.execute(
            "SELECT p.description, p.kind, (SELECT array_agg(n.number ORDER BY n.number) FROM ticket_numbers n"
            " WHERE n.ticket_id=w.ticket_id) AS numbers FROM winners w JOIN prizes p ON p.id=w.prize_id"
            " WHERE w.raffle_id=%s ORDER BY p.rank", (rid,)).fetchall()
    if r["is_owner"] and not r["share_code"] and r["status"] != "DRAFT":
        r["share_code"] = codes.share_code(conn, rid)
    if not r["is_owner"]:
        r.pop("owner_id")
    return r


@router.get("/me/raffles")
def my_raffles(user=Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(f"SELECT {PUBLIC} r.visibility, r.share_code,{COUNTS} FROM raffles r WHERE r.owner_id=%s ORDER BY r.created_at DESC",
                        (user["id"],)).fetchall()


TX_SELECT = ("SELECT pt.id, pt.raffle_id, pt.status, pt.platform, pt.external_ref, pt.proof_id, pt.amount_declared,"
             " pt.expires_at, pt.created_at, pt.reject_reason, r.title AS raffle_title, r.ticket_price, r.total_numbers,"
             " u.name AS buyer_name, u.phone_e164 AS buyer_phone,"
             " (SELECT json_agg(json_build_object('serial', t.serial, 'numbers', (SELECT array_agg(n.number ORDER BY n.number)"
             "   FROM ticket_numbers n WHERE n.ticket_id=t.id)) ORDER BY t.serial) FROM transaction_tickets tt"
             "   JOIN tickets t ON t.id=tt.ticket_id WHERE tt.transaction_id=pt.id) AS tickets"
             " FROM payment_transactions pt JOIN raffles r ON r.id=pt.raffle_id JOIN users u ON u.id=pt.buyer_id")


@router.get("/me/transactions")
def my_transactions(user=Depends(current_user), conn=Depends(get_conn)):
    rows = conn.execute(TX_SELECT + " WHERE pt.buyer_id=%s ORDER BY pt.created_at DESC LIMIT 100", (user["id"],)).fetchall()
    for x in rows:
        x.pop("buyer_phone"); x.pop("buyer_name")
    return rows


@router.get("/raffles/{rid}/transactions")
def raffle_transactions(rid: UUID, status: Optional[str] = None, user=Depends(current_user), conn=Depends(get_conn)):
    _owned_raffle(conn, rid, user, lock=False)
    return conn.execute(TX_SELECT + " WHERE pt.raffle_id=%s AND (%s::text IS NULL OR pt.status::text=%s)"
                        " ORDER BY pt.created_at", (rid, status, status)).fetchall()
