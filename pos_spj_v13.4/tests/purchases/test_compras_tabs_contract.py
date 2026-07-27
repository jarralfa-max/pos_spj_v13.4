"""FASE 1 — Contrato de tabs principales de Compras."""
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


def test_build_ui_tiene_exactamente_tres_tabs_principales():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    assert build_ui.count(".addTab(") == 3


def test_tabs_principales_son_las_tres_autorizadas():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    assert "Compra Tradicional" in build_ui
    assert "Recepción con QR" in build_ui or "Recepcion con QR" in build_ui
    assert "Historial de Compras" in build_ui


def test_no_existe_tab_principal_recepcion_po():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    forbidden = [
        "Recepción de PO",
        "Recepcion de PO",
        "Recepción PO",
        "Recepcion PO",
        "Recepción OC",
        "Recepcion OC",
        "PO Reception",
        "Recibir Orden",
    ]
    for label in forbidden:
        assert label not in build_ui


def test_recepcion_qr_se_monta_en_segunda_tab_principal():
    build_ui = _method_source("modulos/compras_pro.py", "_build_ui")
    build_qr = _method_source("modulos/compras_pro.py", "_build_tab_qr")
    assert "_build_tab_qr(tab_qr)" in build_ui
    assert "RecepcionQRWidget" in build_qr
    assert "wrap_in_scroll_area" in build_qr


def test_compra_tradicional_declara_tres_columnas_sin_redisenar():
    method = _method_source("modulos/compras_pro.py", "_build_tab_tradicional")
    assert "QSplitter" in method
    assert "_build_documental_toolbar" in method
    assert "_build_center_column" in method
    assert "_build_summary_panel" in method
    assert "splitter.setSizes" in method
