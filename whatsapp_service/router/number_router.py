# router/number_router.py — Routing por número de WhatsApp
"""
Determina el tipo de flujo basándose en qué número recibió el mensaje.
"""
from __future__ import annotations
from config.numbers import NumberRegistry, NumeroTipo, NumeroConfig
from models.message import IncomingMessage
from typing import Optional


class NumberRouter:
    def __init__(self, registry: NumberRegistry):
        self.registry = registry

    def route(self, msg: IncomingMessage) -> NumeroConfig:
        """Retorna la configuración del número que recibió el mensaje."""
        cfg = self.registry.get(msg.phone_number_id)
        if not cfg:
            # Número no configurado — tratar como ventas por defecto
            return NumeroConfig(
                phone_number_id=msg.phone_number_id,
                tipo=NumeroTipo.VENTAS,
                sucursal_id=1,
                sucursal_nombre="Principal",
            )
        return cfg
