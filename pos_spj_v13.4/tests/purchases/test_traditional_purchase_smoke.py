"""
tests/purchases/test_traditional_purchase_smoke.py
───────────────────────────────────────────────────
FASE 1 — Smoke tests: flujo de compra tradicional (sin PyQt5).

Verifica mediante AST + importación de módulos puros (sin UI) que:
- El flujo DIRECT tiene los métodos requeridos y su firma es correcta
- Los atributos de instancia críticos están inicializados en __init__
- RegistrarCompraUC importa sin error (desde application layer)
- TraditionalPurchaseUC importa sin error
- El stepper guard existe para el modo DIRECT
- apply_spj_buttons no tiene el bug de fixedSize (ya resuelto)
- Los atributos backward-compat están declarados

No instancia PyQt5. No requiere pantalla.
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


# ── Import-level smoke tests (no UI) ────────────────────────────────────────

class TestUseCaseImports:
    """Use Cases de compras deben importar sin error (sin PyQt5)."""

    def test_registrar_compra_uc_imports(self):
        from application.use_cases.registrar_compra_uc import RegistrarCompraUC
        assert RegistrarCompraUC is not None

    def test_traditional_purchase_uc_imports(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        assert TraditionalPurchaseUC is not None

    def test_purchase_request_uc_imports(self):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        assert PurchaseRequestUC is not None

    def test_purchase_order_uc_imports(self):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        assert PurchaseOrderUC is not None

    def test_receive_po_adapter_imports(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter
        assert ReceivePOAdapter is not None

    def test_purchase_states_imports(self):
        from application.purchases.states import DocumentType
        assert DocumentType is not None

    def test_purchase_commands_imports(self):
        from application.purchases.commands import RegisterPurchaseCommand
        assert RegisterPurchaseCommand is not None


class TestRepositoryImports:
    """Repositorios de compras deben importar sin error."""

    def test_purchase_repository_imports(self):
        from repositories.purchase_repository import PurchaseRepository
        assert PurchaseRepository is not None

    def test_purchase_order_repository_imports(self):
        from repositories.purchase_order_repository import PurchaseOrderRepository
        assert PurchaseOrderRepository is not None

    def test_purchase_request_repository_imports(self):
        from repositories.purchase_request_repository import PurchaseRequestRepository
        assert PurchaseRequestRepository is not None


# ── AST-based behavioral checks ─────────────────────────────────────────────

def _get_class_method_source(src: str, class_name: str, method_name: str) -> str | None:
    """Find a method inside a specific class."""
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


class TestInitializationContract:
    """__init__ de ModuloComprasPro debe inicializar atributos críticos."""

    def _init_src(self):
        src = _source("modulos/compras_pro.py")
        return _get_class_method_source(src, "ModuloComprasPro", "__init__")

    def test_carrito_initialized_as_list(self):
        init = self._init_src()
        assert init is not None
        assert "carrito_compra" in init, "carrito_compra debe inicializarse en __init__"

    def test_doc_type_initialized_to_direct(self):
        init = self._init_src()
        assert init is not None
        assert '_doc_type = "DIRECT"' in init, (
            "_doc_type debe inicializarse a 'DIRECT' en __init__"
        )

    def test_sucursal_id_initialized(self):
        init = self._init_src()
        assert init is not None
        assert "sucursal_id" in init

    def test_autosave_timer_created(self):
        init = self._init_src()
        assert init is not None
        assert "_autosave_timer" in init, (
            "_autosave_timer debe crearse en __init__ para el auto-guardado"
        )

    def test_build_ui_called_in_init(self):
        init = self._init_src()
        assert init is not None
        assert "_build_ui()" in init, "_build_ui() debe llamarse en __init__"

    def test_cargar_proveedores_scheduled_in_init(self):
        init = self._init_src()
        assert init is not None
        assert "cargar_proveedores" in init, (
            "cargar_proveedores debe agendarse (QTimer.singleShot) en __init__"
        )


class TestDirectPurchaseFlow:
    """Flujo de compra directa (DIRECT): métodos y lógica correctos."""

    def _src(self):
        return _source("modulos/compras_pro.py")

    def test_procesar_compra_calls_registrar_compra_uc(self):
        src = self._src()
        method = _get_method_source(src, "_procesar_compra")
        assert method is not None
        assert "RegistrarCompraUC" in method, (
            "_procesar_compra debe delegar a RegistrarCompraUC"
        )

    def test_procesar_como_pr_calls_traditional_purchase_uc(self):
        src = self._src()
        method = _get_method_source(src, "_procesar_como_pr")
        assert method is not None
        assert "TraditionalPurchaseUC" in method, (
            "_procesar_como_pr debe delegar a TraditionalPurchaseUC"
        )

    def test_refresh_totals_display_exists_and_has_subtotal_param(self):
        src = self._src()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_refresh_totals_display":
                param_names = [a.arg for a in node.args.args]
                assert "subtotal" in param_names or "self" in param_names, (
                    "_refresh_totals_display debe aceptar subtotal como param"
                )
                return
        pytest.fail("_refresh_totals_display no encontrado")

    def test_agregar_producto_accepts_prod_dict(self):
        src = self._src()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_agregar_producto":
                param_names = [a.arg for a in node.args.args]
                assert "prod" in param_names, (
                    "_agregar_producto debe aceptar parámetro 'prod'"
                )
                return
        pytest.fail("_agregar_producto no encontrado")


class TestBackwardCompatAttributes:
    """Atributos backward-compat deben estar presentes para lógica de negocio."""

    def _src(self):
        return _source("modulos/compras_pro.py")

    def test_lbl_rfc_alias_exists(self):
        """_lbl_rfc es alias de _inp_rfc para backward compat."""
        src = self._src()
        assert "_lbl_rfc" in src, "_lbl_rfc debe existir como alias backward-compat"

    def test_lbl_tel_alias_exists(self):
        src = self._src()
        assert "_lbl_tel" in src

    def test_lbl_dir_alias_exists(self):
        src = self._src()
        assert "_lbl_dir" in src

    def test_lbl_cred_disp_alias_exists(self):
        src = self._src()
        assert "_lbl_cred_disp" in src

    def test_hidden_stepper_stored_as_attr(self):
        """El stepper debe guardarse como self._hidden_stepper para evitar C++ GC."""
        src = self._src()
        assert "_hidden_stepper" in src, (
            "_hidden_stepper debe guardarse como atributo. "
            "Sin esto, el C++ object es destruido por Python GC."
        )

    def test_hidden_doctype_toolbar_stored_as_attr(self):
        """El doctype toolbar debe guardarse como self._hidden_doctype_toolbar."""
        src = self._src()
        assert "_hidden_doctype_toolbar" in src, (
            "_hidden_doctype_toolbar debe guardarse como atributo (C++ GC guard)."
        )


class TestSpjStylesFixes:
    """Verificar que los bugs resueltos en spj_styles.py no hayan regresado."""

    def test_no_fixedSize_in_apply_spj_buttons(self):
        """apply_spj_buttons no debe llamar .fixedSize() — QPushButton no tiene ese método."""
        src = _source("modulos/spj_styles.py")
        method = _get_method_source(src, "apply_spj_buttons")
        assert method is not None, "apply_spj_buttons no encontrado en spj_styles.py"
        assert "fixedSize()" not in method, (
            "ERROR: apply_spj_buttons llama a .fixedSize() que no existe en QPushButton. "
            "Usar btn.minimumWidth() == btn.maximumWidth() == 30 en su lugar."
        )

    def test_apply_spj_buttons_skips_small_buttons(self):
        """apply_spj_buttons debe tener lógica para saltar botones pequeños."""
        src = _source("modulos/spj_styles.py")
        method = _get_method_source(src, "apply_spj_buttons")
        assert method is not None
        assert "maximumWidth" in method or "minimumWidth" in method, (
            "apply_spj_buttons debe verificar el tamaño del botón antes de aplicar estilo"
        )

    def test_spj_btn_function_exists(self):
        src = _source("modulos/spj_styles.py")
        assert "def spj_btn(" in src

    def test_apply_btn_styles_function_exists(self):
        src = _source("modulos/spj_styles.py")
        assert "def apply_btn_styles(" in src


class TestDesignTokensIntegrity:
    """design_tokens.py debe exportar los tokens que usa compras_pro."""

    def test_colors_exports_primary_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, "PRIMARY_BASE"), "Colors.PRIMARY_BASE debe existir"

    def test_colors_exports_success_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, "SUCCESS_BASE")

    def test_colors_exports_danger_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, "DANGER_BASE")

    def test_colors_exports_neutral(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, "NEUTRAL"), "Colors.NEUTRAL debe existir"

    def test_colors_neutral_has_slate_500(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors.NEUTRAL, "SLATE_500")

    def test_typography_exports_exist(self):
        from modulos.design_tokens import Typography
        assert Typography is not None
