"""FASE 1 — Estabilización: pruebas de importación.

Cada archivo bajo frontend/desktop/modules/purchasing/ debe poder importarse
de forma aislada (sin construir widgets, sin conexión ni QApplication) — esto
detecta imports rotos, clases/constructores duplicados, variables no
definidas a nivel de módulo y firmas incompatibles en tiempo de import, que es
exactamente la clase de defecto que dejó a Compras sin poder abrir
(ver migrations/MIGRATION_LOG.md, document_detail.py / enterprise_routes.py /
purchasing_module_shell.py)."""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "frontend" / "desktop" / "modules" / "purchasing"
PACKAGE_PREFIX = "frontend.desktop.modules.purchasing"


def _module_names() -> list[str]:
    names = [PACKAGE_PREFIX]
    for info in pkgutil.walk_packages([str(PACKAGE_ROOT)], prefix=f"{PACKAGE_PREFIX}."):
        names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", _module_names())
def test_every_purchasing_module_imports_cleanly(module_name):
    importlib.import_module(module_name)


def test_no_duplicate_top_level_class_or_function_definitions():
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        seen: dict[str, int] = {}
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                seen[node.name] = seen.get(node.name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT.parents[3])}: {name} x{count}")
    assert not offenders, "Definiciones duplicadas a nivel de módulo:\n" + "\n".join(offenders)


def test_no_duplicate_methods_within_a_class():
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            seen: dict[str, int] = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    seen[item.name] = seen.get(item.name, 0) + 1
            for name, count in seen.items():
                if count > 1:
                    offenders.append(
                        f"{path.relative_to(PACKAGE_ROOT.parents[3])}: {node.name}.{name} x{count}")
    assert not offenders, "Métodos duplicados dentro de una clase:\n" + "\n".join(offenders)


def test_enterprise_and_direct_purchase_composition_roots_are_importable():
    """The exact entry points main_window/compras_enterprise depend on."""
    from frontend.desktop.modules.purchasing.enterprise_routes import (
        build_enterprise_presenter,
        create_enterprise_purchasing_view,
    )
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseCreateView,
        DirectPurchaseHistoryView,
    )
    from frontend.desktop.modules.purchasing.purchasing_module_shell import (
        PurchasingModuleShell,
    )
    from frontend.desktop.modules.purchasing.document_detail import (
        OrderDetailPanel,
        RequisitionDetailPanel,
    )

    assert callable(create_enterprise_purchasing_view)
    assert callable(build_enterprise_presenter)
    assert callable(build_direct_purchase_presenter)
    assert callable(DirectPurchaseCreateView) and callable(DirectPurchaseHistoryView)
    assert callable(PurchasingModuleShell)
    assert callable(OrderDetailPanel) and callable(RequisitionDetailPanel)
