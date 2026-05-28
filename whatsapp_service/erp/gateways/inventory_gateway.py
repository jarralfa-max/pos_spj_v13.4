from __future__ import annotations


class InventoryGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def check_stock(self, items, sucursal_id: int):
        return self._bridge._verificar_stock_items_impl(items, sucursal_id)

    def create_purchase_order(self, producto_id: int, cantidad: float, sucursal_id: int, notas: str = ""):
        return self._bridge._generar_orden_compra_impl(producto_id, cantidad, sucursal_id, notas)
