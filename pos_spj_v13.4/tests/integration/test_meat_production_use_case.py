"""Integration tests for FASE 7 Producción Cárnica refactor.

Covers:
1. ExecuteMeatProductionCommand — field validation
2. ExecuteMeatProductionUseCase — delegates to service, returns UseCaseResult
3. _build_lote_balance_preview logic — UUID-keyed dicts (no int casts)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pos_spj_v13.4"))

from backend.application.commands.production_commands import (
    ExecuteMeatProductionCommand,
    OpenMeatBatchCommand,
    CloseMeatBatchCommand,
)
from backend.application.use_cases.execute_meat_production_use_case import ExecuteMeatProductionUseCase
from backend.shared.ids import new_uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_op() -> str:
    return new_uuid()


def _mock_service(batch_id="batch-001", folio="F001", ok=True, error=""):
    svc = MagicMock()
    opened = SimpleNamespace(ok=ok, batch_id=batch_id, error=error)
    svc.abrir_lote.return_value = opened
    svc.agregar_subproducto.return_value = None
    svc.cerrar_lote.return_value = SimpleNamespace(
        ok=ok, folio=folio, rendimiento_pct=85.0, error=error
    )
    return svc




# ---------------------------------------------------------------------------
# Command tests
# ---------------------------------------------------------------------------

def test_command_fields():
    op = _make_op()
    cmd = ExecuteMeatProductionCommand(
        operation_id=op,
        branch_id="branch-1",
        user_name="operador",
        product_id="prod-uuid-1",
        recipe_id="rec-uuid-1",
        batch_weight_kg=50.0,
        outputs=({"product_id": "prod-uuid-2", "weight_kg": 30.0},),
        waste_kg=2.0,
    )
    assert cmd.product_id == "prod-uuid-1"
    assert cmd.batch_weight_kg == 50.0
    assert len(cmd.outputs) == 1
    assert cmd.waste_kg == 2.0


def test_open_and_close_commands():
    op = _make_op()
    open_cmd = OpenMeatBatchCommand(
        operation_id=op, branch_id="b1", user_name="u",
        product_id="p1", batch_weight_kg=10.0,
    )
    close_cmd = CloseMeatBatchCommand(
        operation_id=op, branch_id="b1", user_name="u",
        batch_id="batch-1", waste_kg=1.0,
    )
    assert open_cmd.product_id == "p1"
    assert close_cmd.batch_id == "batch-1"


# ---------------------------------------------------------------------------
# Use case tests
# ---------------------------------------------------------------------------

def test_use_case_success():
    svc = _mock_service()
    uc = ExecuteMeatProductionUseCase(production_service=svc)
    cmd = ExecuteMeatProductionCommand(
        operation_id=_make_op(),
        branch_id="branch-1",
        user_name="operador",
        product_id="prod-1",
        recipe_id="rec-1",
        batch_weight_kg=100.0,
        outputs=({"product_id": "prod-2", "weight_kg": 60.0},),
        waste_kg=5.0,
    )
    result = uc.execute(cmd)
    assert result.success is True
    assert result.data["folio"] == "F001"
    svc.abrir_lote.assert_called_once()
    svc.agregar_subproducto.assert_called()
    svc.cerrar_lote.assert_called_once()


def test_use_case_service_failure():
    svc = _mock_service(ok=False, error="Stock insuficiente")
    uc = ExecuteMeatProductionUseCase(production_service=svc)
    cmd = ExecuteMeatProductionCommand(
        operation_id=_make_op(),
        branch_id="b1",
        user_name="u",
        product_id="p1",
        batch_weight_kg=10.0,
    )
    result = uc.execute(cmd)
    assert result.success is False
    assert result.message != ""


def test_use_case_missing_product_id():
    svc = _mock_service()
    uc = ExecuteMeatProductionUseCase(production_service=svc)
    cmd = ExecuteMeatProductionCommand(
        operation_id=_make_op(),
        branch_id="b1",
        user_name="u",
        product_id="",
        batch_weight_kg=10.0,
    )
    result = uc.execute(cmd)
    assert result.success is False
    assert "product_id" in result.message


def test_use_case_zero_weight():
    svc = _mock_service()
    uc = ExecuteMeatProductionUseCase(production_service=svc)
    cmd = ExecuteMeatProductionCommand(
        operation_id=_make_op(),
        branch_id="b1",
        user_name="u",
        product_id="p1",
        batch_weight_kg=0.0,
    )
    result = uc.execute(cmd)
    assert result.success is False


def test_use_case_no_outputs_no_waste():
    """Batch with no outputs and no waste still completes successfully."""
    svc = _mock_service()
    uc = ExecuteMeatProductionUseCase(production_service=svc)
    cmd = ExecuteMeatProductionCommand(
        operation_id=_make_op(),
        branch_id="b1",
        user_name="u",
        product_id="p1",
        batch_weight_kg=50.0,
        outputs=(),
        waste_kg=0.0,
    )
    result = uc.execute(cmd)
    assert result.success is True
    svc.agregar_subproducto.assert_not_called()


# ---------------------------------------------------------------------------
# Balance preview logic — UUID keys (no int casts), pure Python, no PyQt
# ---------------------------------------------------------------------------

def _balance_preview(movs_teoricos: list, reales: dict) -> dict:
    """Mirror of modulos/produccion._build_lote_balance_preview for isolated testing."""
    expected: dict[str, float] = {}
    for m in movs_teoricos:
        if float(m.get("delta", 0)) > 0:
            pid = str(m["product_id"])
            expected[pid] = expected.get(pid, 0.0) + float(m["delta"])
    total_exp = sum(expected.values())
    total_real = sum(float(v or 0) for v in reales.values())
    return {
        "expected": expected,
        "total_expected": total_exp,
        "total_real": total_real,
        "difference": round(total_real - total_exp, 4),
    }


def test_balance_preview_uuid_keys():
    movs = [
        {"product_id": "uuid-pechuga", "nombre": "Pechuga", "delta": 60.0},
        {"product_id": "uuid-muslo", "nombre": "Muslo", "delta": 30.0},
        {"product_id": "uuid-orig", "nombre": "Orig", "delta": -100.0},
    ]
    reales = {"uuid-pechuga": 58.0, "uuid-muslo": 28.0}
    bal = _balance_preview(movs, reales)
    assert bal["total_expected"] == pytest.approx(90.0)
    assert bal["total_real"] == pytest.approx(86.0)
    assert "uuid-pechuga" in bal["expected"]
    assert "uuid-muslo" in bal["expected"]
    assert bal["difference"] == pytest.approx(-4.0)


def test_balance_preview_no_outputs():
    bal = _balance_preview([], {})
    assert bal["total_expected"] == 0.0
    assert bal["total_real"] == 0.0
