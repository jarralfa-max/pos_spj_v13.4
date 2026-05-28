from __future__ import annotations


class OrderGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def create(self, **kwargs):
        return self._bridge._crear_pedido_wa_impl(**kwargs)

    def update_status(self, pedido_id: int, estado: str, notas: str = "") -> bool:
        return self._bridge._actualizar_estado_pedido_impl(pedido_id, estado, notas)
