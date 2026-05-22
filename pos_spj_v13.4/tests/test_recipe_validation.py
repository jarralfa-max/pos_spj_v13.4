"""
tests/test_recipe_validation.py — FASE 2 ERP Refactor

Verifica que RecipeValidationService aplica correctamente el mapa estricto:
    COMBINACION  →  tipo_producto 'compuesto'
    SUBPRODUCTO  →  tipo_producto 'procesable'
    PRODUCCION   →  tipo_producto 'producido'

Y que RecetaTypeError se lanza en todos los casos de incompatibilidad.
"""
from __future__ import annotations

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.recipes.recipe_validation_service import (
    RecipeValidationService,
    RecetaTypeError,
    RECETA_COMBINACION,
    RECETA_SUBPRODUCTO,
    RECETA_PRODUCCION,
)


svc = RecipeValidationService()


# ── Mapa correcto ─────────────────────────────────────────────────────────────

class TestValidTipoCombinations:

    def test_combinacion_compuesto_ok(self):
        svc.validate_tipo_receta_producto("COMBINACION", "compuesto")

    def test_subproducto_procesable_ok(self):
        svc.validate_tipo_receta_producto("SUBPRODUCTO", "procesable")

    def test_produccion_producido_ok(self):
        svc.validate_tipo_receta_producto("PRODUCCION", "producido")

    def test_case_insensitive_tipo_receta(self):
        svc.validate_tipo_receta_producto("combinacion", "compuesto")
        svc.validate_tipo_receta_producto("subproducto", "procesable")
        svc.validate_tipo_receta_producto("produccion",  "producido")

    def test_case_insensitive_tipo_producto(self):
        svc.validate_tipo_receta_producto("COMBINACION", "COMPUESTO")
        svc.validate_tipo_receta_producto("SUBPRODUCTO", "PROCESABLE")
        svc.validate_tipo_receta_producto("PRODUCCION",  "PRODUCIDO")


# ── Combinaciones inválidas — deben lanzar RecetaTypeError ───────────────────

class TestInvalidTipoCombinations:

    def test_combinacion_simple_raises(self):
        with pytest.raises(RecetaTypeError, match="compuesto"):
            svc.validate_tipo_receta_producto("COMBINACION", "simple")

    def test_combinacion_procesable_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("COMBINACION", "procesable")

    def test_combinacion_producido_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("COMBINACION", "producido")

    def test_subproducto_simple_raises(self):
        with pytest.raises(RecetaTypeError, match="procesable"):
            svc.validate_tipo_receta_producto("SUBPRODUCTO", "simple")

    def test_subproducto_compuesto_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("SUBPRODUCTO", "compuesto")

    def test_produccion_simple_raises(self):
        with pytest.raises(RecetaTypeError, match="producido"):
            svc.validate_tipo_receta_producto("PRODUCCION", "simple")

    def test_produccion_compuesto_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("PRODUCCION", "compuesto")

    def test_tipo_receta_desconocido_raises(self):
        with pytest.raises(RecetaTypeError, match="inválido"):
            svc.validate_tipo_receta_producto("RECETA_MAGICA", "compuesto")

    def test_tipo_receta_vacio_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("", "compuesto")

    def test_tipo_producto_vacio_raises(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_tipo_receta_producto("COMBINACION", "")


# ── Auto-referencia ───────────────────────────────────────────────────────────

class TestSelfReference:

    def test_self_reference_raises(self):
        with pytest.raises(RecetaTypeError, match="sí mismo"):
            svc.validate_no_self_reference(product_id=1, component_id=1)

    def test_different_ids_ok(self):
        svc.validate_no_self_reference(product_id=1, component_id=2)

    def test_zero_ids_are_same(self):
        with pytest.raises(RecetaTypeError):
            svc.validate_no_self_reference(product_id=0, component_id=0)


# ── Validación de porcentajes (COMBINACION) ───────────────────────────────────

class TestPercentageValidation:

    def test_suma_exacta_100_ok(self):
        svc.validate_percentages([
            {"porcentaje": 60.0},
            {"porcentaje": 40.0},
        ])

    def test_suma_100_con_tolerancia_ok(self):
        # 0.005 dentro del margen 0.01
        svc.validate_percentages([
            {"porcentaje": 60.003},
            {"porcentaje": 39.997},
        ])

    def test_suma_menor_100_raises(self):
        with pytest.raises(RecetaTypeError, match="100"):
            svc.validate_percentages([
                {"porcentaje": 50.0},
                {"porcentaje": 30.0},
            ])

    def test_suma_mayor_100_raises(self):
        with pytest.raises(RecetaTypeError, match="100"):
            svc.validate_percentages([
                {"porcentaje": 70.0},
                {"porcentaje": 40.0},
            ])

    def test_lista_vacia_ok(self):
        svc.validate_percentages([])


# ── Helpers de inferencia ─────────────────────────────────────────────────────

class TestInferenceHelpers:

    def test_infer_tipo_receta_from_compuesto(self):
        assert svc.infer_tipo_receta_from_producto("compuesto") == "COMBINACION"

    def test_infer_tipo_receta_from_procesable(self):
        assert svc.infer_tipo_receta_from_producto("procesable") == "SUBPRODUCTO"

    def test_infer_tipo_receta_from_producido(self):
        assert svc.infer_tipo_receta_from_producto("producido") == "PRODUCCION"

    def test_infer_tipo_receta_from_simple_returns_none(self):
        assert svc.infer_tipo_receta_from_producto("simple") is None

    def test_infer_tipo_receta_from_insumo_returns_none(self):
        assert svc.infer_tipo_receta_from_producto("insumo") is None

    def test_infer_tipo_producto_from_combinacion(self):
        assert svc.infer_tipo_producto_from_receta("COMBINACION") == "compuesto"

    def test_infer_tipo_producto_from_subproducto(self):
        assert svc.infer_tipo_producto_from_receta("SUBPRODUCTO") == "procesable"

    def test_infer_tipo_producto_from_produccion(self):
        assert svc.infer_tipo_producto_from_receta("PRODUCCION") == "producido"

    def test_infer_tipo_producto_unknown_returns_none(self):
        assert svc.infer_tipo_producto_from_receta("DESCONOCIDO") is None

    def test_product_can_have_recipe_compuesto(self):
        assert svc.product_can_have_recipe("compuesto") is True

    def test_product_can_have_recipe_procesable(self):
        assert svc.product_can_have_recipe("procesable") is True

    def test_product_can_have_recipe_producido(self):
        assert svc.product_can_have_recipe("producido") is True

    def test_product_cannot_have_recipe_simple(self):
        assert svc.product_can_have_recipe("simple") is False

    def test_product_cannot_have_recipe_insumo(self):
        assert svc.product_can_have_recipe("insumo") is False

    def test_product_cannot_have_recipe_servicio(self):
        assert svc.product_can_have_recipe("servicio") is False


# ── Constantes exportadas ─────────────────────────────────────────────────────

class TestExportedConstants:

    def test_receta_combinacion_value(self):
        assert RECETA_COMBINACION == "COMBINACION"

    def test_receta_subproducto_value(self):
        assert RECETA_SUBPRODUCTO == "SUBPRODUCTO"

    def test_receta_produccion_value(self):
        assert RECETA_PRODUCCION == "PRODUCCION"
