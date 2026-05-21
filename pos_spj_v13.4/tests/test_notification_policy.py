# tests/test_notification_policy.py
"""
Tests de la capa de política de notificaciones.
Verifica que los tipos correctos van a WA y los bloqueados solo al inbox.
"""
from __future__ import annotations
import json
import sqlite3
import sys
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE notification_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER, usuario TEXT,
            tipo TEXT, titulo TEXT, cuerpo TEXT DEFAULT '',
            datos TEXT DEFAULT '{}', leido INTEGER DEFAULT 0,
            sucursal_id INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY, usuario TEXT, nombre TEXT,
            rol TEXT DEFAULT 'cajero', sucursal_id INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE personal (
            id INTEGER PRIMARY KEY, nombre TEXT,
            telefono TEXT, activo INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
# 1. NotificationPolicyService
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationPolicy:

    def setup_method(self):
        from core.services.notifications.notification_policy_service import (
            NotificationPolicyService)
        self.policy = NotificationPolicyService()

    # Tipos permitidos → WA
    def test_nomina_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("nomina_pagada") is True

    def test_vacaciones_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("vacaciones_recordatorio") is True

    def test_descanso_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("descanso_recordatorio") is True

    def test_backup_fallido_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("backup_fallido") is True

    def test_diferencia_caja_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("diferencia_caja") is True

    def test_pedido_asignado_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("pedido_asignado_repartidor") is True

    def test_forecast_wa_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("forecast_sugerencia_compra") is True

    # Tipos bloqueados → solo inbox
    def test_pedido_nuevo_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("pedido_whatsapp_nuevo") is False

    def test_venta_cancelada_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("venta_cancelada") is False

    def test_anticipo_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("anticipo_requerido") is False
        assert self.policy.is_wa_allowed_for_staff("anticipo_recibido") is False

    def test_pedido_listo_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("pedido_listo") is False

    def test_venta_confirmada_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("venta_confirmada") is False

    def test_stock_bajo_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("stock_bajo") is False

    def test_corte_z_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("corte_z") is False

    def test_cambio_estado_wa_blocked(self):
        assert self.policy.is_wa_allowed_for_staff("cambio_estado_pedido") is False

    # Tipo desconocido → no está en allowlist → False (safe default)
    def test_unknown_type_not_allowed(self):
        assert self.policy.is_wa_allowed_for_staff("tipo_inventado_xyz") is False

    # Inbox siempre requerido
    def test_inbox_always_required(self):
        for tipo in ("nomina_pagada", "venta_cancelada", "stock_bajo", "pedido_nuevo"):
            assert self.policy.requires_erp_inbox(tipo) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NotificationDispatcher — inbox sin WA para tipos bloqueados
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherBlocksWA:

    def test_wa_not_called_for_blocked_type(self, mem_db):
        from core.services.notifications.notification_dispatcher import (
            NotificationDispatcher)

        wa_calls = []

        class FakeWA:
            def send_message(self, branch_id, phone_number, message):
                wa_calls.append(phone_number)

        mem_db.execute(
            "INSERT INTO usuarios VALUES (1,'cajero1','Juan Cajero','cajero',1,1)")
        mem_db.execute(
            "INSERT INTO personal VALUES (1,'Juan Cajero','+52100000001',1)")
        mem_db.commit()

        disp = NotificationDispatcher(mem_db, FakeWA(), sucursal_id=1)
        disp.dispatch_staff(
            tipo="venta_cancelada",
            destinatarios=[{"id": 1, "telefono": "+52100000001", "usuario": "cajero1"}],
            titulo="Venta cancelada",
            mensaje="Se canceló la venta WA-001",
            datos={},
        )
        # WA NO debe haberse llamado
        assert wa_calls == [], f"WA fue llamado para tipo bloqueado: {wa_calls}"
        # Inbox SÍ debe tener registro
        rows = mem_db.execute(
            "SELECT * FROM notification_inbox WHERE empleado_id=1").fetchall()
        assert len(rows) == 1

    def test_wa_called_for_allowed_type(self, mem_db):
        from core.services.notifications.notification_dispatcher import (
            NotificationDispatcher)

        wa_calls = []

        class FakeWA:
            def send_message(self, branch_id, phone_number, message):
                wa_calls.append(phone_number)

        mem_db.execute(
            "INSERT INTO usuarios VALUES (1,'emp1','Ana RRHH','admin',1,1)")
        mem_db.execute(
            "INSERT INTO personal VALUES (1,'Ana RRHH','+52100000002',1)")
        mem_db.commit()

        disp = NotificationDispatcher(mem_db, FakeWA(), sucursal_id=1)
        disp.dispatch_staff(
            tipo="nomina_pagada",
            destinatarios=[{"id": 1, "telefono": "+52100000002", "usuario": "emp1"}],
            titulo="Nómina Mayo 2026",
            mensaje="Tu pago de nómina fue procesado.",
            datos={"monto": 8500},
        )
        # WA SÍ debe haberse llamado
        assert "+52100000002" in wa_calls
        # Inbox también
        rows = mem_db.execute(
            "SELECT * FROM notification_inbox WHERE empleado_id=1").fetchall()
        assert len(rows) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NotificationService respeta política en _notificar_por_roles
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationServicePolicy:

    def test_stock_bajo_no_envía_whatsapp(self, mem_db):
        """notificar_stock_bajo → WA bloqueado por política → solo inbox."""
        from core.services.notification_service import NotificationService

        wa_calls = []

        class FakeWA:
            def send_message(self, **kw): wa_calls.append(kw)

        mem_db.execute(
            "INSERT INTO usuarios VALUES (1,'gerente1','Pedro Gerente','gerente',1,1)")
        mem_db.execute(
            "INSERT INTO personal VALUES (1,'Pedro Gerente','+52100000003',1)")
        mem_db.commit()

        svc = NotificationService(mem_db, whatsapp_service=FakeWA(), sucursal_id=1)
        svc.notificar_stock_bajo("Pollo Entero", 1.0, 5.0, sucursal_id=1)

        assert wa_calls == [], "WA no debe enviarse para stock_bajo"

    def test_corte_z_no_envía_whatsapp(self, mem_db):
        from core.services.notification_service import NotificationService

        wa_calls = []

        class FakeWA:
            def send_message(self, **kw): wa_calls.append(kw)

        mem_db.execute(
            "INSERT INTO usuarios VALUES (1,'admin1','Admin','admin',1,1)")
        mem_db.execute(
            "INSERT INTO personal VALUES (1,'Admin','+52100000004',1)")
        mem_db.commit()

        svc = NotificationService(mem_db, whatsapp_service=FakeWA(), sucursal_id=1)
        svc.notificar_corte_z("Z-001", 5000.0, 4950.0, -50.0, "cajero1", sucursal_id=1)

        assert wa_calls == [], "WA no debe enviarse para corte_z"
