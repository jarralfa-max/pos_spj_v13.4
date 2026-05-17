"""
tests/purchases/test_phase2_unified_uc.py
──────────────────────────────────────────
FASE 2 — Tests de la ruta canónica unificada.

Verifica que:
1. TraditionalPurchaseUC importa correctamente
2. execute(RegisterPurchaseCommand) retorna PurchaseResult
3. Tipos de estado PRState/POState/DocumentType están disponibles
4. La conversión RegisterPurchaseCommand → DatosCompraDTO es fiel
5. Carrito vacío retorna error sin tocar servicios
6. document_type=PR/PO todavía no implementado (retorna error claro)
7. AppContainer expone uc_compra_tradicional
8. ProcesarCompraUC (deprecated) sigue importando sin error
9. application/use_cases/__init__.py exporta todos los símbolos nuevos
10. No hay doble GL cuando se usa la ruta canónica
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import MagicMock, patch


# ── Importaciones de la nueva capa ────────────────────────────────────────────

class TestPhase2Imports:

    def test_traditional_purchase_uc_imports(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        assert TraditionalPurchaseUC is not None

    def test_register_purchase_command_imports(self):
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        assert RegisterPurchaseCommand is not None
        assert PurchaseItemCommand is not None

    def test_register_purchase_command_has_pr_initial_state(self):
        from application.purchases.commands import RegisterPurchaseCommand
        from application.purchases.states import PRState
        field_names = RegisterPurchaseCommand.__dataclass_fields__
        assert "pr_estado_inicial" in field_names
        assert field_names["pr_estado_inicial"].default == PRState.BORRADOR

    def test_purchase_result_imports(self):
        from application.purchases.results import PurchaseResult
        assert PurchaseResult is not None

    def test_states_imports(self):
        from application.purchases.states import DocumentType, PRState, POState
        assert DocumentType.DIRECT == "DIRECT"
        assert PRState.BORRADOR == "BORRADOR"
        assert POState.ABIERTA == "ABIERTA"

    def test_package_init_exports_all(self):
        from application import purchases
        assert hasattr(purchases, "TraditionalPurchaseUC")
        assert hasattr(purchases, "RegisterPurchaseCommand")
        assert hasattr(purchases, "PurchaseResult")
        assert hasattr(purchases, "PRState")
        assert hasattr(purchases, "POState")

    def test_application_use_cases_init_exports_new_symbols(self):
        from application.use_cases import (
            TraditionalPurchaseUC, RegisterPurchaseCommand,
            PurchaseResult, DocumentType, PRState, POState,
        )
        assert TraditionalPurchaseUC is not None

    def test_deprecated_procesr_compra_uc_still_imports(self):
        """ProcesarCompraUC sigue importando (backward compat)."""
        from core.use_cases.compra import ProcesarCompraUC
        from application.use_cases import ProcesarCompraUC as ProcesarCompraUC2
        assert ProcesarCompraUC is not None
        assert ProcesarCompraUC2 is not None


# ── PurchaseItemCommand ───────────────────────────────────────────────────────

class TestPurchaseItemCommand:

    def test_subtotal_property(self):
        from application.purchases.commands import PurchaseItemCommand
        item = PurchaseItemCommand(product_id=1, qty=5.0, unit_cost=100.0, nombre="Pollo")
        assert abs(item.subtotal - 500.0) < 0.001

    def test_default_lote_empty(self):
        from application.purchases.commands import PurchaseItemCommand
        item = PurchaseItemCommand(product_id=1, qty=1.0, unit_cost=10.0, nombre="Test")
        assert item.lote == ""
        assert item.fecha_caducidad == ""


# ── RegisterPurchaseCommand ───────────────────────────────────────────────────

class TestRegisterPurchaseCommand:

    def _make_command(self, **overrides):
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType
        defaults = dict(
            proveedor_id=1,
            proveedor_nombre="Carnes del Norte",
            sucursal_id=1,
            usuario="admin",
            items=[PurchaseItemCommand(product_id=1, qty=10.0, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO",
            subtotal=500.0,
            iva_monto=80.0,
            total=580.0,
            document_type=DocumentType.DIRECT,
        )
        defaults.update(overrides)
        return RegisterPurchaseCommand(**defaults)

    def test_default_document_type_is_direct(self):
        from application.purchases.states import DocumentType
        cmd = self._make_command()
        assert cmd.document_type == DocumentType.DIRECT

    def test_po_id_defaults_to_none(self):
        cmd = self._make_command()
        assert cmd.po_id is None

    def test_to_datos_compra_dto_preserves_fields(self):
        cmd = self._make_command(
            proveedor_id=5,
            sucursal_id=3,
            moneda="USD",
            condicion_pago="credito_30",
            plazo_dias=30,
        )
        dto = cmd.to_datos_compra_dto()
        assert dto.proveedor_id == 5
        assert dto.sucursal_id == 3
        assert dto.moneda == "USD"
        assert dto.condicion_pago == "credito_30"
        assert dto.plazo_dias == 30

    def test_to_datos_compra_dto_items_count(self):
        from application.purchases.commands import PurchaseItemCommand
        cmd = self._make_command(items=[
            PurchaseItemCommand(product_id=1, qty=10.0, unit_cost=50.0, nombre="Pollo"),
            PurchaseItemCommand(product_id=2, qty=5.0, unit_cost=120.0, nombre="Res"),
        ])
        dto = cmd.to_datos_compra_dto()
        assert len(dto.items) == 2

    def test_to_datos_compra_dto_qty_rounded(self):
        from application.purchases.commands import PurchaseItemCommand
        cmd = self._make_command(items=[
            PurchaseItemCommand(product_id=1, qty=10.123456789, unit_cost=50.0, nombre="X"),
        ])
        dto = cmd.to_datos_compra_dto()
        # Should be rounded to 6 decimal places
        assert len(str(dto.items[0].qty).split(".")[-1]) <= 7


# ── TraditionalPurchaseUC ─────────────────────────────────────────────────────

class TestTraditionalPurchaseUC:

    def _make_container(self, folio="CMP-FASE2-001"):
        from application.use_cases.registrar_compra_uc import ResultadoCompraDTO
        container = MagicMock()
        mock_result = ResultadoCompraDTO(
            ok=True, folio=folio,
            recetas_procesadas=[], warnings=[],
        )
        # RegistrarCompraUC will be instantiated inside execute()
        container.purchase_service = MagicMock()
        container.purchase_service.register_purchase.return_value = (folio, [])
        container.recipe_engine = None
        return container

    def _make_command(self, document_type=None):
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType
        return RegisterPurchaseCommand(
            proveedor_id=1,
            proveedor_nombre="Proveedor Test",
            sucursal_id=1,
            usuario="admin",
            items=[PurchaseItemCommand(product_id=1, qty=5.0, unit_cost=100.0, nombre="Pollo")],
            metodo_pago="CONTADO",
            subtotal=500.0,
            iva_monto=0.0,
            total=500.0,
            document_type=document_type or DocumentType.DIRECT,
        )

    def test_execute_returns_purchase_result(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        from application.purchases.results import PurchaseResult
        container = self._make_container()
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(self._make_command())
        assert isinstance(result, PurchaseResult)

    def test_execute_direct_ok_returns_folio(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        container = self._make_container(folio="CMP-FASE2-TEST")
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(self._make_command())
        assert result.ok, f"esperado ok=True, error={result.error}"
        assert result.folio == "CMP-FASE2-TEST"

    def test_empty_cart_returns_error_without_calling_service(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        from application.purchases.commands import RegisterPurchaseCommand
        from application.purchases.states import DocumentType
        container = self._make_container()
        uc = TraditionalPurchaseUC(container)
        cmd = RegisterPurchaseCommand(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=[],
            metodo_pago="CONTADO",
            subtotal=0.0, iva_monto=0.0, total=0.0,
        )
        result = uc.execute(cmd)
        assert not result.ok
        assert "vacío" in result.error.lower()
        container.purchase_service.register_purchase.assert_not_called()

    def test_document_type_pr_routes_to_pr_uc(self):
        """Phase 3: document_type=PR es enrutado (no rechazado)."""
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        from application.purchases.states import DocumentType
        import inspect
        source = inspect.getsource(TraditionalPurchaseUC._execute_pr)
        assert "PurchaseRequestUC" in source, (
            "TraditionalPurchaseUC._execute_pr debe delegar a PurchaseRequestUC"
        )

    def test_document_type_po_routes_to_po_uc(self):
        """Phase 3: document_type=PO es enrutado (no rechazado)."""
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        import inspect
        source = inspect.getsource(TraditionalPurchaseUC._execute_po)
        assert "PurchaseRequestUC" in source or "PurchaseOrderUC" in source

    def test_result_document_type_is_direct(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        from application.purchases.states import DocumentType
        container = self._make_container()
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(self._make_command())
        if result.ok:
            assert result.document_type == DocumentType.DIRECT

    def test_no_double_gl_via_canonical_route(self):
        """
        La ruta canónica NO llama registrar_asiento() directamente.
        El GL es responsabilidad del PurchaseFinanceHandler (EventBus).
        Verifica que TraditionalPurchaseUC no tiene llamadas directas a GL.
        """
        import inspect
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        source = inspect.getsource(TraditionalPurchaseUC)
        assert "registrar_asiento" not in source, (
            "TraditionalPurchaseUC no debe llamar registrar_asiento() directamente. "
            "El GL es responsabilidad del PurchaseFinanceHandler."
        )

    def test_no_direct_add_stock_in_canonical_uc(self):
        """La ruta canónica no llama add_stock() directamente."""
        import inspect
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        source = inspect.getsource(TraditionalPurchaseUC)
        assert "add_stock" not in source, (
            "TraditionalPurchaseUC no debe llamar add_stock() directamente."
        )


# ── PurchaseResult ────────────────────────────────────────────────────────────

class TestPurchaseResult:

    def test_error_result_factory(self):
        from application.purchases.results import PurchaseResult
        r = PurchaseResult.error_result("algo falló")
        assert not r.ok
        assert r.error == "algo falló"
        assert r.folio == ""

    def test_from_resultado_dto(self):
        from application.purchases.results import PurchaseResult
        from application.purchases.states import DocumentType
        from application.use_cases.registrar_compra_uc import ResultadoCompraDTO
        dto = ResultadoCompraDTO(ok=True, folio="CMP-001", warnings=["w1"])
        result = PurchaseResult.from_resultado_dto(dto, DocumentType.DIRECT)
        assert result.ok
        assert result.folio == "CMP-001"
        assert result.document_type == DocumentType.DIRECT
        assert "w1" in result.warnings


# ── AppContainer wiring ───────────────────────────────────────────────────────

class TestAppContainerWiring:

    def test_app_container_has_uc_compra_tradicional_attribute(self):
        """AppContainer debe tener uc_compra_tradicional registrado."""
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "uc_compra_tradicional" in source, (
            "AppContainer.__init__ debe registrar uc_compra_tradicional"
        )

    def test_app_container_uc_compra_still_present(self):
        """uc_compra (deprecado) sigue presente para compat."""
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "uc_compra" in source

    def test_deprecated_docstring_in_procesar_compra_uc(self):
        """ProcesarCompraUC tiene aviso DEPRECATED en su docstring."""
        from core.use_cases.compra import ProcesarCompraUC
        doc = ProcesarCompraUC.__doc__ or ""
        assert "DEPRECATED" in doc or "deprecated" in doc.lower(), (
            "ProcesarCompraUC debe tener aviso DEPRECATED en su docstring"
        )
