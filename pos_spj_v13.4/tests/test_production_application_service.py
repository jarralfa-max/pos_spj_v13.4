"""
tests/test_production_application_service.py — FASE 7

Verifica que ProductionApplicationService:
  - Delegaciones de receta: ejecutar_receta, preview_receta, get_historial, get_detalle
  - Delegaciones de lote:   abrir_lote, agregar_subproducto, remover_subproducto,
                             cerrar_lote, cancelar_lote, preview_lote
  - Delegaciones de consulta: get_batches, get_batch_detail
  - from_container() construye correctamente desde AppContainer mock
  - Errores apropiados cuando engine/uc no disponible
  - Ninguna lógica de negocio duplicada — solo delegación
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.production_application_service import ProductionApplicationService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def recipe():
    m = MagicMock()
    m.ejecutar_produccion = MagicMock(return_value="result_dto")
    m.preview_produccion  = MagicMock(return_value=[{"delta": -10.0}])
    m.get_historial       = MagicMock(return_value=[{"id": 1}])
    m.get_detalle_produccion = MagicMock(return_value=[{"producto_id": 2}])
    return m


@pytest.fixture()
def uc():
    m = MagicMock()
    m.abrir_lote  = MagicMock(return_value=MagicMock(ok=True, batch_id="B1"))
    m.cerrar_lote = MagicMock(return_value=MagicMock(ok=True))
    return m


@pytest.fixture()
def engine():
    m = MagicMock()
    m.add_output    = MagicMock(return_value=MagicMock(output_id="O1"))
    m.remove_output = MagicMock()
    m.preview_batch = MagicMock(return_value=MagicMock(usable_pct=85.0))
    m.cancel_batch  = MagicMock()
    m.get_batches   = MagicMock(return_value=[{"id": "B1"}])
    m.get_batch_detail = MagicMock(return_value={"batch": {"id": "B1"}})
    return m


@pytest.fixture()
def svc(recipe, uc, engine):
    return ProductionApplicationService(
        recipe_engine=recipe,
        production_uc=uc,
        production_engine=engine,
    )


# ── Recipe delegation ─────────────────────────────────────────────────────────

class TestRecipeDelegation:

    def test_ejecutar_receta_delegates_all_args(self, svc, recipe):
        svc.ejecutar_receta(
            receta_id=5, cantidad_base=20.0, usuario="juan",
            sucursal_id=1, notas="test", operation_id="OP1",
            mediciones_reales={2: 12.5},
        )
        recipe.ejecutar_produccion.assert_called_once_with(
            receta_id=5,
            cantidad_base=20.0,
            usuario="juan",
            sucursal_id=1,
            notas="test",
            operation_id="OP1",
            mediciones_reales={2: 12.5},
        )

    def test_ejecutar_receta_returns_engine_result(self, svc):
        assert svc.ejecutar_receta(1, 10.0, "u", sucursal_id=1) == "result_dto"

    def test_preview_receta_delegates(self, svc, recipe):
        result = svc.preview_receta(receta_id=3, cantidad_base=5.0)
        recipe.preview_produccion.assert_called_once_with(3, 5.0)
        assert result == [{"delta": -10.0}]

    def test_get_historial_delegates(self, svc, recipe):
        svc.get_historial(sucursal_id=2, receta_id=7, limit=50)
        recipe.get_historial.assert_called_once_with(
            sucursal_id=2, receta_id=7, limit=50
        )

    def test_get_historial_defaults(self, svc, recipe):
        svc.get_historial()
        recipe.get_historial.assert_called_once_with(
            sucursal_id=None, receta_id=None, limit=100
        )

    def test_get_detalle_delegates(self, svc, recipe):
        result = svc.get_detalle(42)
        recipe.get_detalle_produccion.assert_called_once_with(42)
        assert result == [{"producto_id": 2}]

    def test_engine_exception_propagates(self, svc, recipe):
        recipe.ejecutar_produccion.side_effect = ValueError("sin stock")
        with pytest.raises(ValueError, match="sin stock"):
            svc.ejecutar_receta(1, 1.0, "u", sucursal_id=1)


# ── Batch lifecycle delegation ────────────────────────────────────────────────

class TestBatchDelegation:

    def test_abrir_lote_delegates(self, svc, uc):
        svc.abrir_lote(
            producto_origen_id=1, peso_kg=100.0,
            sucursal_id=1, usuario="op", receta_id=3,
        )
        uc.abrir_lote.assert_called_once_with(
            producto_origen_id=1,
            peso_kg=100.0,
            sucursal_id=1,
            usuario="op",
            receta_id=3,
        )

    def test_abrir_lote_returns_uc_result(self, svc):
        r = svc.abrir_lote(1, 50.0, 1, "op")
        assert r.batch_id == "B1"

    def test_agregar_subproducto_delegates(self, svc, engine):
        svc.agregar_subproducto(
            batch_id="B1", producto_id=2,
            peso_kg=60.0, expected_pct=70.0, is_waste=False,
        )
        engine.add_output.assert_called_once_with(
            batch_id="B1", product_id=2,
            weight=60.0, expected_pct=70.0, is_waste=False,
        )

    def test_remover_subproducto_delegates(self, svc, engine):
        svc.remover_subproducto(batch_id="B1", producto_id=2)
        engine.remove_output.assert_called_once_with(batch_id="B1", product_id=2)

    def test_cerrar_lote_delegates(self, svc, uc):
        svc.cerrar_lote(batch_id="B1", sucursal_id=1, usuario="op")
        uc.cerrar_lote.assert_called_once_with(
            batch_id="B1", sucursal_id=1, usuario="op"
        )

    def test_cancelar_lote_delegates(self, svc, engine):
        svc.cancelar_lote(batch_id="B1", usuario="op", motivo="error")
        engine.cancel_batch.assert_called_once_with(
            batch_id="B1", cancelled_by="op", motivo="error"
        )

    def test_preview_lote_delegates(self, svc, engine):
        r = svc.preview_lote("B1")
        engine.preview_batch.assert_called_once_with("B1")
        assert r.usable_pct == 85.0


# ── Query delegation ──────────────────────────────────────────────────────────

class TestQueryDelegation:

    def test_get_batches_delegates(self, svc, engine):
        result = svc.get_batches(branch_id=1, estado="cerrado", limit=50)
        engine.get_batches.assert_called_once_with(
            branch_id=1, estado="cerrado",
            fecha_desde="", fecha_hasta="", limit=50,
        )
        assert result == [{"id": "B1"}]

    def test_get_batches_returns_empty_when_no_engine(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, production_engine=None)
        assert svc.get_batches() == []

    def test_get_batch_detail_delegates(self, svc, engine):
        r = svc.get_batch_detail("B1")
        engine.get_batch_detail.assert_called_once_with("B1")
        assert r == {"batch": {"id": "B1"}}

    def test_get_batch_detail_empty_when_no_engine(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, production_engine=None)
        assert svc.get_batch_detail("X") == {}


# ── Error handling when deps missing ─────────────────────────────────────────

class TestMissingDependencies:

    def test_abrir_lote_raises_when_uc_none(self, recipe, engine):
        svc = ProductionApplicationService(recipe, None, engine)
        with pytest.raises(RuntimeError, match="uc_produccion"):
            svc.abrir_lote(1, 10.0, 1, "op")

    def test_cerrar_lote_raises_when_uc_none(self, recipe, engine):
        svc = ProductionApplicationService(recipe, None, engine)
        with pytest.raises(RuntimeError, match="uc_produccion"):
            svc.cerrar_lote("B1", 1, "op")

    def test_agregar_subproducto_raises_when_engine_none(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, None)
        with pytest.raises(RuntimeError, match="production_engine"):
            svc.agregar_subproducto("B1", 2, 10.0)

    def test_remover_raises_when_engine_none(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, None)
        with pytest.raises(RuntimeError, match="production_engine"):
            svc.remover_subproducto("B1", 2)

    def test_cancelar_lote_raises_when_engine_none(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, None)
        with pytest.raises(RuntimeError, match="production_engine"):
            svc.cancelar_lote("B1", "op")

    def test_preview_lote_raises_when_engine_none(self, recipe, uc):
        svc = ProductionApplicationService(recipe, uc, None)
        with pytest.raises(RuntimeError, match="production_engine"):
            svc.preview_lote("B1")


# ── from_container factory ────────────────────────────────────────────────────

class TestFromContainer:

    def _make_container(self):
        c = MagicMock()
        c.recipe_engine    = MagicMock()
        c.uc_produccion    = MagicMock()
        c.production_engine= MagicMock()
        return c

    def test_from_container_wires_recipe_engine(self):
        c = self._make_container()
        svc = ProductionApplicationService.from_container(c)
        assert svc._recipe is c.recipe_engine

    def test_from_container_wires_uc(self):
        c = self._make_container()
        svc = ProductionApplicationService.from_container(c)
        assert svc._uc is c.uc_produccion

    def test_from_container_wires_production_engine(self):
        c = self._make_container()
        svc = ProductionApplicationService.from_container(c)
        assert svc._engine is c.production_engine

    def test_from_container_production_engine_optional(self):
        c = MagicMock(spec=[])  # no attributes at all
        c.recipe_engine = MagicMock()
        c.uc_produccion = MagicMock()
        svc = ProductionApplicationService.from_container(c)
        assert svc._engine is None
