import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from app import migrate


def new_db(pg):
    admin = pg.rsplit("/", 1)[0]
    name = "mig_" + uuid.uuid4().hex[:8]
    with psycopg.connect(admin + "/postgres", autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name}")
    return admin + "/" + name


def conn(dsn):
    return psycopg.connect(dsn, row_factory=dict_row)


def tables(c):
    return {r["table_name"] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}


def test_fresh_database_gets_every_migration(pg):
    dsn = new_db(pg)
    with conn(dsn) as c:
        applied = migrate.apply_all(c)
    assert applied == [f.stem for f in migrate.files()] and applied[0] == "0001_baseline"
    with conn(dsn) as c:
        assert {"users", "rate_limits", "schema_migrations"} <= tables(c)
        assert migrate.apply_all(c) == []  # idempotente
        assert migrate.current(c) == migrate.files()[-1].stem


def test_legacy_database_without_migration_table_is_adopted(pg):
    """Neon ya creada con el esquema inicial: se reconoce la línea base y solo se aplican las nuevas."""
    dsn = new_db(pg)
    with conn(dsn) as c:
        c.execute(migrate.files()[0].read_text())  # como lo dejaba SGRS_AUTO_SCHEMA antes
    with conn(dsn) as c:
        assert "schema_migrations" not in tables(c)
        applied = migrate.apply_all(c)
    assert "0001_baseline" not in applied and "0002_rate_limits_and_consent" in applied
    with conn(dsn) as c:
        cols = {r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")}
        assert {"terms_accepted_at", "terms_version"} <= cols


def test_failed_migration_rolls_back_everything(pg, tmp_path, monkeypatch):
    dsn = new_db(pg)
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE a (id int);")
    (tmp_path / "0002_mala.sql").write_text("CREATE TABLE b (id int); SELECT * FROM no_existe;")
    monkeypatch.setattr(migrate, "DIR", tmp_path)
    with pytest.raises(psycopg.errors.UndefinedTable):
        with conn(dsn) as c:
            migrate.apply_all(c)
    with conn(dsn) as c:
        assert not ({"a", "b", "schema_migrations"} & tables(c))  # nada a medias


def test_migration_files_are_numbered_without_gaps():
    nums = [int(f.name[:4]) for f in migrate.files()]
    assert nums == list(range(1, len(nums) + 1))
