
# tests/test_sales.py — SPJ POS v9
import pytest
from core.services.sales.unified_sales_service import (
    UnifiedSalesService, ItemVenta, DatosPago, ResultadoVenta,
    CarritoVacioError, PagoInsuficienteError, StockError
)

def _item(prod_id=1, qty=1.0, precio=150.0, nombre="Pollo"):
    return ItemVenta(producto_id=prod_id, cantidad=qty, precio_unitario=precio, nombre=nombre)

def _pago(forma="Efectivo", recibido=200.0, cliente_id=None):
    return DatosPago(forma_pago=forma, efectivo_recibido=recibido, cliente_id=cliente_id)


class TestProcesarVenta:
    def test_venta_exitosa_retorna_resultado(self, sales_svc):
        result = sales_svc.procesar_venta([_item()], _pago())
        assert isinstance(result, ResultadoVenta)
        assert result.total == 150.0
        assert result.cambio == 50.0

    def test_carrito_vacio_lanza_excepcion(self, sales_svc):
        with pytest.raises(CarritoVacioError):
            sales_svc.procesar_venta([], _pago())

    def test_pago_insuficiente_lanza_excepcion(self, sales_svc):
        with pytest.raises(PagoInsuficienteError):
            sales_svc.procesar_venta([_item()], _pago(recibido=50.0))

    def test_sin_stock_lanza_excepcion(self, sales_svc):
        with pytest.raises(StockError):
            sales_svc.procesar_venta([_item(prod_id=4, qty=1.0)], _pago())

    def test_stock_se_descuenta(self, sales_svc, mem_db):
        sales_svc.procesar_venta([_item(qty=3.0)], _pago())
        stock = mem_db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0]
        assert float(stock) == 47.0

    def test_venta_se_registra_en_bd(self, sales_svc, mem_db):
        result = sales_svc.procesar_venta([_item()], _pago())
        row = mem_db.execute("SELECT * FROM ventas WHERE id=?", (result.venta_id,)).fetchone()
        assert row is not None
        assert float(row["total"]) == 150.0
        assert row["estado"] == "completada"

    def test_movimiento_caja_creado(self, sales_svc, mem_db):
        result = sales_svc.procesar_venta([_item()], _pago())
        row = mem_db.execute("SELECT * FROM movimientos_caja WHERE venta_id=?", (result.venta_id,)).fetchone()
        assert row is not None
        assert row["tipo"] == "INGRESO"

    def test_puntos_asignados_a_cliente(self, sales_svc, mem_db):
        sales_svc.procesar_venta([_item()], _pago(cliente_id=1))
        row = mem_db.execute("SELECT puntos FROM clientes WHERE id=1").fetchone()
        assert int(row["puntos"]) > 100  # tenia 100, gano mas

    def test_folio_generado(self, sales_svc):
        result = sales_svc.procesar_venta([_item()], _pago())
        assert result.folio.startswith("V")

    def test_multiples_items(self, sales_svc):
        items = [_item(1, 2.0, 150.0, "Pollo"), _item(2, 3.0, 20.0, "Agua")]
        result = sales_svc.procesar_venta(items, _pago(recibido=400.0))
        assert result.total == 360.0
        assert result.cambio == 40.0

    def test_descuento_global(self, sales_svc):
        pago = DatosPago(forma_pago="Efectivo", efectivo_recibido=200.0, descuento_global=20.0)
        result = sales_svc.procesar_venta([_item()], pago)
        assert result.total == 130.0

    def test_pago_con_tarjeta_no_requiere_efectivo(self, sales_svc):
        pago = DatosPago(forma_pago="Tarjeta", efectivo_recibido=0.0)
        result = sales_svc.procesar_venta([_item()], pago)
        assert result.total == 150.0

    def test_ticket_data_incluido(self, sales_svc):
        result = sales_svc.procesar_venta([_item()], _pago())
        assert "folio" in result.ticket_data
        assert "total" in result.ticket_data
        assert "items" in result.ticket_data


class TestAnularVenta:
    def test_anular_restaura_stock(self, sales_svc, mem_db):
        result = sales_svc.procesar_venta([_item(qty=5.0)], _pago())
        stock_after_sale = float(mem_db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0])
        sales_svc.anular_venta(result.venta_id, "test")
        stock_after_cancel = float(mem_db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0])
        assert stock_after_cancel == stock_after_sale + 5.0

    def test_anular_cambia_estado(self, sales_svc, mem_db):
        result = sales_svc.procesar_venta([_item()], _pago())
        sales_svc.anular_venta(result.venta_id)
        row = mem_db.execute("SELECT estado FROM ventas WHERE id=?", (result.venta_id,)).fetchone()
        assert row["estado"] == "cancelada"

    def test_anular_dos_veces_lanza_excepcion(self, sales_svc):
        from core.services.sales.unified_sales_service import VentaError
        result = sales_svc.procesar_venta([_item()], _pago())
        sales_svc.anular_venta(result.venta_id)
        with pytest.raises(VentaError):
            sales_svc.anular_venta(result.venta_id)

    def test_anular_inexistente_lanza_excepcion(self, sales_svc):
        from core.services.sales.unified_sales_service import VentaError
        with pytest.raises(VentaError):
            sales_svc.anular_venta(99999)
