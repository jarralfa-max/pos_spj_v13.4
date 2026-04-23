import sqlite3
import tempfile
import importlib
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
WA_SERVICE_DIR = os.path.join(ROOT_DIR, "whatsapp_service")
if WA_SERVICE_DIR not in sys.path:
    sys.path.insert(0, WA_SERVICE_DIR)

from core.services.auth_service import AuthService
from core.services.sales_service import SalesService
from core.services.sales.unified_sales_service import PagoInsuficienteError
from core.services.sales_reversal_service import SalesReversalService
from core.events.outbox import enqueue_event, fetch_pending, mark_dispatched
import core.events.outbox_dispatcher as outbox_dispatcher_mod
from core.events.outbox_dispatcher import dispatch_pending, OutboxDispatcherThread
from repositories.auth_repository import AuthRepository


def test_auth_service_auto_rehash_plaintext_password():
    class Repo:
        def __init__(self):
            self.migrated = []

        def get_user_by_username(self, username):
            return {
                "id": 7,
                "username": username,
                "password_hash": "1234",  # legacy plaintext
                "rol": "admin",
                "nombre": "Root",
                "sucursal_id": 1,
                "sucursal_nombre": "Principal",
                "sucursales_disponibles": [{"id": 1, "nombre": "Principal"}],
            }

        def migrate_password_hash(self, user_id, new_hash):
            self.migrated.append((user_id, new_hash))
            return True

    class Security:
        def clear_cache(self):
            return None

        def load_permissions(self, **kwargs):
            return None

    class Audit:
        def __init__(self):
            self.actions = []

        def log_change(self, **kwargs):
            self.actions.append(kwargs.get("accion"))

    repo = Repo()
    audit = Audit()
    svc = AuthService(repo, Security(), audit)

    out = svc.authenticate("admin", "1234")

    assert out["username"] == "admin"
    assert any(a == "PASSWORD_REHASHED" for a in audit.actions)
    assert repo.migrated and repo.migrated[0][0] == 7
    # Nuevo hash no debe permanecer en texto plano
    assert repo.migrated[0][1] != "1234"


def test_auth_repository_detects_password_column_and_migrates():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            usuario TEXT,
            clave TEXT,
            rol TEXT,
            nombre TEXT,
            activo INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO usuarios(id, usuario, clave, rol, nombre, activo) VALUES (1,'u1','abc','admin','U1',1)"
    )
    conn.commit()

    repo = AuthRepository(conn)
    assert repo._detect_password_column() == "clave"
    assert repo.migrate_password_hash(1, "NEW_HASH") is True

    row = conn.execute("SELECT clave FROM usuarios WHERE id=1").fetchone()
    assert row["clave"] == "NEW_HASH"


def test_sales_service_legacy_rejects_cash_below_total():
    class DummyDB:
        pass

    svc = SalesService(
        db_conn=DummyDB(),
        sales_repo=None,
        recipe_repo=None,
        inventory_service=None,
        finance_service=None,
        loyalty_service=None,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=None,
        whatsapp_service=None,
        config_service=None,
        feature_flag_service=None,
    )

    try:
        svc._procesar_venta_legacy_minimal(
            items_payload=[{"product_id": 1, "qty": 2, "unit_price": 10.0}],
            payment_method="Efectivo",
            amount_paid=5.0,
            client_id=None,
            discount=0.0,
            usuario="cajero",
        )
        assert False, "Debió levantar PagoInsuficienteError"
    except PagoInsuficienteError:
        assert True


def test_webapp_start_server_applies_db_path():
    from webapp import api_pedidos as api

    srv = api.start_webapp_server(port=0, db_path="/tmp/spj_test_hardening.db")
    try:
        assert api._DB_PATH == "/tmp/spj_test_hardening.db"
    finally:
        srv.shutdown()
        srv.server_close()


def test_auth_service_failed_attempt_uses_usuario_column():
    class Repo:
        def __init__(self, db):
            self.db = db

        def get_user_by_username(self, username):
            return None

    class Security:
        def clear_cache(self): return None
        def load_permissions(self, **kwargs): return None

    class Audit:
        def log_change(self, **kwargs): return None

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            usuario TEXT UNIQUE,
            intentos_fallidos INTEGER DEFAULT 0,
            bloqueado_hasta TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute("INSERT INTO usuarios(usuario, intentos_fallidos, activo) VALUES ('u1',0,1)")
    conn.commit()

    svc = AuthService(Repo(conn), Security(), Audit())
    svc._register_failed_attempt("u1")

    row = conn.execute("SELECT intentos_fallidos FROM usuarios WHERE usuario='u1'").fetchone()
    assert int(row["intentos_fallidos"]) == 1


def test_auth_service_registers_failed_attempt_on_wrong_password():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY,
            usuario TEXT UNIQUE,
            contrasena TEXT,
            rol TEXT,
            nombre TEXT,
            activo INTEGER DEFAULT 1,
            intentos_fallidos INTEGER DEFAULT 0,
            bloqueado_hasta TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO usuarios(id, usuario, contrasena, rol, nombre, activo, intentos_fallidos) "
        "VALUES (1,'u2','secreto','admin','U2',1,0)"
    )
    conn.commit()

    repo = AuthRepository(conn)

    class Security:
        def clear_cache(self): return None
        def load_permissions(self, **kwargs): return None

    class Audit:
        def log_change(self, **kwargs): return None

    svc = AuthService(repo, Security(), Audit())
    try:
        svc.authenticate("u2", "incorrecta")
        assert False, "Debió fallar por contraseña incorrecta"
    except PermissionError:
        pass

    row = conn.execute("SELECT intentos_fallidos FROM usuarios WHERE usuario='u2'").fetchone()
    assert int(row["intentos_fallidos"]) == 1


def test_webapp_check_auth_header_validation():
    from webapp.api_pedidos import WebAppHandler

    h = WebAppHandler.__new__(WebAppHandler)
    h.headers = {"X-API-Token": "tok_ok"}
    h._get_config = lambda *_a, **_k: "tok_ok"
    assert h._check_auth() is True

    h2 = WebAppHandler.__new__(WebAppHandler)
    h2.headers = {"X-API-Token": "tok_bad"}
    h2._get_config = lambda *_a, **_k: "tok_ok"
    assert h2._check_auth() is False


def test_webapp_check_auth_rejects_when_token_not_configured():
    from webapp.api_pedidos import WebAppHandler
    h = WebAppHandler.__new__(WebAppHandler)
    h.headers = {"X-API-Token": "anything"}
    h._get_config = lambda *_a, **_k: ""
    assert h._check_auth() is False


def test_sales_reversal_service_accepts_db_wrapper_with_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    class LegacyDB:
        def __init__(self, c):
            self.conn = c

    svc = SalesReversalService(LegacyDB(conn))
    assert svc.branch_id == 1
    # wrapper interno debe operar sobre sqlite connection real
    row = svc.db.execute("SELECT 1 as ok").fetchone()
    assert row["ok"] == 1


def test_webapp_security_event_is_audited():
    from webapp import api_pedidos as api

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        conn.execute(
            """
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                accion TEXT,
                modulo TEXT,
                entidad TEXT,
                entidad_id TEXT,
                valor_antes TEXT,
                valor_despues TEXT,
                sucursal_id INTEGER,
                detalles TEXT
            )
            """
        )
        conn.commit()
        conn.close()

        prev = api._DB_PATH
        api._DB_PATH = tmp.name
        try:
            api._record_security_event("WEBAPP_AUTH_DENIED_GET", "Ruta: /api/productos", "127.0.0.1")
        finally:
            api._DB_PATH = prev

        conn2 = sqlite3.connect(tmp.name)
        row = conn2.execute(
            "SELECT accion, entidad_id, detalles FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn2.close()
        assert row is not None
        assert row[0] == "WEBAPP_AUTH_DENIED_GET"
        assert row[1] == "127.0.0.1"


def test_auto_audit_fail_closed_raises_on_error():
    os.environ["SPJ_AUDIT_CRITICAL_FAILCLOSED"] = "1"
    mod = importlib.import_module("core.services.auto_audit")
    mod = importlib.reload(mod)

    class BadDB:
        def execute(self, *_a, **_k):
            raise RuntimeError("db write failed")

    class C:
        db = BadDB()
        audit_service = None

    try:
        mod.audit_write(
            C(),
            modulo="TEST",
            accion="WRITE",
            entidad="x",
            entidad_id="1",
            usuario="u",
            detalles="d",
        )
        assert False, "Debe elevar excepción en modo fail-closed"
    except RuntimeError:
        assert True


def test_caja_navigation_back_button_is_connected():
    path = os.path.join(os.path.dirname(__file__), "..", "modulos", "caja.py")
    source = open(path, encoding="utf-8").read()
    assert "self._btn_back.clicked.connect(self._prev_page)" in source


def test_caja_navigation_does_not_recreate_next_button():
    path = os.path.join(os.path.dirname(__file__), "..", "modulos", "caja.py")
    source = open(path, encoding="utf-8").read()
    assert "self._btn_next = create_success_button" not in source
    assert 'self._btn_next = create_primary_button(self, "Siguiente ▶", "Continuar al siguiente paso")' not in source


def test_event_outbox_persist_fetch_and_mark():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    event_id = enqueue_event(
        conn,
        event_type="VENTA_COMPLETADA",
        payload={"venta_id": 10, "total": 99.5},
        aggregate_type="venta",
        aggregate_id="10",
    )
    assert event_id > 0

    pending = fetch_pending(conn, limit=10)
    assert pending and pending[0]["event_type"] == "VENTA_COMPLETADA"
    assert pending[0]["payload"]["venta_id"] == 10

    mark_dispatched(conn, event_id)
    pending2 = fetch_pending(conn, limit=10)
    assert all(ev["id"] != event_id for ev in pending2)


def test_event_outbox_dispatcher_marks_dispatched_and_error():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ok_id = enqueue_event(conn, "OK_EVENT", {"x": 1})
    bad_id = enqueue_event(conn, "BAD_EVENT", {"y": 2})

    class FakeBus:
        def publish(self, event_type, payload, async_=False):
            if event_type == "BAD_EVENT":
                raise RuntimeError("dispatch boom")
            return None

    result = dispatch_pending(conn, bus=FakeBus(), max_events=10)
    assert result["pending"] == 2
    assert result["dispatched"] == 1
    assert result["failed"] == 1

    row_ok = conn.execute("SELECT status FROM event_outbox WHERE id=?", (ok_id,)).fetchone()
    row_bad = conn.execute("SELECT status, error FROM event_outbox WHERE id=?", (bad_id,)).fetchone()
    assert row_ok["status"] == "DISPATCHED"
    assert row_bad["status"] == "ERROR"
    assert "dispatch boom" in (row_bad["error"] or "")


def test_outbox_dispatcher_thread_drains_multiple_batches(monkeypatch):
    responses = iter([
        {"pending": 100, "dispatched": 100, "failed": 0},
        {"pending": 30, "dispatched": 30, "failed": 0},
    ])
    calls = {"n": 0}

    def fake_dispatch(_db, bus=None, max_events=0):
        calls["n"] += 1
        assert max_events == 100
        return next(responses)

    monkeypatch.setattr(outbox_dispatcher_mod, "dispatch_pending", fake_dispatch)

    t = OutboxDispatcherThread(db=object(), batch_size=100, max_batches_per_cycle=10)
    summary = t._drain_once()
    assert calls["n"] == 2
    assert summary["batches"] == 2
    assert summary["dispatched"] == 130
    assert summary["failed"] == 0


def test_outbox_dispatcher_thread_respects_max_batches_cap(monkeypatch):
    calls = {"n": 0}

    def fake_dispatch(_db, bus=None, max_events=0):
        calls["n"] += 1
        return {"pending": max_events, "dispatched": 0, "failed": 0}

    monkeypatch.setattr(outbox_dispatcher_mod, "dispatch_pending", fake_dispatch)

    t = OutboxDispatcherThread(db=object(), batch_size=50, max_batches_per_cycle=3)
    summary = t._drain_once()
    assert calls["n"] == 3
    assert summary["batches"] == 3


def test_health_metrics_include_outbox_and_webapp_security_signals():
    path = os.path.join(ROOT_DIR, "pos_spj_v13.4", "core", "health", "health_server.py")
    source = open(path, encoding="utf-8").read()
    assert "spj_outbox_pending" in source
    assert "spj_outbox_error" in source
    assert "spj_webapp_auth_denied_hoy" in source


def test_whatsapp_settings_no_default_verify_token():
    path = os.path.join(ROOT_DIR, "whatsapp_service", "config", "settings.py")
    source = open(path, encoding="utf-8").read()
    assert 'WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")' in source


def test_whatsapp_webhook_uses_compare_digest():
    path = os.path.join(ROOT_DIR, "whatsapp_service", "webhook", "whatsapp.py")
    source = open(path, encoding="utf-8").read()
    assert "hmac.compare_digest" in source
    assert "return Response(status_code=503)" in source


def test_merma_high_value_requires_manager_pin():
    path = os.path.join(ROOT_DIR, "pos_spj_v13.4", "modulos", "merma.py")
    source = open(path, encoding="utf-8").read()
    assert "Ingresa PIN de gerente/admin para autorizar la merma" in source
    assert "MERMA_DENEGADA_PIN" in source


def test_sales_service_generates_unique_auditable_folio():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, folio TEXT)")
    conn.commit()

    class DB:
        def __init__(self, c): self._c = c
        def execute(self, *a, **k): return self._c.execute(*a, **k)

    svc = SalesService(
        db_conn=DB(conn),
        sales_repo=None,
        recipe_repo=None,
        inventory_service=None,
        finance_service=None,
        loyalty_service=None,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=None,
        whatsapp_service=None,
        config_service=None,
        feature_flag_service=None,
    )

    f1 = svc._generate_unique_sale_folio()
    conn.execute("INSERT INTO ventas(folio) VALUES (?)", (f1,))
    conn.commit()
    f2 = svc._generate_unique_sale_folio()
    assert f1 != f2
    assert f1.startswith("V") and "-" in f1
