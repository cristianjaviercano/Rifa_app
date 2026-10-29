"""Códigos cortos para entrar a una rifa (R…) o a la sala de un organizador (S…)."""
import re
import secrets

import psycopg

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I para evitar confusiones al dictarlos
CODE_RE = re.compile(r"^[RS][A-HJ-NP-Z2-9]{7}$")


def normalize(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def pretty(code: str) -> str:
    return f"{code[0]}-{code[1:]}"


def assign(conn, table: str, id_, prefix: str, column: str) -> str:
    """Asigna (una sola vez) un código único; reintenta si hay colisión. Devuelve el código vigente."""
    cur = conn.execute(f"SELECT {column} AS c FROM {table} WHERE id=%s", (id_,)).fetchone()
    if cur and cur["c"]:
        return cur["c"]
    for _ in range(8):
        code = prefix + "".join(secrets.choice(ALPHABET) for _ in range(7))
        try:
            with conn.transaction():
                row = conn.execute(f"UPDATE {table} SET {column}=%s WHERE id=%s AND {column} IS NULL RETURNING {column} AS c",
                                   (code, id_)).fetchone()
            if row:
                return row["c"]
            return conn.execute(f"SELECT {column} AS c FROM {table} WHERE id=%s", (id_,)).fetchone()["c"]
        except psycopg.errors.UniqueViolation:
            continue
    raise RuntimeError("no se pudo generar un código único")


def room_code(conn, user_id) -> str:
    return assign(conn, "users", user_id, "S", "room_code")


def share_code(conn, raffle_id) -> str:
    return assign(conn, "raffles", raffle_id, "R", "share_code")
