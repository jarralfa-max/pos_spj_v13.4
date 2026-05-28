from __future__ import annotations


class QuoteGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def create(self, **kwargs):
        return self._bridge._crear_cotizacion_wa_impl(**kwargs)

    def convert_to_order(self, cotizacion_id: int, usuario: str = "whatsapp"):
        return self._bridge._convertir_cotizacion_a_venta_impl(cotizacion_id, usuario)
