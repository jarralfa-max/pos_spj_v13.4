from __future__ import annotations

import importlib
import py_compile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_UI = ROOT / "modulos/productos.py"


def test_products_module_compiles_and_declares_required_dependencies() -> None:
    py_compile.compile(str(PRODUCTS_UI), doraise=True)
    source = PRODUCTS_UI.read_text(encoding="utf-8")
    for name in (
        "ProductQueryService",
        "ProductCatalogService",
        "ProductImageService",
        "DeactivateProductUseCase",
        "RestoreProductUseCase",
    ):
        assert name in source
    assert "ProductCatalogService(repository=" not in source


def test_products_module_imports_when_qt_runtime_available() -> None:
    try:
        module = importlib.import_module("modulos.productos")
    except ImportError as exc:
        message = str(exc)
        if "libGL.so.1" in message or "PyQt5" in message:
            pytest.skip(f"PyQt5 runtime dependency unavailable: {exc}")
        raise

    assert module.ModuloProductos is not None
    assert module.DialogoProducto is not None
    assert module.ProductQueryService is not None
    assert module.ProductCatalogService is not None
    assert module.DeactivateProductUseCase is not None
    assert module.RestoreProductUseCase is not None
