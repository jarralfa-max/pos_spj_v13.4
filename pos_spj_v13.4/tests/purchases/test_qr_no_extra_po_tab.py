"""
tests/purchases/test_qr_no_extra_po_tab.py
────────────────────────────────────────────
FASE 1 — Política QR NO-TOUCH: no 4ª tab externa de PO Reception.

Garantiza que:
- ModuloComprasPro tiene EXACTAMENTE 3 tabs externas
- No existe una tab "PO" ni "Recepción PO" en el nivel de ModuloComprasPro
- La recepción PO existe SOLO dentro de RecepcionQRWidget
- Los nombres de los 3 tabs externos son los canónicos

Si alguno de estos tests falla, alguien agregó una 4ª tab externa (error de arquitectura).

No instancia PyQt5.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import pytest


def _source(rel_path: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, rel_path), encoding="utf-8").read()


def _get_method_source(src: str, method_name: str) -> str | None:
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return None


class TestOuterTabsCountIs3:
    """La regla más importante: exactamente 3 tabs en el nivel externo."""

    def test_outer_tabs_count_is_exactly_3(self):
        """ModuloComprasPro._build_ui debe tener exactamente 3 addTab calls."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None, "_build_ui no encontrado en compras_pro.py"
        count = method_src.count(".addTab(")
        assert count == 3, (
            f"VIOLACIÓN DE ARQUITECTURA: ModuloComprasPro tiene {count} tabs externas, "
            f"debe tener exactamente 3. "
            f"La Recepción PO va DENTRO de RecepcionQRWidget, no al nivel externo."
        )

    def test_outer_tab_0_is_compra_tradicional(self):
        """Primer tab debe ser 'Compra Tradicional'."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        assert "Compra Tradicional" in method_src, (
            "El primer tab externo debe ser 'Compra Tradicional'"
        )

    def test_outer_tab_1_is_recepcion_qr(self):
        """Segundo tab debe ser 'Recepción con QR'."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        assert "Recepci" in method_src and "QR" in method_src, (
            "El segundo tab externo debe ser 'Recepción con QR'"
        )

    def test_outer_tab_2_is_historial(self):
        """Tercer tab debe ser 'Historial de Compras'."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        assert "Historial" in method_src, (
            "El tercer tab externo debe ser 'Historial de Compras'"
        )


class TestNoFourthPOTabInOuterModule:
    """No debe existir ninguna variante de tab PO al nivel externo."""

    def test_no_po_reception_tab_in_build_ui(self):
        """No 'Recepción PO' ni '_tab_po_recv' en _build_ui de ModuloComprasPro."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        assert "_tab_po_recv" not in method_src, (
            "_tab_po_recv no debe aparecer en _build_ui de ModuloComprasPro. "
            "Este widget pertenece al interior de RecepcionQRWidget."
        )

    def test_no_recepcion_po_addtab_in_compras_pro_build_ui(self):
        """La cadena 'Recepción PO' no debe pasarse a addTab en _build_ui externo."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        # Check that no addTab call passes a string with "PO" in the outer _build_ui
        import re
        addtab_calls = re.findall(r'\.addTab\([^)]+\)', method_src)
        for call in addtab_calls:
            assert "PO" not in call or "QR" in call or "Recepci" not in call, (
                f"addTab con 'PO' encontrado en _build_ui externo: {call}. "
                f"La tab PO va dentro de RecepcionQRWidget."
            )


class TestPOTabIsInsideQRWidget:
    """La tab PO debe existir DENTRO de RecepcionQRWidget."""

    def test_tab_po_recv_exists_in_qr_widget(self):
        """_tab_po_recv debe estar declarado en recepcion_qr_widget.py."""
        src = _source("modulos/recepcion_qr_widget.py")
        assert "_tab_po_recv" in src, (
            "_tab_po_recv no encontrado en recepcion_qr_widget.py. "
            "La Recepción PO (Fase 6) debe estar dentro del widget QR."
        )

    def test_po_recepcion_addtab_in_qr_widget_build_ui(self):
        """RecepcionQRWidget._build_ui debe contener el addTab para Recepción PO."""
        src = _source("modulos/recepcion_qr_widget.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None, "_build_ui no encontrado en recepcion_qr_widget.py"
        assert "_tab_po_recv" in method_src, (
            "addTab con _tab_po_recv no encontrado en RecepcionQRWidget._build_ui"
        )

    def test_build_tab_po_recepcion_method_exists(self):
        """El método _build_tab_po_recepcion debe existir en RecepcionQRWidget."""
        src = _source("modulos/recepcion_qr_widget.py")
        assert "_build_tab_po_recepcion" in src, (
            "_build_tab_po_recepcion no encontrado en recepcion_qr_widget.py"
        )

    def test_qr_widget_has_exactly_5_internal_tabs(self):
        """RecepcionQRWidget._build_ui tiene exactamente 5 tabs."""
        src = _source("modulos/recepcion_qr_widget.py")
        method_src = _get_method_source(src, "_build_ui")
        assert method_src is not None
        count = method_src.count(".addTab(")
        assert count == 5, (
            f"RecepcionQRWidget debe tener 5 tabs internas, encontradas: {count}. "
            f"Tabs esperadas: Generar QR, Asignar, Recepcionar, Historial, Recepción PO"
        )


class TestArchitectureIntegrity:
    """Tests de integridad arquitectural del módulo."""

    def test_recepcion_qr_widget_imported_in_build_tab_qr(self):
        """RecepcionQRWidget debe importarse DENTRO de _build_tab_qr (lazy import)."""
        src = _source("modulos/compras_pro.py")
        method_src = _get_method_source(src, "_build_tab_qr")
        assert method_src is not None, "_build_tab_qr no encontrado"
        assert "RecepcionQRWidget" in method_src, (
            "RecepcionQRWidget debe instanciarse dentro de _build_tab_qr"
        )

    def test_no_qr_motor_import_at_module_level(self):
        """El motor QR no debe importarse al nivel de módulo en compras_pro.py."""
        src = _source("modulos/compras_pro.py")
        # Check top-level imports (before any function/class definition)
        lines = src.splitlines()
        top_level_imports = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class ") or stripped.startswith("def "):
                break
            if "qr_service" in stripped.lower() or "recepcion_qr" in stripped.lower():
                top_level_imports.append(stripped)
        assert len(top_level_imports) == 0, (
            f"El motor QR no debe importarse al nivel de módulo: {top_level_imports}"
        )
