"""
FASE 1 — Smoke tests de importación para Compras.

Estos tests no cambian comportamiento: parsean/importan módulos críticos y
verifican que las clases/métodos base sigan presentes en la capa UI.
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _source(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _tree(rel_path: str) -> ast.Module:
    return ast.parse(_source(rel_path), filename=rel_path)


@pytest.mark.parametrize(
    "rel_path",
    [
        "modulos/compras_pro.py",
        "modulos/recepcion_qr_widget.py",
        "modulos/ui_components.py",
        "modulos/design_tokens.py",
        "core/services/purchase_service.py",
        "repositories/purchase_repository.py",
        "application/use_cases/registrar_compra_uc.py",
        "core/use_cases/compra.py",
    ],
)
def test_archivos_compras_parsean_sin_syntax_error(rel_path: str):
    _tree(rel_path)


def _import_or_skip(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        msg = str(exc)
        if "libGL.so.1" in msg or "PyQt5" in msg or "No module named" in msg:
            pytest.skip(f"PyQt5 runtime dependency unavailable in this environment: {exc}")
        raise


def test_modulo_compras_importa_y_expone_clase_principal():
    module = _import_or_skip("modulos.compras_pro")
    assert hasattr(module, "ModuloComprasPro")
    assert hasattr(module, "_PurchaseKPICard")


def test_recepcion_qr_widget_importa_sin_tocar_motor_qr():
    module = _import_or_skip("modulos.recepcion_qr_widget")
    assert hasattr(module, "RecepcionQRWidget")


def test_imports_runtime_criticos_estan_declarados():
    src = _source("modulos/compras_pro.py")
    assert "QInputDialog" in src, "QInputDialog debe estar importado para evitar NameError"
    assert "QScrollArea" in src, "QScrollArea debe estar importado para evitar NameError"
    assert "PageHeader" in src
    assert "create_standard_tabs" in src
    assert "wrap_in_scroll_area" in src


def test_metodos_criticos_de_ui_existen():
    tree = _tree("modulos/compras_pro.py")
    methods = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in {
        "_build_ui",
        "_build_tab_tradicional",
        "_build_tab_qr",
        "_build_tab_historial",
        "_build_purchase_kpi_bar",
        "_build_documental_toolbar",
        "_build_center_column",
        "_build_summary_panel",
        "_procesar_compra",
    }:
        assert name in methods
