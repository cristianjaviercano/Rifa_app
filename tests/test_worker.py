from tests.conftest import dsn
import psycopg
from psycopg.rows import dict_row

from app import worker


def test_worker_tick_runs_every_job(db, raffle, mkuser, monkeypatch):
    """expira reservas vencidas, cierra rifas, programa recordatorios y procesa la cola."""
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_flow import H, body
    client = TestClient(app)
    r, b = raffle(), mkuser()
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    db.execute("UPDATE payment_transactions SET expires_at = now() - interval '1 minute' WHERE id=%s", (tid,))
    db.execute("UPDATE raffles SET sales_close_at = now() - interval '1 second', draw_at = now() + interval '3 hours' WHERE id=%s", (r["id"],))
    monkeypatch.setattr(worker, "DSN", dsn())
    worker.tick()
    assert db.execute("SELECT status FROM payment_transactions WHERE id=%s", (tid,)).fetchone()["status"] == "EXPIRED"
    assert db.execute("SELECT status FROM raffles WHERE id=%s", (r["id"],)).fetchone()["status"] == "CLOSED"
