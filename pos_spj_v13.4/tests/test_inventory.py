
# tests/test_inventory.py — SPJ POS v9
import pytest
from core.services.inventory.unified_inventory_service import (
    UnifiedInventoryService, InventoryError, StockInsuficienteError
)

class TestGetStock:
    def test_stock_existente(self, inv_svc):
        assert inv_svc.get_stock(1) == 50.0

    def test_stock_producto_inexistente(self, inv_svc):
        assert inv_svc.get_stock(9999) == 0.0

    def test_stock_sin_existencia(self, inv_svc):
        assert inv_svc.get_stock(4) == 0.0


class TestRegisterMovement:
    def test_entrada_incrementa_stock(self, inv_svc, mem_db):
        inv_svc.register_movement(1, "purchase", 10.0, reference="OC-001")
        assert inv_svc.get_stock(1) == 60.0

    def test_salida_decrementa_stock(self, inv_svc):
        inv_svc.register_movement(1, "sale", 5.0)
        assert inv_svc.get_stock(1) == 45.0

    def test_salida_sin_stock_lanza_excepcion(self, inv_svc):
        with pytest.raises(StockInsuficienteError):
            inv_svc.register_movement(4, "sale", 1.0)

    def test_tipo_invalido_lanza_excepcion(self, inv_svc):
        with pytest.raises(InventoryError):
            inv_svc.register_movement(1, "tipo_inexistente", 1.0)

    def test_cantidad_negativa_lanza_excepcion(self, inv_svc):
        with pytest.raises(InventoryError):
            inv_svc.register_movement(1, "sale", -5.0)

    def test_movimiento_crea_registro(self, inv_svc, mem_db):
        inv_svc.register_movement(1, "purchase", 5.0, reference="TEST-001")
        rows = mem_db.execute("SELECT * FROM movimientos_inventario WHERE referencia='TEST-001'").fetchall()
        assert len(rows) == 1
        assert float(rows[0]["cantidad"]) == 5.0

    def test_ajuste_exacto(self, inv_svc):
        inv_svc.adjust_stock(1, 30.0, reason="Inventario fisico")
        assert inv_svc.get_stock(1) == 30.0

    def test_ajuste_sin_diferencia_no_crea_movimiento(self, inv_svc, mem_db):
        before = mem_db.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0]
        inv_svc.adjust_stock(1, 50.0)  # same as current
        after = mem_db.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0]
        assert before == after

    def test_validate_stock_suficiente(self, inv_svc):
        assert inv_svc.validate_stock(1, 50.0) is True

    def test_validate_stock_insuficiente(self, inv_svc):
        assert inv_svc.validate_stock(1, 51.0) is False

    def test_waste_decrementa_stock(self, inv_svc):
        inv_svc.register_movement(1, "waste", 3.0)
        assert inv_svc.get_stock(1) == 47.0

    def test_produccion_incrementa_stock(self, inv_svc):
        inv_svc.register_movement(1, "production", 20.0)
        assert inv_svc.get_stock(1) == 70.0


class TestLowStock:
    def test_producto_bajo_minimo_aparece(self, inv_svc, mem_db):
        mem_db.execute("UPDATE productos SET existencia=2 WHERE id=1")
        mem_db.commit()
        low = inv_svc.get_low_stock()
        ids = [r["id"] for r in low]
        assert 1 in ids

    def test_producto_sobre_minimo_no_aparece(self, inv_svc):
        low = inv_svc.get_low_stock()
        ids = [r["id"] for r in low]
        assert 1 not in ids  # stock=50, minimo=5

    def test_sin_stock_aparece(self, inv_svc):
        low = inv_svc.get_low_stock()
        ids = [r["id"] for r in low]
        assert 4 in ids  # stock=0, minimo=5
