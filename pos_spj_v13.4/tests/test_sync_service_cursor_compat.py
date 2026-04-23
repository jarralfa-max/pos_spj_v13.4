import sqlite3

from core.services.sync_service import SyncService


class _DBWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)


def test_sync_service_cursor_usa_conn_si_no_hay_cursor_directo():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE configuraciones(clave TEXT, valor TEXT)")
    conn.execute(
        "CREATE TABLE sync_outbox(id INTEGER PRIMARY KEY, tabla TEXT, operacion TEXT, registro_id INTEGER, payload TEXT, sucursal_id INTEGER, enviado INTEGER, intentos INTEGER, fecha TEXT)"
    )
    conn.execute("CREATE TABLE sync_state(key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

    svc = SyncService(_DBWrapper(conn))
    svc.registrar_evento("ventas", "insert", 1, {"ok": True})

    row = conn.execute("SELECT COUNT(*) FROM sync_outbox").fetchone()
    assert row[0] == 1
