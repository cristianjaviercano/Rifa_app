"""Salas (portafolios): cada organizador tiene una sala con un código; nadie ve las rifas de otro
a menos que reciba el código de la sala o el enlace/código de una rifa concreta."""
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import codes
from .db import get_conn
from .raffles import _owned_raffle, err
from .security import current_user, optional_user
from .views import COUNTS, PUBLIC

router = APIRouter(prefix="/api/v1")


class RoomIn(BaseModel):
    room_name: str = Field(min_length=1, max_length=60)


class VisibilityIn(BaseModel):
    visibility: str = Field(pattern="^(PORTFOLIO|LINK)$")


def _remember(conn, user, owner_id):
    if user and user["id"] != owner_id:
        conn.execute("INSERT INTO memberships (user_id, owner_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user["id"], owner_id))


def _room_raffles(conn, owner_id):
    return conn.execute(
        f"SELECT {PUBLIC} r.visibility,{COUNTS} FROM raffles r WHERE r.owner_id=%s AND r.visibility='PORTFOLIO'"
        " AND r.status IN ('OPEN','CLOSED','DRAWN') ORDER BY (r.status='OPEN') DESC, r.sales_close_at", (owner_id,)).fetchall()


@router.get("/rooms/{code}")
def get_room(code: str, user=Depends(optional_user), conn=Depends(get_conn)):
    owner = conn.execute("SELECT id, name, room_name, room_code FROM users WHERE room_code=%s", (codes.normalize(code),)).fetchone()
    if not owner:
        raise err(404, "ROOM_NOT_FOUND")
    _remember(conn, user, owner["id"])
    rows = _room_raffles(conn, owner["id"])
    for r in rows:
        r.pop("owner_id", None)
    return {"room_code": owner["room_code"], "room_name": owner["room_name"] or f"Sala de {owner['name']}",
            "owner_name": owner["name"], "is_owner": bool(user and user["id"] == owner["id"]), "raffles": rows}


@router.get("/resolve/{code}")
def resolve(code: str, conn=Depends(get_conn)):
    """Un único campo «tengo un código»: devuelve a dónde llevar al usuario."""
    c = codes.normalize(code)
    if not codes.CODE_RE.match(c):
        raise err(404, "CODE_NOT_FOUND")
    if c[0] == "S":
        row = conn.execute("SELECT room_code FROM users WHERE room_code=%s", (c,)).fetchone()
        if row:
            return {"type": "room", "code": row["room_code"]}
    else:
        row = conn.execute("SELECT id FROM raffles WHERE share_code=%s AND status <> 'DRAFT'", (c,)).fetchone()
        if row:
            return {"type": "raffle", "id": row["id"]}
    raise err(404, "CODE_NOT_FOUND")


@router.get("/me/room")
def my_room(user=Depends(current_user), conn=Depends(get_conn)):
    code = codes.room_code(conn, user["id"])
    u = conn.execute("SELECT name, room_name FROM users WHERE id=%s", (user["id"],)).fetchone()
    rows = conn.execute(f"SELECT {PUBLIC} r.visibility, r.share_code,{COUNTS} FROM raffles r WHERE r.owner_id=%s"
                        " ORDER BY r.created_at DESC", (user["id"],)).fetchall()
    for r in rows:
        if r["status"] != "DRAFT" and not r["share_code"]:
            r["share_code"] = codes.share_code(conn, r["id"])
    return {"room_code": code, "room_name": u["room_name"] or f"Sala de {u['name']}", "has_custom_name": bool(u["room_name"]), "raffles": rows}


@router.post("/me/room")
def rename_room(b: RoomIn, user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("UPDATE users SET room_name=%s WHERE id=%s", (b.room_name.strip(), user["id"]))
    return {"room_name": b.room_name.strip()}


@router.get("/me/rooms")
def my_memberships(user=Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        "SELECT u.room_code, coalesce(u.room_name, 'Sala de ' || u.name) AS room_name, u.name AS owner_name,"
        " (SELECT count(*) FROM raffles r WHERE r.owner_id=u.id AND r.visibility='PORTFOLIO' AND r.status='OPEN') AS open_raffles"
        " FROM memberships m JOIN users u ON u.id=m.owner_id WHERE m.user_id=%s AND u.room_code IS NOT NULL"
        " ORDER BY m.created_at DESC LIMIT 50", (user["id"],)).fetchall()


@router.post("/raffles/{rid}/visibility")
def set_visibility(rid: UUID, b: VisibilityIn, user=Depends(current_user), conn=Depends(get_conn)):
    _owned_raffle(conn, rid, user)
    conn.execute("UPDATE raffles SET visibility=%s WHERE id=%s", (b.visibility, rid))
    return {"id": rid, "visibility": b.visibility}
