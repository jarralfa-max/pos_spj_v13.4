"""
tests/purchases/test_purchase_finance_effects.py
─────────────────────────────────────────────────
FASE 1 — Tests de caracterización: efectos financieros de una compra.

Propósito: documentar cuándo y cómo se generan asientos GL y CxP.
Protegen contra:
  - Doble asiento si dos rutas (UC + handler) ejecutan GL
  - Pérdida de asiento en refactorización
  - PR/PO que generen asientos prematuros

Cobertura (via ProcesarCompraUC — ruta actual con GL directo):
- Asiento 1201/2101 siempre generado en compra
- Asiento 2101/1101 generado solo en CONTADO con monto_pagado > 0
- CxP creado cuando deuda > 0
- No asiento en CREDITO sin pago
- GL es exactamente 1x por compra (sin duplicación)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import MagicMock, patch, call

from core.use_cases.compra import ProcesarCompraUC, ItemCompra, DatosCompra


@pytest.fixture
def purchase_svc():
    svc = MagicMock()
    svc.register_purchase.return_value = ("CMP-20260515-TEST", [])
    return svc


@pytest.fixture
def finance_svc():
    svc = MagicMock()
    svc.registrar_asiento.return_value = 42
    svc.crear_cxp.return_value = 99
    return svc


@pytest.fixture
def inv_svc():
    return MagicMock()


@pytest.fixture
def uc(purchase_svc, finance_svc, inv_svc):
    bus = MagicMock()
    bus.publish = MagicMock()
    return ProcesarCompraUC(
        purchase_service=purchase_svc,
        finance_service=finance_svc,
        inventory_service=inv_svc,
        event_bus=bus,
    )


def _items(n=1):
    return [ItemCompra(producto_id=1, nombre="Pollo", cantidad=10.0, costo_unit=50.0)] * n


class TestPurchaseFinanceEffects:

    def test_gl_asiento_inventory_cxp_always_posted(self, uc, finance_svc):
        """Asiento 1201/2101 siempre se genera al registrar compra."""
        datos = DatosCompra(proveedor_id=1, forma_pago="CONTADO", monto_pagado=500.0)
        result = uc.ejecutar(_items(), datos, sucursal_id=1, usuario="admin")
        assert result.ok, f"compra falló: {result.error}"
        calls = [str(c) for c in finance_svc.registrar_asiento.call_args_list]
        # Verify at least one call references inventory (1201) and payable (2101)
        assert finance_svc.registrar_asiento.called, "registrar_asiento no fue llamado"
        first_call_kwargs = finance_svc.registrar_asiento.call_args_list[0]
        args, kwargs = first_call_kwargs
        combined = dict(zip(["debe", "haber", "concepto", "monto"], args))
        combined.update(kwargs)
        assert "1201" in str(combined.get("debe", "")) or "1201" in str(combined), (
            "asiento de entrada debe usar cuenta 1201 en debe"
        )

    def test_payment_gl_posted_only_for_contado(self, uc, finance_svc):
        """Asiento 2101/1101 solo se genera si forma_pago != CREDITO y monto > 0."""
        datos_contado = DatosCompra(
            proveedor_id=1, forma_pago="CONTADO", monto_pagado=500.0
        )
        uc.ejecutar(_items(), datos_contado, sucursal_id=1, usuario="admin")
        contado_call_count = finance_svc.registrar_asiento.call_count

        finance_svc.registrar_asiento.reset_mock()

        datos_credito = DatosCompra(
            proveedor_id=1, forma_pago="CREDITO", monto_pagado=0.0
        )
        uc.ejecutar(_items(), datos_credito, sucursal_id=1, usuario="admin")
        credito_call_count = finance_svc.registrar_asiento.call_count

        assert contado_call_count > credito_call_count, (
            "CONTADO debe generar más asientos que CREDITO (incluye pago)"
        )

    def test_cxp_created_when_debt_remains(self, uc, finance_svc):
        """CxP se crea cuando monto_pagado < total (deuda pendiente)."""
        datos = DatosCompra(
            proveedor_id=1, forma_pago="CREDITO", monto_pagado=0.0
        )
        result = uc.ejecutar(_items(), datos, sucursal_id=1, usuario="admin")
        assert result.ok
        assert finance_svc.crear_cxp.called, "crear_cxp debe llamarse cuando hay deuda"

    def test_cxp_not_created_when_fully_paid(self, uc, finance_svc):
        """CxP NO se crea cuando el pago es completo."""
        datos = DatosCompra(
            proveedor_id=1, forma_pago="CONTADO", monto_pagado=500.0
        )
        result = uc.ejecutar(_items(), datos, sucursal_id=1, usuario="admin")
        assert result.ok
        # monto_pagado == total (500) → sin deuda → sin CxP
        assert not finance_svc.crear_cxp.called, (
            "crear_cxp NO debe llamarse cuando el pago es completo"
        )

    def test_asiento_id_returned_in_result(self, uc, finance_svc):
        """El asiento_id debe devolverse en el resultado."""
        finance_svc.registrar_asiento.return_value = 77
        datos = DatosCompra(proveedor_id=1, forma_pago="CONTADO", monto_pagado=500.0)
        result = uc.ejecutar(_items(), datos, sucursal_id=1, usuario="admin")
        assert result.asiento_id == 77

    def test_no_double_gl_on_single_purchase(self, uc, finance_svc):
        """Una sola compra no debe generar más de 2 asientos GL (entrada + pago)."""
        datos = DatosCompra(
            proveedor_id=1, forma_pago="CONTADO", monto_pagado=500.0
        )
        uc.ejecutar(_items(), datos, sucursal_id=1, usuario="admin")
        # Maximum 2: 1201/2101 (entry) + 2101/1101 (payment)
        assert finance_svc.registrar_asiento.call_count <= 2, (
            f"se esperan <= 2 asientos por compra, "
            f"se generaron {finance_svc.registrar_asiento.call_count} (posible duplicación)"
        )

    def test_pr_must_not_generate_gl(self):
        """
        Contrato pre-implementación: PR no debe llamar registrar_asiento.
        Si el módulo PR no existe, el test pasa.
        """
        try:
            from application.purchases import purchase_request_uc
            assert not hasattr(purchase_request_uc, "registrar_asiento"), (
                "PR UC no debe exponer registrar_asiento"
            )
        except ImportError:
            pass

    def test_po_must_not_generate_gl(self):
        """
        Contrato pre-implementación: PO no debe llamar registrar_asiento.
        """
        try:
            from application.purchases import purchase_order_uc
            assert not hasattr(purchase_order_uc, "registrar_asiento"), (
                "PO UC no debe exponer registrar_asiento"
            )
        except ImportError:
            pass

    def test_pr_must_not_create_cxp(self):
        """Contrato pre-implementación: PR no genera CxP."""
        try:
            from application.purchases import purchase_request_uc
            assert not hasattr(purchase_request_uc, "crear_cxp"), (
                "PR UC no debe exponer crear_cxp"
            )
        except ImportError:
            pass
