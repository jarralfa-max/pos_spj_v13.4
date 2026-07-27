"""Las compras no generan movimientos de Caja: salen de capital/tesorería o CxP."""
from __future__ import annotations

from pathlib import Path

import pytest

from application.services.caja_application_service import CajaApplicationService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

APP_ROOT = Path(__file__).resolve().parents[2]


class _FinanceRecorder:
    """Registra llamadas para verificar que compras no tocan Caja."""

    def __init__(self):
        self.asientos = []
        self.movimientos_caja = []
        self.cxp = []

    def registrar_asiento(self, **kwargs):
        self.asientos.append(kwargs)

    def registrar_movimiento_manual(self, *args, **kwargs):
        self.movimientos_caja.append((args, kwargs))

    def crear_cxp(self, **kwargs):
        self.cxp.append(kwargs)

    def get_estado_turno(self, *args, **kwargs):
        return {"id": new_uuid()}   # simula turno abierto: aun así no debe usarse


class _InventoryStub:
    def increase_stock(self, **kwargs):
        return True

    def add_stock(self, **kwargs):
        return True


class _RepoStub:
    def __init__(self, db):
        self.db = db

    def insert_purchase(self, **kwargs):
        return new_uuid()


def test_cash_purchase_never_registers_cash_movement():
    """Fuente: purchase_service ya no llama registrar_movimiento_manual."""
    raw = (APP_ROOT / "core" / "services" / "purchase_service.py").read_text(encoding="utf-8")
    code_lines = [l for l in raw.splitlines() if not l.strip().startswith("#")]
    src = "\n".join(code_lines)
    assert "registrar_movimiento_manual" not in src
    assert "movimientos_caja" not in src
    assert 'haber="caja_efectivo"' not in src
    assert 'haber="capital_operativo"' in src


def test_purchase_journal_goes_against_capital_not_cash():
    """El asiento de compra contado es inventario_almacen/capital_operativo."""
    src = (APP_ROOT / "core" / "services" / "purchase_service.py").read_text(encoding="utf-8")
    assert 'debe="inventario_almacen"' in src


def test_cash_service_guard_rejects_purchase_movements():
    conn = make_db()
    svc = CajaApplicationService.__new__(CajaApplicationService)
    svc.db = conn
    svc._publish = lambda *a, **k: None

    with pytest.raises(ValueError, match="no se registran desde Caja"):
        svc.registrar_movimiento_manual(
            new_uuid(), new_uuid(), "user", "RETIRO", 100.0,
            "Pago compra F-1", modulo="compras",
        )
    with pytest.raises(ValueError, match="no se registran desde Caja"):
        svc.registrar_movimiento_manual(
            new_uuid(), new_uuid(), "user", "RETIRO", 100.0,
            "Pago compra F-1", referencia_tipo="compra",
        )
    n = conn.execute("SELECT COUNT(*) FROM movimientos_caja").fetchone()[0]
    assert n == 0
