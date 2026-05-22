# tests/test_wa_repositories.py
"""Tests for WhatsApp repositories and services (no SQL injection, no external deps)."""
import sqlite3
import pytest

from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository
from core.repositories.whatsapp_history_repository import WhatsAppHistoryRepository
from core.repositories.whatsapp_metrics_repository import WhatsAppMetricsRepository
from core.services.whatsapp_admin_service import WhatsAppAdminService
from core.services.whatsapp_credential_service import WhatsAppCredentialService


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE whatsapp_numeros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id INTEGER, canal TEXT DEFAULT 'todos',
            proveedor TEXT DEFAULT 'meta', numero_negocio TEXT,
            meta_token TEXT, meta_phone_id TEXT,
            twilio_sid TEXT, twilio_token TEXT,
            verify_token TEXT DEFAULT 'spj_verify',
            rasa_url TEXT DEFAULT 'http://localhost:5005',
            rasa_activo INTEGER DEFAULT 0, activo INTEGER DEFAULT 1,
            nombre_sucursal TEXT, UNIQUE(sucursal_id, canal)
        );
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE pedidos_whatsapp (
            id INTEGER PRIMARY KEY, fecha TEXT, numero_whatsapp TEXT,
            telefono_cliente TEXT, mensaje TEXT, estado TEXT, total REAL
        );
        CREATE TABLE wa_message_queue (
            id INTEGER PRIMARY KEY, fecha_creacion TEXT,
            to_number TEXT, message TEXT, status TEXT
        );
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER);
    """)
    return conn


# ── WhatsAppConfigRepository ──────────────────────────────────────────────────

class TestWhatsAppConfigRepository:
    def setup_method(self):
        self.db = _make_db()
        self.repo = WhatsAppConfigRepository(self.db)

    def test_insert_and_get_numero(self):
        self.repo.insert_numero(None, "todos", "meta", "+521234567890",
                                "phone_id_123", "token_abc", "",
                                "http://localhost:5005", 0, 1, None)
        rows = self.repo.get_numeros()
        assert len(rows) == 1
        assert rows[0][3] == "+521234567890"

    def test_update_numero(self):
        self.repo.insert_numero(None, "todos", "meta", "+521234567890",
                                "pid1", "tok1", "", "http://localhost:5005", 0, 1, None)
        rows = self.repo.get_numeros()
        nid = rows[0][0]
        self.repo.update_numero(nid, None, "clientes", "meta", "+529876543210",
                                "pid2", "tok2", "", "http://localhost:5005", 0, 1, None)
        rows2 = self.repo.get_numeros()
        assert rows2[0][3] == "+529876543210"

    def test_delete_numero(self):
        self.repo.insert_numero(None, "todos", "meta", "+521234567890",
                                "p", "t", "", "http://localhost:5005", 0, 1, None)
        rows = self.repo.get_numeros()
        nid = rows[0][0]
        self.repo.delete_numero(nid)
        assert len(self.repo.get_numeros()) == 0

    def test_config_get_set(self):
        assert self.repo.get_config("bot_nombre", "default") == "default"
        self.repo.set_config("bot_nombre", "Asistente SPJ")
        self.repo.commit()
        assert self.repo.get_config("bot_nombre") == "Asistente SPJ"

    def test_config_key_prefix(self):
        self.repo.set_config("test_key", "test_val")
        self.repo.commit()
        row = self.db.execute(
            "SELECT valor FROM configuraciones WHERE clave='wa_test_key'"
        ).fetchone()
        assert row is not None and row[0] == "test_val"


# ── WhatsAppHistoryRepository ─────────────────────────────────────────────────

class TestWhatsAppHistoryRepository:
    def setup_method(self):
        self.db = _make_db()
        self.repo = WhatsAppHistoryRepository(self.db)

    def test_empty_history(self):
        rows = self.repo.get_history("")
        assert rows == []

    def test_history_from_pedidos(self):
        self.db.execute(
            "INSERT INTO pedidos_whatsapp(fecha, numero_whatsapp, mensaje, estado) "
            "VALUES('2025-01-01', '+521234567890', 'Hola', 'recibido')"
        )
        self.db.commit()
        rows = self.repo.get_history("")
        assert len(rows) == 1

    def test_history_search_safe_no_injection(self):
        """Verifica que la búsqueda usa parámetros seguros (no interpolación)."""
        self.db.execute(
            "INSERT INTO pedidos_whatsapp(fecha, numero_whatsapp, mensaje, estado) "
            "VALUES('2025-01-01', '+521234567890', 'Hola', 'recibido')"
        )
        self.db.commit()
        # Attempt SQL injection via search — should not cause error
        rows = self.repo.get_history("'; DROP TABLE pedidos_whatsapp; --")
        # Table should still exist
        count = self.db.execute(
            "SELECT COUNT(*) FROM pedidos_whatsapp"
        ).fetchone()[0]
        assert count == 1

    def test_history_search_filters(self):
        self.db.execute(
            "INSERT INTO pedidos_whatsapp(fecha, numero_whatsapp, mensaje, estado) "
            "VALUES('2025-01-01', '+521234567890', 'Quiero pollo', 'recibido')"
        )
        self.db.commit()
        rows = self.repo.get_history("pollo")
        assert len(rows) == 1
        rows_no = self.repo.get_history("pizza")
        assert len(rows_no) == 0


# ── WhatsAppMetricsRepository ─────────────────────────────────────────────────

class TestWhatsAppMetricsRepository:
    def setup_method(self):
        self.db = _make_db()
        # bot_sessions table may not exist — metrics should handle gracefully
        self.repo = WhatsAppMetricsRepository(self.db)

    def test_empty_metrics(self):
        m = self.repo.get_metrics()
        assert m["total"] == 0
        assert m["hoy"] == 0
        assert m["valor_total"] == 0.0

    def test_metrics_with_data(self):
        self.db.execute(
            "INSERT INTO pedidos_whatsapp(fecha, estado, total) "
            "VALUES(datetime('now'), 'pendiente', 150.0)"
        )
        self.db.commit()
        m = self.repo.get_metrics()
        assert m["total"] == 1
        assert m["pendientes"] == 1
        assert m["valor_total"] == 150.0


# ── WhatsAppCredentialService ─────────────────────────────────────────────────

class TestWhatsAppCredentialService:
    def setup_method(self):
        self.db = _make_db()
        self.svc = WhatsAppCredentialService(self.db)

    def test_save_and_get_masked(self):
        self.svc.save_credentials(
            "EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "12345678901234",
            "spj_verify_2025"
        )
        masked = self.svc.get_masked_credentials()
        assert masked["configured"] is True
        assert masked["phone_number_id"] == "12345678901234"
        assert "EAAxxxxx" in masked["token_masked"]
        assert len(masked["token_masked"]) < 40  # not full token

    def test_save_empty_token_raises(self):
        with pytest.raises(ValueError):
            self.svc.save_credentials("", "phone_id")

    def test_save_empty_phone_id_raises(self):
        with pytest.raises(ValueError):
            self.svc.save_credentials("some_token", "")

    def test_validate_meta_credentials_empty(self):
        ok, err = self.svc.validate_meta_credentials("", "phone_id")
        assert not ok
        assert "vacío" in err

    def test_validate_meta_credentials_short_token(self):
        ok, err = self.svc.validate_meta_credentials("short", "phone_id")
        assert not ok
        assert "corto" in err

    def test_validate_webhook_token_ok(self):
        ok, err = self.svc.validate_webhook_token("spj_verify_2025")
        assert ok and err == ""

    def test_validate_webhook_token_empty(self):
        ok, err = self.svc.validate_webhook_token("")
        assert not ok

    def test_validate_webhook_token_too_short(self):
        ok, err = self.svc.validate_webhook_token("abc")
        assert not ok


# ── WhatsAppAdminService ──────────────────────────────────────────────────────

class TestWhatsAppAdminService:
    def setup_method(self):
        self.db = _make_db()
        self.svc = WhatsAppAdminService(self.db)

    def test_get_bot_config_defaults(self):
        cfg = self.svc.get_bot_config()
        assert cfg["bot_nombre"] == "Asistente SPJ"
        assert cfg["bot_activo"] is False
        assert cfg["timeout"] == 30

    def test_save_and_reload_bot_config(self):
        self.svc.save_bot_config({
            "bot_nombre": "SPJ Bot",
            "bot_activo": True,
            "rasa_activo": False,
            "rasa_url": "http://rasa.local:5005",
            "timeout": 45,
            "msg_bienvenida": "Hola!",
            "cotizaciones": True,
            "rrhh_notif": False,
        })
        cfg = self.svc.get_bot_config()
        assert cfg["bot_nombre"] == "SPJ Bot"
        assert cfg["bot_activo"] is True
        assert cfg["timeout"] == 45

    def test_get_history_empty(self):
        assert self.svc.get_history() == []

    def test_get_metrics_empty(self):
        m = self.svc.get_metrics()
        assert "total" in m and m["total"] == 0
