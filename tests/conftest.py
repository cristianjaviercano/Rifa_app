import os, subprocess, tempfile, uuid
import psycopg, pytest
from psycopg.rows import dict_row

PGBIN = "/usr/lib/postgresql/16/bin"
PORT = 5433
EXT = os.environ.get("SGRS_TEST_DSN")  # CI: PostgreSQL ya provisto (con contraseña)
os.environ["SGRS_DSN"] = EXT or f"postgresql://postgres@127.0.0.1:{PORT}/sgrs"
os.environ["SGRS_RATE_LIMITS"] = "off"   # las pruebas de límites lo activan explícitamente
os.environ["SGRS_POOL"] = "0"


def dsn() -> str:
    """DSN de la base de pruebas, con credenciales (c.info.dsn las omite)."""
    import app.db
    return app.db.DSN


def _migrate(dsn_):
    from app import migrate
    with psycopg.connect(dsn_, row_factory=dict_row) as m:
        migrate.apply_all(m)


@pytest.fixture(scope="session", autouse=True)  # autouse: ninguna prueba depende del orden en que se inicializa la BD
def pg():
    ext = EXT
    if ext:
        import app.db
        app.db.DSN = ext
        with psycopg.connect(ext, autocommit=True) as c:
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        _migrate(ext)
        yield ext
        return
    d = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(["su", "nobody", "-s", "/bin/bash", "-c", " ".join(a)], check=True, capture_output=True)
    subprocess.run(["chown", "nobody", d], check=True)
    run(f"{PGBIN}/initdb -D {d}/data -U postgres --auth=trust")
    run(f"{PGBIN}/pg_ctl -D {d}/data -o '-p {PORT} -k {d}' -l {d}/log -w start")
    admin = f"postgresql://postgres@127.0.0.1:{PORT}"
    with psycopg.connect(admin + "/postgres", autocommit=True) as c:
        c.execute("CREATE DATABASE sgrs")
    _migrate(admin + "/sgrs")
    yield admin + "/sgrs"
    run(f"{PGBIN}/pg_ctl -D {d}/data -m immediate stop")


@pytest.fixture
def db(pg):
    with psycopg.connect(pg, row_factory=dict_row, autocommit=True) as c:
        yield c


@pytest.fixture
def raffle(db):
    def mk(n=10, price=10000, close="+1 hour"):
        owner = db.execute("INSERT INTO users (phone_e164,name) VALUES (%s,'owner') RETURNING id",
                           ("+57" + uuid.uuid4().hex[:9],)).fetchone()["id"]
        r = db.execute(
            "INSERT INTO raffles (owner_id,title,terms_md,total_numbers,numbers_per_ticket,ticket_price,"
            " sales_close_at,draw_at,draw_method,status) VALUES (%s,'t','t',%s,1,%s,"
            f" now() + interval '{close}', now() + interval '2 days','INTERNAL_CSPRNG','OPEN') RETURNING id",
            (owner, n, price)).fetchone()["id"]
        for s in range(1, n + 1):
            t = db.execute("INSERT INTO tickets (raffle_id,serial) VALUES (%s,%s) RETURNING id", (r, s)).fetchone()["id"]
            db.execute("INSERT INTO ticket_numbers VALUES (%s,%s,%s)", (r, s, t))
        tickets = [x["id"] for x in db.execute("SELECT id FROM tickets WHERE raffle_id=%s ORDER BY serial", (r,))]
        return {"id": r, "owner": owner, "tickets": tickets}
    return mk


@pytest.fixture
def mkuser(db):
    def f():
        return db.execute("INSERT INTO users (phone_e164,name) VALUES (%s,'b') RETURNING id, role",
                          ("+57" + uuid.uuid4().hex[:9],)).fetchone()
    return f
