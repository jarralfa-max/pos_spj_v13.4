# tests/test_domain_entities.py — SPJ POS v13.5
"""Tests para las entidades del domain layer."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from domain.entities.sale import Sale, SaleItem
from domain.entities.product import Product
from domain.entities.customer import Customer
from domain.entities.purchase import Purchase, PurchaseItem
from domain.value_objects.money import Money
from domain.value_objects.quantity import Quantity
from domain.services.sale_domain_service import SaleDomainService


class TestSaleEntity:
    def test_sale_item_subtotal(self):
        item = SaleItem(producto_id=1, nombre="Pechuga", cantidad=2.0, precio_unitario=95.0)
        assert item.subtotal == 190.0

    def test_sale_item_subtotal_with_discount(self):
        item = SaleItem(producto_id=1, nombre="Pechuga", cantidad=2.0, precio_unitario=100.0, descuento=10.0)
        assert item.subtotal == 180.0

    def test_sale_total(self):
        items = [
            SaleItem(producto_id=1, nombre="Pechuga", cantidad=2.0, precio_unitario=95.0),
            SaleItem(producto_id=2, nombre="Pierna", cantidad=1.0, precio_unitario=75.0),
        ]
        sale = Sale(items=items)
        assert sale.total == 265.0

    def test_sale_total_with_global_discount(self):
        items = [SaleItem(producto_id=1, nombre="Pechuga", cantidad=2.0, precio_unitario=100.0)]
        sale = Sale(items=items, descuento_global=10.0)
        assert sale.total == 180.0

    def test_sale_validate_empty(self):
        sale = Sale(items=[])
        errors = sale.validate()
        assert len(errors) > 0

    def test_sale_validate_invalid_quantity(self):
        items = [SaleItem(producto_id=1, nombre="X", cantidad=-1.0, precio_unitario=10.0)]
        sale = Sale(items=items)
        errors = sale.validate()
        assert any("Cantidad" in e for e in errors)

    def test_sale_validate_ok(self):
        items = [SaleItem(producto_id=1, nombre="Pechuga", cantidad=2.0, precio_unitario=95.0)]
        sale = Sale(items=items)
        assert sale.validate() == []


class TestProductEntity:
    def test_tiene_stock(self):
        p = Product(id=1, nombre="Pechuga", precio=95.0, existencia=10.0)
        assert p.tiene_stock(5.0) is True
        assert p.tiene_stock(11.0) is False

    def test_esta_disponible(self):
        p = Product(id=1, nombre="X", precio=10.0, existencia=5.0, activo=True, oculto=False)
        assert p.esta_disponible() is True

    def test_oculto_no_disponible(self):
        p = Product(id=1, nombre="X", precio=10.0, existencia=5.0, activo=True, oculto=True)
        assert p.esta_disponible() is False


class TestCustomerEntity:
    def test_credito_disponible(self):
        c = Customer(id=1, nombre="Ana", credit_limit=1000.0, credit_balance=300.0)
        assert c.credito_disponible == 700.0

    def test_credito_suficiente(self):
        c = Customer(id=1, nombre="Ana", credit_limit=1000.0, credit_balance=300.0)
        assert c.tiene_credito_suficiente(500.0) is True
        assert c.tiene_credito_suficiente(800.0) is False


class TestMoneyValueObject:
    def test_add(self):
        assert (Money(100.0) + Money(50.0)) == Money(150.0)

    def test_multiply(self):
        assert Money(100.0) * 0.9 == Money(90.0)

    def test_zero(self):
        assert Money.zero().amount == 0.0

    def test_immutable(self):
        m = Money(100.0)
        with pytest.raises(Exception):
            m.amount = 200.0


class TestQuantityValueObject:
    def test_add(self):
        assert (Quantity(5.0) + Quantity(3.0)) == Quantity(8.0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            Quantity(-1.0)

    def test_is_sufficient(self):
        assert Quantity(10.0).is_sufficient(Quantity(8.0)) is True
        assert Quantity(5.0).is_sufficient(Quantity(8.0)) is False


class TestSaleDomainService:
    def test_calcular_totales(self):
        svc = SaleDomainService()
        items = [SaleItem(producto_id=1, nombre="X", cantidad=2.0, precio_unitario=100.0)]
        result = svc.calcular_totales(items, descuento_global=10.0)
        assert result["total"] == 180.0
        assert result["descuento_monto"] == 20.0

    def test_calcular_cambio(self):
        svc = SaleDomainService()
        assert svc.calcular_cambio(total=150.0, efectivo_recibido=200.0) == 50.0

    def test_cambio_zero_when_exact(self):
        svc = SaleDomainService()
        assert svc.calcular_cambio(total=100.0, efectivo_recibido=100.0) == 0.0
