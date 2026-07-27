# tests/test_uc_produccion.py — SPJ POS v13.4
"""Tests para GestionarProduccionUC (core/use_cases/produccion.py)."""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Fake engine result objects (mirror ProductionEngine API)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeYieldResult:
    usable_pct: float = 85.0
    waste_pct: float = 0.0


@dataclass
class _FakeBatchResult:
    batch_id: str
    folio: str
    yield_result: Optional[_FakeYieldResult] = None
    inventory_movements: int = 0
    cost_allocations: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine(
    open_ok=True,
    close_ok=True,
    rendimiento=85.0,
    movimientos=3,
    open_error=None,
    close_error=None,
):
    eng = MagicMock()
    if open_error:
        eng.open_batch.side_effect = open_error
    else:
        eng.open_batch.return_value = _FakeBatchResult(
            batch_id="BATCH-001", folio="PROD-20260101-001"
        )
    if close_error:
        eng.close_batch.side_effect = close_error
    else:
        eng.close_batch.return_value = _FakeBatchResult(
            batch_id="BATCH-001",
            folio="PROD-20260101-001",
            yield_result=_FakeYieldResult(usable_pct=rendimiento),
            inventory_movements=movimientos,
        )
    return eng


def _make_uc(engine=None, event_bus=None):
    from core.use_cases.produccion import GestionarProduccionUC
    eng = engine or _make_engine()
    inv = MagicMock()
    return GestionarProduccionUC(
        production_engine=eng,
        inventory_service=inv,
        event_bus=event_bus,
    )


# ─────────────────────────────────────────────────────────────────────────────
# abrir_lote
# ─────────────────────────────────────────────────────────────────────────────

class TestAbrirLote:
    def test_abrir_lote_retorna_ok_con_batch_id(self):
        uc = _make_uc()
        r = uc.abrir_lote(
            producto_origen_id=1, peso_kg=10.0,
            sucursal_id=1, usuario="produccion",
        )
        assert r.ok is True
        assert r.batch_id == "BATCH-001"
        assert r.folio == "PROD-20260101-001"

    def test_abrir_lote_peso_cero_retorna_error(self):
        uc = _make_uc()
        r = uc.abrir_lote(
            producto_origen_id=1, peso_kg=0.0,
            sucursal_id=1, usuario="produccion",
        )
        assert r.ok is False
        assert "Peso" in r.error or "0" in r.error

    def test_abrir_lote_peso_negativo_retorna_error(self):
        uc = _make_uc()
        r = uc.abrir_lote(
            producto_origen_id=1, peso_kg=-5.0,
            sucursal_id=1, usuario="produccion",
        )
        assert r.ok is False

    def test_abrir_lote_fallo_engine_retorna_error(self):
        eng = _make_engine(open_error=RuntimeError("no hay inventario"))
        uc = _make_uc(engine=eng)
        r = uc.abrir_lote(
            producto_origen_id=1, peso_kg=10.0,
            sucursal_id=1, usuario="produccion",
        )
        assert r.ok is False
        assert "inventario" in r.error

    def test_abrir_lote_llama_engine_open_batch(self):
        eng = _make_engine()
        uc = _make_uc(engine=eng)
        uc.abrir_lote(
            producto_origen_id=2, peso_kg=15.0,
            sucursal_id=1, usuario="jefe",
        )
        eng.open_batch.assert_called_once_with(
            product_source_id=2,
            source_weight=15.0,
            branch_id=1,
            created_by="jefe",
            receta_id=None,
        )

    def test_abrir_lote_con_receta_id_pasa_correctamente(self):
        eng = _make_engine()
        uc = _make_uc(engine=eng)
        uc.abrir_lote(
            producto_origen_id=3, peso_kg=5.0,
            sucursal_id=2, usuario="chef",
            receta_id=7,
        )
        call_kwargs = eng.open_batch.call_args.kwargs
        assert call_kwargs["receta_id"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# cerrar_lote
# ─────────────────────────────────────────────────────────────────────────────

class TestCerrarLote:
    def test_cerrar_lote_ok_retorna_rendimiento(self):
        eng = _make_engine(rendimiento=92.5, movimientos=4)
        uc = _make_uc(engine=eng)
        r = uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="jefe")
        assert r.ok is True
        assert r.rendimiento_pct == pytest.approx(92.5)
        assert r.movimientos == 4

    def test_cerrar_lote_retorna_batch_id_y_folio(self):
        uc = _make_uc()
        r = uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="jefe")
        assert r.batch_id == "BATCH-001"
        assert r.folio == "PROD-20260101-001"

    def test_cerrar_lote_fallo_engine_retorna_error(self):
        eng = _make_engine(close_error=ValueError("lote no existe"))
        uc = _make_uc(engine=eng)
        r = uc.cerrar_lote(batch_id="BAD-ID", sucursal_id=1, usuario="jefe")
        assert r.ok is False
        assert "lote no existe" in r.error

    def test_cerrar_lote_publica_produccion_completada(self):
        bus = MagicMock()
        eng = _make_engine(rendimiento=80.0, movimientos=2)
        uc = _make_uc(engine=eng, event_bus=bus)
        uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="chef")
        bus.publish.assert_called_once()
        event_name = bus.publish.call_args.args[0]
        assert event_name == "PRODUCCION_COMPLETADA"

    def test_cerrar_lote_payload_tiene_campos_requeridos(self):
        bus = MagicMock()
        eng = _make_engine(rendimiento=70.0)
        uc = _make_uc(engine=eng, event_bus=bus)
        uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=2, usuario="planta")
        payload = bus.publish.call_args.args[1]
        assert "batch_id" in payload
        assert "folio" in payload
        assert "rendimiento_pct" in payload
        assert "sucursal_id" in payload
        assert payload["sucursal_id"] == 2

    def test_cerrar_lote_sin_bus_no_falla(self):
        eng = _make_engine()
        uc = _make_uc(engine=eng, event_bus=None)
        r = uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="jefe")
        assert r.ok is True

    def test_cerrar_lote_fallo_bus_no_propaga(self):
        bus = MagicMock()
        bus.publish.side_effect = RuntimeError("bus down")
        eng = _make_engine()
        uc = _make_uc(engine=eng, event_bus=bus)
        r = uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="jefe")
        assert r.ok is True

    def test_cerrar_lote_sin_yield_result_retorna_cero(self):
        eng = MagicMock()
        eng.close_batch.return_value = _FakeBatchResult(
            batch_id="BATCH-001",
            folio="PROD-001",
            yield_result=None,
            inventory_movements=1,
        )
        uc = _make_uc(engine=eng)
        r = uc.cerrar_lote(batch_id="BATCH-001", sucursal_id=1, usuario="jefe")
        assert r.ok is True
        assert r.rendimiento_pct == pytest.approx(0.0)
