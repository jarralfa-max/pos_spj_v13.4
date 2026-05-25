import sqlite3

from core.db.connection import DatabaseWrapper


def test_database_wrapper_transaction_accepts_name_parameter():
    raw = sqlite3.connect(":memory:")
    db = DatabaseWrapper(raw)
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")

    with db.transaction("RECETA_CREATE"):
        db.execute("INSERT INTO t(v) VALUES (?)", ("ok",))

    row = db.fetchone("SELECT v FROM t WHERE id = 1")
    assert row[0] == "ok"

