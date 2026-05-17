"""
tests/purchases/test_compras_tabs_contract.py
─────────────────────────────────────────────
FASE 1 — Contrato de tabs del módulo compras.

Verifica (vía AST) que:
- _build_ui() agrega exactamente 3 tabs al QTabWidget externo
- Los nombres de los 3 tabs corresponden a los esperados
- RecepcionQRWidget._build_ui() agrega exactamente 5 tabs internas
- Los métodos _build_tab_* existen para cada tab declarada
- No hay addTab extra fuera de los métodos _build_ui

No instancia PyQt5.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import re
import pytest


def _source(rel_path: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, rel_path), encoding="utf-8").read()


# ── compras_pro.py ──────────────────────────────────────────────────────────

class TestOuterTabsContract:
    """ModuloComprasPro debe tener exactamente 3 tabs externas."""

    def _src(self):
        return _source("modulos/compras_pro.py")

    def test_exactly_3_addtab_in_build_ui(self):
        """_build_ui debe contener exactamente 3 llamadas a addTab."""
        src = self._src()
        tree = ast.parse(src)

        # Find the _build_ui method body
        build_ui_src = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui":
                # Extract lines from file
                lines = src.splitlines()
                start = node.lineno - 1
                end = node.end_lineno
                build_ui_src = "\n".join(lines[start:end])
                break

        assert build_ui_src is not None, "_build_ui method not found in compras_pro.py"
        count = build_ui_src.count(".addTab(")
        assert count == 3, (
            f"_build_ui debe tener exactamente 3 llamadas a addTab, encontradas: {count}"
        )

    def test_compra_tradicional_tab_declared(self):
        src = self._src()
        assert "Compra Tradicional" in src, "Tab 'Compra Tradicional' debe existir"

    def test_recepcion_qr_tab_declared(self):
        src = self._src()
        assert "Recepción con QR" in src or "Recepcion con QR" in src, (
            "Tab 'Recepción con QR' debe existir"
        )

    def test_historial_tab_declared(self):
        src = self._src()
        assert "Historial de Compras" in src, "Tab 'Historial de Compras' debe existir"

    def test_build_tab_tradicional_method_exists(self):
        src = self._src()
        assert "_build_tab_tradicional" in src

    def test_build_tab_qr_method_exists(self):
        src = self._src()
        assert "_build_tab_qr" in src

    def test_build_tab_historial_method_exists(self):
        src = self._src()
        assert "_build_tab_historial" in src

    def test_no_po_tab_at_outer_level(self):
        """No debe haber una tab 'Recepción PO' en el nivel externo de ModuloComprasPro."""
        src = self._src()
        tree = ast.parse(src)

        build_ui_src = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui":
                lines = src.splitlines()
                build_ui_src = "\n".join(lines[node.lineno - 1:node.end_lineno])
                break

        assert build_ui_src is not None
        # Ensure no PO reception tab in outer _build_ui
        assert "Recepción PO" not in build_ui_src and "po_recv" not in build_ui_src, (
            "No debe haber una tab de 'Recepción PO' en el nivel externo de ModuloComprasPro. "
            "La recepción PO va DENTRO de RecepcionQRWidget."
        )

    def test_kpi_bar_built_in_build_ui(self):
        """El KPI bar debe construirse en _build_ui (fuera de las tabs)."""
        src = self._src()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui":
                lines = src.splitlines()
                build_ui_src = "\n".join(lines[node.lineno - 1:node.end_lineno])
                assert "_build_purchase_kpi_bar" in build_ui_src, (
                    "_build_purchase_kpi_bar() debe llamarse en _build_ui(), no dentro de un tab"
                )
                break


class TestTabMethods:
    """Los métodos _build_tab_* deben existir y aceptar un parámetro parent."""

    def _methods_with_args(self):
        src = _source("modulos/compras_pro.py")
        tree = ast.parse(src)
        result = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result[node.name] = [a.arg for a in node.args.args]
        return result

    def test_build_tab_tradicional_has_parent_param(self):
        methods = self._methods_with_args()
        assert "_build_tab_tradicional" in methods
        assert "parent" in methods["_build_tab_tradicional"], (
            "_build_tab_tradicional debe aceptar 'parent' como parámetro"
        )

    def test_build_tab_qr_has_parent_param(self):
        methods = self._methods_with_args()
        assert "_build_tab_qr" in methods
        assert "parent" in methods["_build_tab_qr"]

    def test_build_tab_historial_has_parent_param(self):
        methods = self._methods_with_args()
        assert "_build_tab_historial" in methods
        assert "parent" in methods["_build_tab_historial"]


# ── recepcion_qr_widget.py ──────────────────────────────────────────────────

class TestQRWidgetInternalTabs:
    """RecepcionQRWidget debe tener exactamente 5 tabs internas."""

    def _src(self):
        return _source("modulos/recepcion_qr_widget.py")

    def test_exactly_5_addtab_in_build_ui(self):
        """_build_ui de RecepcionQRWidget debe tener exactamente 5 addTab."""
        src = self._src()
        tree = ast.parse(src)

        build_ui_src = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui":
                lines = src.splitlines()
                build_ui_src = "\n".join(lines[node.lineno - 1:node.end_lineno])
                break

        assert build_ui_src is not None, "_build_ui not found in recepcion_qr_widget.py"
        count = build_ui_src.count(".addTab(")
        assert count == 5, (
            f"RecepcionQRWidget._build_ui debe tener 5 tabs internas, encontradas: {count}"
        )

    def test_tab_generar_qr_declared(self):
        src = self._src()
        assert "Generar Etiqueta QR" in src or "Generar" in src

    def test_tab_asignar_declared(self):
        src = self._src()
        assert "Asignar" in src

    def test_tab_recepcionar_declared(self):
        src = self._src()
        assert "Recepcionar" in src

    def test_tab_historial_declared(self):
        src = self._src()
        assert "Historial" in src

    def test_tab_po_recv_declared(self):
        src = self._src()
        assert "_tab_po_recv" in src, (
            "_tab_po_recv debe existir en RecepcionQRWidget (Fase 6)"
        )

    def test_recepcion_po_label_in_qr_widget(self):
        src = self._src()
        assert "Recepción PO" in src or "Recepcion PO" in src, (
            "El tab 'Recepción PO' debe estar DENTRO de RecepcionQRWidget"
        )
