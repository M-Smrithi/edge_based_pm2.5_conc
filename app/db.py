"""stdlib sqlite3 access + forward-only SQL migrations (app/migrations/NNN_*.sql, applied once, recorded)."""
from __future__ import annotations
import sqlite3
from pathlib import Path

from flask import g

import core.config as C

MIGRATIONS = Path(__file__).parent / "migrations"


def connect(path=None) -> sqlite3.Connection:
    path = Path(path or C.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)  # explicit transactions
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON"); con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA busy_timeout=30000")
    return con


def migrate(con: sqlite3.Connection) -> list[str]:
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_utc TEXT NOT NULL)")
    done = {r["name"] for r in con.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        con.execute("BEGIN")
        try:
            for stmt in [s.strip() for s in f.read_text().split(";\n") if s.strip()]:
                con.execute(stmt)
            con.execute("INSERT INTO schema_migrations VALUES(?, datetime('now'))", (f.name,))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK"); raise
        applied.append(f.name)
    return applied


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


class tx:
    """with tx(con): ... -> BEGIN IMMEDIATE / COMMIT / ROLLBACK."""
    def __init__(self, con): self.con = con
    def __enter__(self): self.con.execute("BEGIN IMMEDIATE"); return self.con
    def __exit__(self, et, ev, tb):
        self.con.execute("ROLLBACK" if et else "COMMIT"); return False
