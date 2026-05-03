# tests/test_application_layer.py — SPJ POS v13.5
"""Tests para el application layer (shims a core/use_cases)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

class TestApplicationImports:
    def test_procesar_venta_uc_importable(self):
        from application.use_cases import ProcesarVentaUC
        assert ProcesarVentaUC is not None

    def test_procesar_compra_uc_importable(self):
        from application.use_cases import ProcesarCompraUC
        assert ProcesarCompraUC is not None

    def test_gestionar_cliente_uc_importable(self):
        from application.use_cases import GestionarClienteUC
        assert GestionarClienteUC is not None

    def test_gestionar_nomina_uc_importable(self):
        from application.use_cases import GestionarNominaUC
        assert GestionarNominaUC is not None

    def test_gestionar_inventario_uc_importable(self):
        from application.use_cases import GestionarInventarioUC
        assert GestionarInventarioUC is not None

    def test_gestionar_produccion_uc_importable(self):
        from application.use_cases import GestionarProduccionUC
        assert GestionarProduccionUC is not None

class TestSaleDTO:
    def test_dto_subtotal_auto_calculated(self):
        from application.dtos.sale_dto import SaleItemDTO
        dto = SaleItemDTO(producto_id=1, nombre="X", cantidad=2.0, precio_unitario=50.0)
        assert dto.subtotal == 100.0

    def test_create_sale_dto(self):
        from application.dtos.sale_dto import CreateSaleDTO, SaleItemDTO
        dto = CreateSaleDTO(
            items=[SaleItemDTO(producto_id=1, nombre="X", cantidad=1.0, precio_unitario=100.0)],
            forma_pago="Efectivo"
        )
        assert dto.sucursal_id == 1
