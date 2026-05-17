"""FASE 1 — Smoke estructural de Compra Tradicional sin rediseño."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _source(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _method_source(rel_path: str, method_name: str) -> str:
    src = _source(rel_path)
    tree = ast.parse(src, filename=rel_path)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Método {method_name} no encontrado en {rel_path}")


def test_compra_tradicional_carga_layout_tres_columnas():
    method = _method_source("modulos/compras_pro.py", "_build_tab_tradicional")
    assert "_build_documental_toolbar" in method
    assert "_build_center_column" in method
    assert "_build_summary_panel" in method
    assert method.count("splitter.addWidget") == 3


def test_columna_derecha_contiene_partidas_totales_y_accion():
    method = _method_source("modulos/compras_pro.py", "_build_summary_panel")
    assert "_build_purchase_items_panel" in method
    assert "_build_purchase_totals_footer" in _source("modulos/compras_pro.py")
    assert "_build_dynamic_action_button" in _source("modulos/compras_pro.py")
    assert "_btn_autorizar" in method or "_build_dynamic_action_button" in method


def test_tabla_partidas_declara_columnas_minimas_del_contrato():
    method = _method_source("modulos/compras_pro.py", "_build_purchase_items_panel")
    for label in ["SKU/ID", "Producto", "Cant./UM", "Peso Est.", "Costo", "Subtotal"]:
        assert label in method
    assert "self.tabla.setObjectName(\"tableView\")" in method


def test_compra_directa_delega_a_registrar_compra_uc():
    method = _method_source("modulos/compras_pro.py", "_procesar_compra")
    assert "RegistrarCompraUC" in method
    assert "execute" in method


def test_pr_no_debe_validarse_en_fase1_como_implementacion_final():
    """Caracterización: Fase 1 no implementa PR/PO; solo asegura que existe ruta a separar."""
    src = _source("modulos/compras_pro.py")
    assert "_procesar_como_pr" in src
    assert "TraditionalPurchaseUC" in src
