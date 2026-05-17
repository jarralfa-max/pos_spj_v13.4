"""
tests/purchases/test_fase6_route_separation.py
──────────────────────────────────────────────
FASE 6 — Separar rutas documentales.

Contratos protegidos:
1. DIRECT mantiene la ruta física: TraditionalPurchaseUC → RegistrarCompraUC.
2. PR no llama RegistrarCompraUC ni PurchaseService/register_purchase.
3. PO documental no llama RegistrarCompraUC ni PurchaseService/register_purchase.
4. Recepción PO crea trazabilidad sin reusar la ruta de compra directa.
5. Los use cases PR/PO no contienen side effects de inventario/finanzas.
"""
from __future__ import annotations

import inspect


def _src(obj) -> str:
    return inspect.getsource(obj)


class TestTraditionalPurchaseRouteSeparation:
    """Asegura que DIRECT/PR/PO no comparten la ruta física indebidamente."""

    def test_direct_route_uses_registrar_compra_uc(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC

        src = _src(TraditionalPurchaseUC._execute_direct)
        assert "RegistrarCompraUC" in src

    def test_pr_route_does_not_use_direct_purchase_side_effects(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC

        src = _src(TraditionalPurchaseUC._execute_pr)
        forbidden = ["RegistrarCompraUC", "PurchaseService", "register_purchase", "add_stock"]
        assert not [token for token in forbidden if token in src]
        assert "PurchaseRequestUC" in src

    def test_po_route_does_not_use_direct_purchase_side_effects(self):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC

        src = _src(TraditionalPurchaseUC._execute_po)
        forbidden = ["RegistrarCompraUC", "PurchaseService", "register_purchase", "add_stock"]
        assert not [token for token in forbidden if token in src]
        assert "convertir_a_po" in src


class TestDocumentalUseCasesNoPhysicalEffects:
    """PR/PO son documentales; inventario/finanzas pertenecen a DIRECT o recepción."""

    def test_purchase_request_uc_has_no_direct_purchase_service_call(self):
        from application.purchases.purchase_request_uc import PurchaseRequestUC

        src = _src(PurchaseRequestUC)
        forbidden = ["register_purchase", "add_stock", "registrar_asiento", "crear_cxp"]
        assert not [token for token in forbidden if token in src]

    def test_purchase_order_uc_has_no_direct_purchase_service_call(self):
        from application.purchases.purchase_order_uc import PurchaseOrderUC

        src = _src(PurchaseOrderUC)
        forbidden = ["register_purchase", "add_stock", "registrar_asiento", "crear_cxp"]
        assert not [token for token in forbidden if token in src]


class TestPOReceptionRouteSeparation:
    """Recepción PO afecta inventario una sola vez y no reutiliza compra directa."""

    def test_receive_po_adapter_does_not_call_register_purchase(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter

        src = _src(ReceivePOAdapter.register_partial_receipt)
        assert "register_purchase" not in src
        assert "_create_receipt_purchase_record" in src

    def test_receive_po_adapter_traceability_helper_does_not_call_inventory(self):
        from application.purchases.receive_po_adapter import ReceivePOAdapter

        src = _src(ReceivePOAdapter._create_receipt_purchase_record)
        forbidden = ["add_stock", "registrar_lote", "registrar_asiento", "crear_cxp"]
        assert not [token for token in forbidden if token in src]
        assert "create_purchase" in src
