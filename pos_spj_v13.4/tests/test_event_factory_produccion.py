"""
tests/test_event_factory_produccion.py — FASE 8

Verifica que make_produccion_completada_payload():
  - Produce el esquema canónico con todas las claves esperadas
  - Dual-key sucursal_id/branch_id
  - costs siempre es un dict con las 3 claves
  - Valores por defecto razonables cuando no se pasan opcionales
  - Ambos publishers (RecipeEngine path y GestionarProduccionUC path)
    emiten el esquema normalizado
  - ProductionFinanceHandler lee costs del payload normalizado sin DB
  - ProductionFinanceHandler aún funciona con payload legacy (cost_allocations dict)
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.events.event_factory import make_produccion_completada_payload
from core.events.handlers.production_handler import ProductionFinanceHandler


# ── make_produccion_completada_payload ────────────────────────────────────────

class TestMakeProduccionCompletadaPayload:

    def _minimal(self, **kw):
        defaults = dict(
            folio="LT-001",
            operation_id="OP-1",
            sucursal_id=1,
            usuario="op",
        )
        defaults.update(kw)
        return make_produccion_completada_payload(**defaults)

    # Required structure
    def test_always_has_costs_dict(self):
        p = self._minimal()
        assert isinstance(p["costs"], dict)
        assert "raw_material_cost"   in p["costs"]
        assert "finished_goods_cost" in p["costs"]
        assert "waste_cost"          in p["costs"]

    def test_always_has_yields_dict(self):
        p = self._minimal()
        assert isinstance(p["yields"], dict)
        assert "total_generado"  in p["yields"]
        assert "total_consumido" in p["yields"]
        assert "total_merma"     in p["yields"]
        assert "usable_pct"      in p["yields"]
        assert "waste_pct"       in p["yields"]

    def test_always_has_raw_materials_and_outputs_lists(self):
        p = self._minimal()
        assert isinstance(p["raw_materials"], list)
        assert isinstance(p["outputs"],       list)

    # Dual-key compatibility
    def test_sucursal_id_and_branch_id_are_equal(self):
        p = self._minimal(sucursal_id=3)
        assert p["sucursal_id"] == 3
        assert p["branch_id"]   == 3

    # Identity keys
    def test_batch_id_and_produccion_id_default_none(self):
        p = self._minimal()
        assert p["batch_id"]      is None
        assert p["produccion_id"] is None

    def test_batch_path_sets_batch_id(self):
        p = self._minimal(batch_id="B-42")
        assert p["batch_id"] == "B-42"

    def test_recipe_path_sets_produccion_id(self):
        p = self._minimal(produccion_id=99)
        assert p["produccion_id"] == 99

    # Costs round-tripped correctly
    def test_costs_values_rounded(self):
        p = self._minimal(
            raw_material_cost=1000.12345678,
            finished_goods_cost=950.98765432,
            waste_cost=49.13579,
        )
        assert abs(p["costs"]["raw_material_cost"]   - 1000.1235) < 0.0001
        assert abs(p["costs"]["finished_goods_cost"] -  950.9877) < 0.0001
        assert abs(p["costs"]["waste_cost"]          -   49.1358) < 0.0001

    def test_zero_costs_by_default(self):
        p = self._minimal()
        assert p["costs"]["raw_material_cost"]   == 0.0
        assert p["costs"]["finished_goods_cost"] == 0.0
        assert p["costs"]["waste_cost"]          == 0.0

    # Yield rolled into yields dict
    def test_rendimiento_pct_in_yields(self):
        p = self._minimal(rendimiento_pct=82.5, waste_pct=5.0)
        assert p["yields"]["usable_pct"] == 82.5
        assert p["yields"]["waste_pct"]  == 5.0

    def test_total_yields_in_yields_dict(self):
        p = self._minimal(
            total_generado=18.0, total_consumido=20.0, total_merma=2.0
        )
        assert p["yields"]["total_generado"]  == 18.0
        assert p["yields"]["total_consumido"] == 20.0
        assert p["yields"]["total_merma"]     == 2.0

    # Movement lists passed through
    def test_raw_materials_and_outputs_passed_through(self):
        rm = [{"product_id": 1, "quantity": 20.0}]
        out = [{"product_id": 2, "quantity": 12.0, "is_waste": False}]
        p = self._minimal(raw_materials=rm, outputs=out)
        assert p["raw_materials"] == rm
        assert p["outputs"]       == out

    # Receta fields
    def test_receta_id_and_nombre(self):
        p = self._minimal(receta_id=5, receta_nombre="Despiece Pollo")
        assert p["receta_id"]    == 5
        assert p["receta_nombre"] == "Despiece Pollo"

    def test_folio_and_operation_id(self):
        p = self._minimal(folio="LT-999", operation_id="UUID-ABC")
        assert p["folio"]        == "LT-999"
        assert p["operation_id"] == "UUID-ABC"

    # Always has usuario
    def test_usuario_present(self):
        p = self._minimal(usuario="juan")
        assert p["usuario"] == "juan"


# ── ProductionFinanceHandler reads normalized payload costs ───────────────────

class TestFinanceHandlerUsesNormalizedPayload:

    def _finance(self):
        m = MagicMock()
        m.registrar_asiento = MagicMock()
        return m

    def test_reads_raw_cost_from_costs_dict(self):
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            "costs": {
                "raw_material_cost":   500.0,
                "finished_goods_cost": 450.0,
                "waste_cost":          50.0,
            },
        })
        calls = {c[1]["debe"]: c[1]["monto"]
                 for c in fin.registrar_asiento.call_args_list}
        assert abs(calls.get("7001-costo-materia-prima-consumida", 0) - 500.0) < 0.001

    def test_reads_finished_cost_from_costs_dict(self):
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            "costs": {
                "raw_material_cost":   500.0,
                "finished_goods_cost": 450.0,
                "waste_cost":          50.0,
            },
        })
        calls = {c[1]["debe"]: c[1]["monto"]
                 for c in fin.registrar_asiento.call_args_list}
        assert abs(calls.get("1202-inventario-productos-terminados", 0) - 450.0) < 0.001

    def test_reads_waste_cost_from_costs_dict(self):
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            "costs": {
                "raw_material_cost":   500.0,
                "finished_goods_cost": 450.0,
                "waste_cost":          50.0,
            },
        })
        calls = {c[1]["debe"]: c[1]["monto"]
                 for c in fin.registrar_asiento.call_args_list}
        assert abs(calls.get("7003-costo-merma-produccion", 0) - 50.0) < 0.001

    def test_zero_costs_dict_skips_gl(self):
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            "costs": {
                "raw_material_cost":   0.0,
                "finished_goods_cost": 0.0,
                "waste_cost":          0.0,
            },
        })
        fin.registrar_asiento.assert_not_called()

    def test_legacy_cost_allocations_dict_still_works(self):
        """Backward compat: old-style cost_allocations dict still processed."""
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            # No "costs" key — legacy format
            "cost_allocations": {
                "raw_material_cost":   300.0,
                "finished_goods_cost": 270.0,
            },
        })
        calls = {c[1]["debe"]: c[1]["monto"]
                 for c in fin.registrar_asiento.call_args_list}
        assert abs(calls.get("7001-costo-materia-prima-consumida", 0) - 300.0) < 0.001

    def test_integer_cost_allocations_silently_skipped(self):
        """Old integer cost_allocations=3 must not crash or produce wrong GL."""
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":        "B1",
            "folio":           "LT-1",
            "sucursal_id":     1,
            "cost_allocations": 3,   # old integer — no costs dict
        })
        fin.registrar_asiento.assert_not_called()

    def test_normalized_payload_takes_precedence_over_legacy(self):
        """costs dict (FASE 8) wins over cost_allocations dict (legacy)."""
        fin = self._finance()
        handler = ProductionFinanceHandler(finance_service=fin, db=None)
        handler.handle({
            "batch_id":    "B1",
            "folio":       "LT-1",
            "sucursal_id": 1,
            "costs": {
                "raw_material_cost":   100.0,
                "finished_goods_cost": 90.0,
                "waste_cost":          10.0,
            },
            "cost_allocations": {    # should be ignored
                "raw_material_cost":   999.0,
                "finished_goods_cost": 999.0,
            },
        })
        calls = {c[1]["debe"]: c[1]["monto"]
                 for c in fin.registrar_asiento.call_args_list}
        assert abs(calls["7001-costo-materia-prima-consumida"] - 100.0) < 0.001


# ── Schema completeness across both publishers ────────────────────────────────

class TestPayloadSchemaBothPaths:

    REQUIRED_KEYS = {
        "batch_id", "produccion_id", "folio", "operation_id",
        "sucursal_id", "branch_id", "usuario", "receta_id", "receta_nombre",
        "rendimiento_pct", "yields", "raw_materials", "outputs", "costs",
    }

    def test_batch_path_payload_has_all_required_keys(self):
        p = make_produccion_completada_payload(
            batch_id="B1", folio="LT-1", operation_id="OP",
            sucursal_id=1, usuario="op",
        )
        missing = self.REQUIRED_KEYS - set(p.keys())
        assert missing == set(), f"Missing keys: {missing}"

    def test_recipe_path_payload_has_all_required_keys(self):
        p = make_produccion_completada_payload(
            produccion_id=42, folio="REC-1", operation_id="OP",
            sucursal_id=1, usuario="op", receta_id=5, receta_nombre="Despiece",
        )
        missing = self.REQUIRED_KEYS - set(p.keys())
        assert missing == set(), f"Missing keys: {missing}"
