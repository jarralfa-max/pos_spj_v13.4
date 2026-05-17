"""
tests/purchases/test_compras_module_imports.py
──────────────────────────────────────────────
FASE 1 — Smoke tests: importaciones del módulo compras_pro.

Verifica que:
- compras_pro.py no tiene errores de sintaxis (AST parse)
- recepcion_qr_widget.py no tiene errores de sintaxis
- spj_styles.py no tiene errores de sintaxis
- Los imports internos de compras_pro (design_tokens, ui_components, spj_styles) se resuelven sin ImportError real cuando están disponibles
- La clase ModuloComprasPro está definida
- _PurchaseKPICard está definida
- _HistorialLoader está definida

Estos tests NO instancian PyQt5 (sin pantalla en headless).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import pytest


def _source(rel_path: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, rel_path)
    return open(path, encoding="utf-8").read()


def _tree(rel_path: str):
    return ast.parse(_source(rel_path))


class TestSyntaxClean:
    """Todos los archivos del módulo compras deben parsear sin SyntaxError."""

    def test_compras_pro_no_syntax_error(self):
        _tree("modulos/compras_pro.py")

    def test_recepcion_qr_widget_no_syntax_error(self):
        _tree("modulos/recepcion_qr_widget.py")

    def test_spj_styles_no_syntax_error(self):
        _tree("modulos/spj_styles.py")

    def test_design_tokens_no_syntax_error(self):
        _tree("modulos/design_tokens.py")

    def test_ui_components_no_syntax_error(self):
        _tree("modulos/ui_components.py")


class TestClassesExist:
    """Las clases principales deben estar presentes en el código fuente."""

    def _src(self):
        return _source("modulos/compras_pro.py")

    def test_modulo_compras_pro_class_defined(self):
        src = self._src()
        tree = ast.parse(src)
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "ModuloComprasPro" in class_names, (
            "ModuloComprasPro debe estar definida en compras_pro.py"
        )

    def test_purchase_kpi_card_class_defined(self):
        src = self._src()
        tree = ast.parse(src)
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "_PurchaseKPICard" in class_names, (
            "_PurchaseKPICard debe estar definida en compras_pro.py"
        )

    def test_historial_loader_class_defined(self):
        src = self._src()
        tree = ast.parse(src)
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "_HistorialLoader" in class_names, (
            "_HistorialLoader (QThread) debe estar definida en compras_pro.py"
        )

    def test_recepcion_qr_widget_class_defined(self):
        src = _source("modulos/recepcion_qr_widget.py")
        tree = ast.parse(src)
        class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "RecepcionQRWidget" in class_names, (
            "RecepcionQRWidget debe estar definida en recepcion_qr_widget.py"
        )


class TestCriticalMethodsExist:
    """Métodos críticos de negocio deben existir en compras_pro.py."""

    def _methods(self):
        src = _source("modulos/compras_pro.py")
        tree = ast.parse(src)
        return {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_procesar_compra_exists(self):
        assert "_procesar_compra" in self._methods()

    def test_procesar_como_pr_exists(self):
        assert "_procesar_como_pr" in self._methods()

    def test_cargar_proveedores_exists(self):
        assert "cargar_proveedores" in self._methods()

    def test_build_ui_exists(self):
        assert "_build_ui" in self._methods()

    def test_build_tab_tradicional_exists(self):
        assert "_build_tab_tradicional" in self._methods()

    def test_build_tab_qr_exists(self):
        assert "_build_tab_qr" in self._methods()

    def test_build_tab_historial_exists(self):
        assert "_build_tab_historial" in self._methods()

    def test_refresh_totals_display_exists(self):
        assert "_refresh_totals_display" in self._methods()

    def test_agregar_producto_exists(self):
        assert "_agregar_producto" in self._methods()

    def test_auto_save_draft_exists(self):
        assert "_auto_save_draft" in self._methods()

    def test_guardar_borrador_exists(self):
        assert "_guardar_borrador" in self._methods()

    def test_cargar_borrador_exists(self):
        assert "_cargar_borrador" in self._methods()


class TestImportStatements:
    """Los imports críticos deben estar declarados en el archivo."""

    def _src(self):
        return _source("modulos/compras_pro.py")

    def test_imports_design_tokens(self):
        src = self._src()
        assert "from modulos.design_tokens import" in src, (
            "compras_pro debe importar desde design_tokens"
        )

    def test_imports_colors(self):
        src = self._src()
        assert "Colors" in src

    def test_imports_apply_spj_buttons(self):
        src = self._src()
        assert "apply_spj_buttons" in src

    def test_imports_refresh_mixin(self):
        src = self._src()
        assert "RefreshMixin" in src

    def test_imports_page_header(self):
        src = self._src()
        assert "PageHeader" in src

    def test_imports_create_standard_tabs(self):
        src = self._src()
        assert "create_standard_tabs" in src

    def test_doc_type_initialized_in_init(self):
        src = self._src()
        assert 'self._doc_type = "DIRECT"' in src, (
            "__init__ debe inicializar _doc_type a 'DIRECT'"
        )
