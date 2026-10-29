"""Simulación de un sorteo ficticio de extremo a extremo (usa la API real y PostgreSQL).

Uso:  SGRS_DSN=postgresql://... python -m scripts.simulate [--buyers 25] [--seed 1] [--method INTERNAL_CSPRNG|EXTERNAL_LOTTERY]
"""
import argparse
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.audit import verify_chain
from app.main import app, expire_holds
from app.security import issue_token

PLATFORMS = ["NEQUI", "DAVIPLATA", "BREVE", "PAYPAL"]


def run(dsn, buyers=25, seed=1, method="INTERNAL_CSPRNG", total=100, per_ticket=2, price=10000):
    rnd = random.Random(seed)
    cli = TestClient(app)
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as db:
        def mkuser(name):
            return db.execute("INSERT INTO users (phone_e164,name,phone_verified_at) VALUES (%s,%s,now())"
                              " RETURNING id", ("+57" + uuid.uuid4().hex[:9], name)).fetchone()["id"]

        def hdr(uid, key=None):
            h = {"Authorization": f"Bearer {issue_token(uid, 'USER')}"}
            return {**h, "Idempotency-Key": key or str(uuid.uuid4())}

        admin = mkuser("admin")
        now = datetime.now(timezone.utc)
        r = cli.post("/api/v1/raffles", headers=hdr(admin), json={
            "title": "Rifa ficticia", "terms_md": "Términos de prueba", "total_numbers": total,
            "numbers_per_ticket": per_ticket, "ticket_price": price,
            "sales_close_at": (now + timedelta(hours=6)).isoformat(),
            "draw_at": (now + timedelta(days=1)).isoformat(), "draw_method": method,
            "lottery_name": "Lotería de prueba" if method == "EXTERNAL_LOTTERY" else None,
            "prizes": [{"kind": "MAIN", "rank": 1, "description": "Moto", "offset": 0},
                       {"kind": "SECO", "rank": 2, "description": "Seco +1", "offset": 1},
                       {"kind": "CONSECUTIVE", "rank": 3, "description": "Consecutivo -1", "offset": -1}]})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert cli.post(f"/api/v1/raffles/{rid}/publish", headers=hdr(admin)).status_code == 200
        tickets = cli.get(f"/api/v1/raffles/{rid}/tickets").json()
        free = [t["id"] for t in tickets]

        stats = {"reservas": 0, "aprobadas": 0, "rechazadas": 0, "expiradas": 0, "conflictos": 0}
        txs = []
        for i in range(buyers):
            b = mkuser(f"comprador{i}")
            pick = rnd.sample(tickets, k=min(len(tickets), rnd.randint(1, 3)))  # puede chocar con otros
            ids = [t["id"] for t in pick]
            res = cli.post(f"/api/v1/raffles/{rid}/reservations", headers=hdr(b), json={
                "ticket_ids": ids, "platform": rnd.choice(PLATFORMS), "external_ref": f"REF{seed}-{i}",
                "amount_declared": price * len(ids)})
            if res.status_code == 201:
                stats["reservas"] += 1
                txs.append(res.json()["transaction_id"])
            else:
                assert res.status_code == 409, res.text
                stats["conflictos"] += 1

        fates = ["approve"] * 8 + ["reject"] + ["expire"]
        for tid in txs:
            f = rnd.choice(fates)
            if f == "approve":
                assert cli.post(f"/api/v1/transactions/{tid}/approve", headers=hdr(admin)).status_code == 200
                stats["aprobadas"] += 1
            elif f == "reject":
                assert cli.post(f"/api/v1/transactions/{tid}/reject", headers=hdr(admin),
                                json={"reason": "comprobante ilegible"}).status_code == 200
                stats["rechazadas"] += 1
            else:
                db.execute("UPDATE payment_transactions SET expires_at=now()-interval '1 minute' WHERE id=%s", (tid,))
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            stats["expiradas"] = expire_holds(c)

        # Viaje en el tiempo: vence la fecha de cierre de ventas.
        db.execute("UPDATE raffles SET sales_close_at=now()-interval '1 minute' WHERE id=%s", (rid,))
        late = cli.post(f"/api/v1/raffles/{rid}/reservations", headers=hdr(mkuser("tarde")), json={
            "ticket_ids": [free[0]], "platform": "NEQUI", "external_ref": "TARDE", "amount_declared": price})
        assert late.status_code == 423
        assert cli.post(f"/api/v1/raffles/{rid}/close", headers=hdr(admin)).status_code == 200
        acct = cli.get(f"/api/v1/raffles/{rid}/accounting", headers=hdr(admin)).json()

        body = ({"winning_number": rnd.randrange(total), "source_url": "https://loteria.example/resultado/123"}
                if method == "EXTERNAL_LOTTERY" else {})
        d = cli.post(f"/api/v1/raffles/{rid}/draw", headers=hdr(admin), json=body)
        assert d.status_code == 200, d.text
        draw = d.json()

        # Invariantes
        q = lambda sql, *a: db.execute(sql, a).fetchall()
        assert not q("SELECT 1 FROM tickets WHERE raffle_id=%s AND status='CONGELADO'", rid), "quedó CONGELADO"
        paid = q("SELECT count(*) c FROM tickets WHERE raffle_id=%s AND status IN ('PAGADO','GANADOR')", rid)[0]["c"]
        assert paid == acct["sold_count"]
        assert acct["validated_amount"] == price * paid
        assert acct["pending_amount"] == 0
        assert verify_chain(db), "cadena de auditoría rota"
        stats["boletas_pagadas"] = paid
        stats["recaudo_validado"] = str(acct["validated_amount"])
        stats["notificaciones"] = {x["type"]: x["c"] for x in q(
            "SELECT type, count(*) c FROM notifications WHERE raffle_id=%s GROUP BY type", rid)}
        stats["sorteo"] = draw
        return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--buyers", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--method", default="INTERNAL_CSPRNG")
    a = ap.parse_args()
    import json
    print(json.dumps(run(os.environ["SGRS_DSN"], a.buyers, a.seed, a.method), indent=2, default=str))
