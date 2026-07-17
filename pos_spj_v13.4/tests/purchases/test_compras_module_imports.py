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
        # PUR-13: modulos/compras_pro.py eliminado; Compras es el módulo enterprise.
        "modulos/compras_enterprise.py",
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
    # PUR-13: el monolito fue eliminado; Compras es el módulo enterprise canónico.
    module = _import_or_skip("modulos.compras_enterprise")
    assert hasattr(module, "ModuloComprasEnterprise")


def test_recepcion_qr_widget_importa_sin_tocar_motor_qr():
    module = _import_or_skip("modulos.recepcion_qr_widget")
    assert hasattr(module, "RecepcionQRWidget")


def test_monolito_compras_pro_eliminado():
    """PUR-13: el monolito compras_pro.py ya no existe (fue eliminado, no wrappeado)."""
    assert not (ROOT / "modulos" / "compras_pro.py").exists()
    assert not (ROOT / "modulos" / "compras").exists()
