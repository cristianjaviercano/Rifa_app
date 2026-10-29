import hashlib
import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .audit import write_audit
from .db import get_conn
from .notify import enqueue, public_url
from .security import current_user, optional_user

router = APIRouter(prefix="/api/v1")


def err(http, code, **extra):
    return HTTPException(http, {"code": code, **extra})


class PrizeIn(BaseModel):
    kind: str = Field(pattern="^(MAIN|SECO|CONSECUTIVE)$")
    rank: int = 1
    description: str
    offset: int = 0  # 0 = número ganador; +1/-1 = secos consecutivos


class RaffleIn(BaseModel):
    title: str
    terms_md: str
    total_numbers: int = Field(gt=0)
    numbers_per_ticket: int = Field(gt=0)
    ticket_price: Decimal = Field(gt=0)
    sales_close_at: datetime
    draw_at: datetime
    draw_method: str = Field(pattern="^(INTERNAL_CSPRNG|EXTERNAL_LOTTERY)$")
    lottery_name: Optional[str] = None
    hold_minutes: int = Field(default=120, gt=0)
    payment_accounts: dict[str, str] = {}
    prizes: list[PrizeIn] = Field(min_length=1)


class DrawIn(BaseModel):
    winning_number: Optional[int] = None  # solo método externo
    source_url: Optional[str] = None


def _owned_raffle(conn, rid, user, lock=True):
    r = conn.execute("SELECT * FROM raffles WHERE id=%s" + (" FOR UPDATE" if lock else ""), (rid,)).fetchone()
    if not r:
        raise err(404, "RAFFLE_NOT_FOUND")
    if user is not None and user["role"] != "SUPERUSER" and r["owner_id"] != user["id"]:
        raise err(403, "FORBIDDEN")
    return r


@router.post("/raffles", status_code=201)
def create_raffle(b: RaffleIn, user=Depends(current_user), conn=Depends(get_conn)):
    if b.total_numbers % b.numbers_per_ticket:
        raise err(422, "NUMBERS_NOT_DIVISIBLE")
    if b.sales_close_at >= b.draw_at:
        raise err(422, "DATES_INVALID")
    if b.draw_method == "EXTERNAL_LOTTERY" and not b.lottery_name:
        raise err(422, "LOTTERY_NAME_REQUIRED")
    r = conn.execute(
        "INSERT INTO raffles (owner_id,title,terms_md,total_numbers,numbers_per_ticket,ticket_price,"
        " sales_close_at,draw_at,draw_method,lottery_name,hold_minutes,payment_accounts) VALUES"
        " (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id",
        (user["id"], b.title, b.terms_md, b.total_numbers, b.numbers_per_ticket, b.ticket_price,
         b.sales_close_at, b.draw_at, b.draw_method, b.lottery_name, b.hold_minutes,
         json.dumps(b.payment_accounts))).fetchone()
    for p in b.prizes:
        conn.execute("INSERT INTO prizes (raffle_id,kind,rank,description,rule) VALUES (%s,%s,%s,%s,%s::jsonb)",
                     (r["id"], p.kind, p.rank, p.description, json.dumps({"offset": p.offset})))
    write_audit(conn, user["id"], "CREATE", "raffle", r["id"], {"title": b.title})
    return {"id": r["id"], "status": "DRAFT"}


@router.post("/raffles/{rid}/publish")
def publish(rid: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    r = _owned_raffle(conn, rid, user)
    if r["status"] != "DRAFT":
        raise err(409, "INVALID_STATE", current=r["status"])
    n, npt = r["total_numbers"], r["numbers_per_ticket"]
    conn.execute("INSERT INTO tickets (raffle_id, serial) SELECT %s, g FROM generate_series(1,%s) g", (rid, n // npt))
    conn.execute(
        "INSERT INTO ticket_numbers (raffle_id, number, ticket_id)"
        " SELECT t.raffle_id, (t.serial-1)*%s + k, t.id FROM tickets t, generate_series(0,%s) k WHERE t.raffle_id=%s",
        (npt, npt - 1, rid))
    conn.execute("UPDATE raffles SET status='OPEN' WHERE id=%s", (rid,))
    write_audit(conn, user["id"], "PUBLISH", "raffle", rid, {"tickets": n // npt})
    return {"id": rid, "status": "OPEN", "tickets": n // npt}


@router.get("/raffles/{rid}/tickets")
def list_tickets(rid: UUID, status: Optional[str] = None, conn=Depends(get_conn), user=Depends(optional_user)):
    rows = conn.execute(
        "SELECT t.id, t.serial, t.status, (t.owner_id IS NOT NULL AND t.owner_id = %s) AS mine,"
        " array_agg(n.number ORDER BY n.number) AS numbers FROM tickets t"
        " JOIN ticket_numbers n ON n.ticket_id=t.id WHERE t.raffle_id=%s AND (%s::text IS NULL OR t.status::text=%s)"
        " GROUP BY t.id ORDER BY t.serial", (user["id"] if user else None, rid, status, status)).fetchall()
    return rows


def close_raffle(conn, rid, actor_id):
    """Cierra ventas y emite el arqueo contable (inmutable)."""
    conn.execute("UPDATE raffles SET status='CLOSED' WHERE id=%s", (rid,))
    sold = conn.execute("SELECT count(*) c FROM tickets WHERE raffle_id=%s AND status='PAGADO'", (rid,)).fetchone()["c"]
    by = conn.execute(
        "SELECT pt.platform::text AS platform, pt.status::text AS status, count(tt.ticket_id) AS tickets,"
        " coalesce(sum(tt.unit_price),0) AS amount FROM payment_transactions pt"
        " JOIN transaction_tickets tt ON tt.transaction_id=pt.id WHERE pt.raffle_id=%s"
        " GROUP BY 1,2 ORDER BY 1,2", (rid,)).fetchall()
    validated = sum((x["amount"] for x in by if x["status"] == "APPROVED"), Decimal(0))
    pending = sum((x["amount"] for x in by if x["status"] == "PENDING"), Decimal(0))
    snap = {"sold_tickets": sold, "by_platform_status": [{**x, "amount": str(x["amount"])} for x in by]}
    h = hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()
    conn.execute(
        "INSERT INTO accounting_closures (raffle_id,sold_count,validated_amount,pending_amount,snapshot,hash)"
        " VALUES (%s,%s,%s,%s,%s::jsonb,%s)", (rid, sold, validated, pending, json.dumps(snap), h))
    write_audit(conn, actor_id, "CLOSE", "raffle", rid, {"sold": sold, "validated": str(validated), "hash": h})


@router.post("/raffles/{rid}/close")
def close(rid: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    r = _owned_raffle(conn, rid, user)
    if r["status"] != "OPEN":
        raise err(409, "INVALID_STATE", current=r["status"])
    if conn.execute("SELECT now() < %s AS early", (r["sales_close_at"],)).fetchone()["early"]:
        raise err(409, "BEFORE_CLOSING_DATE")
    close_raffle(conn, rid, user["id"])
    return accounting(rid, conn, user)


def auto_close(conn) -> int:
    """Scheduler: cierra rifas OPEN cuya fecha_cierre_ventas ya pasó."""
    ids = conn.execute("SELECT id FROM raffles WHERE status='OPEN' AND sales_close_at <= now()"
                       " FOR UPDATE SKIP LOCKED").fetchall()
    for r in ids:
        close_raffle(conn, r["id"], None)
    return len(ids)


@router.get("/raffles/{rid}/accounting")
def accounting(rid: UUID, conn=Depends(get_conn), user=Depends(current_user)):
    _owned_raffle(conn, rid, user, lock=False)
    a = conn.execute("SELECT * FROM accounting_closures WHERE raffle_id=%s", (rid,)).fetchone()
    if not a:
        raise err(404, "NOT_CLOSED")
    return a


@router.post("/raffles/{rid}/draw")
def draw(rid: UUID, body: DrawIn, user=Depends(current_user), conn=Depends(get_conn)):
    r = _owned_raffle(conn, rid, user)
    if r["status"] != "CLOSED":
        raise err(409, "INVALID_STATE", current=r["status"])
    if conn.execute("SELECT 1 FROM payment_transactions WHERE raffle_id=%s AND status='PENDING'", (rid,)).fetchone():
        raise err(409, "PENDING_TX_REMAIN")  # el administrador debe resolver todo antes del sorteo
    total = r["total_numbers"]
    if r["draw_method"] == "EXTERNAL_LOTTERY":
        if body.winning_number is None or not body.source_url:
            raise err(422, "EXTERNAL_RESULT_REQUIRED")
        if not 0 <= body.winning_number < total:
            raise err(422, "NUMBER_OUT_OF_RANGE", max=total - 1)
        win = body.winning_number
    else:
        sold = [x["number"] for x in conn.execute(
            "SELECT n.number FROM ticket_numbers n JOIN tickets t ON t.id=n.ticket_id"
            " WHERE n.raffle_id=%s AND t.status='PAGADO'", (rid,))]
        if not sold:
            raise err(409, "NO_SOLD_TICKETS")
        win = sold[secrets.randbelow(len(sold))]  # CSPRNG
    conn.execute("INSERT INTO draws (raffle_id,method,winning_number,source_url,executed_by) VALUES (%s,%s,%s,%s,%s)",
                 (rid, r["draw_method"], win, body.source_url, user["id"]))
    result = []
    for p in conn.execute("SELECT * FROM prizes WHERE raffle_id=%s ORDER BY rank", (rid,)).fetchall():
        num = (win + int(p["rule"].get("offset", 0))) % total
        t = conn.execute(
            "SELECT t.id, t.owner_id FROM ticket_numbers n JOIN tickets t ON t.id=n.ticket_id"
            " WHERE n.raffle_id=%s AND n.number=%s AND t.status IN ('PAGADO','GANADOR')", (rid, num)).fetchone()
        item = {"prize_id": p["id"], "kind": p["kind"], "description": p["description"], "number": num, "winner_ticket": t["id"] if t else None}
        if t:
            conn.execute("UPDATE tickets SET status='GANADOR' WHERE id=%s", (t["id"],))
            conn.execute("INSERT INTO winners VALUES (%s,%s,%s)", (rid, p["id"], t["id"]))
            enqueue(conn, t["owner_id"], rid, "WINNER", p["id"],
                    [r["title"], p["description"], str(num).zfill(len(str(total - 1)))])
        result.append(item)
    for b in conn.execute("SELECT DISTINCT owner_id FROM tickets WHERE raffle_id=%s AND status IN ('PAGADO','GANADOR')"
                          " AND owner_id IS NOT NULL AND owner_id NOT IN"
                          " (SELECT user_id FROM notifications WHERE raffle_id=%s AND type='WINNER')", (rid, rid)).fetchall():
        enqueue(conn, b["owner_id"], rid, "DRAW_FINISHED", rid,
                [r["title"], str(win).zfill(len(str(total - 1))), public_url(rid)])
    conn.execute("UPDATE raffles SET status='DRAWN' WHERE id=%s", (rid,))
    write_audit(conn, user["id"], "DRAW", "raffle", rid,
                {"method": r["draw_method"], "winning_number": win, "source_url": body.source_url})
    return {"winning_number": win, "method": r["draw_method"], "prizes": result}
