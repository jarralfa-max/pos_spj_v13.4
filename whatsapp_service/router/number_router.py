# router/number_router.py — Routing por número de WhatsApp
"""
Determina el tipo de flujo basándose en qué número recibió el mensaje.
"""
from __future__ import annotations
from config.numbers import NumberRegistry, NumeroTipo, NumeroConfig
from models.message import IncomingMessage


class NumberRouter:
    def __init__(self, registry: NumberRegistry):
        self.registry = registry

    def route(self, msg: IncomingMessage) -> NumeroConfig:
        """Retorna la configuración del número que recibió el mensaje."""
        cfg = self.registry.get(msg.phone_number_id)
        if not cfg:
            # Número no configurado: no inventar sucursal.
            # Tratarlo como global para forzar selección antes de crear pedidos.
            return NumeroConfig(
                phone_number_id=msg.phone_number_id,
                tipo=NumeroTipo.GLOBAL,
                sucursal_id=None,
                sucursal_nombre="",
                display_name="Número no configurado",
            )
        return cfg
