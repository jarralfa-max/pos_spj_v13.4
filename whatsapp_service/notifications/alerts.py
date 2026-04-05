# notifications/alerts.py — Alertas del sistema al staff
"""
Envía alertas clasificadas por severidad al personal vía WhatsApp.
Escucha eventos del ERP: stock bajo, cancelaciones, forecast.
"""
from __future__ import annotations
import logging
from enum import Enum
from typing import List
from messaging.sender import send_text
from messaging.templates import send_event_template

logger = logging.getLogger("wa.notif.alerts")


class AlertSeverity(str, Enum):
    CRITICO = "critico"        # Stock agotado, errores graves
    IMPORTANTE = "importante"  # Stock bajo, cancelaciones frecuentes
    INFORMATIVO = "info"       # Sugerencias de compra, resúmenes


SEVERITY_EMOJI = {
    AlertSeverity.CRITICO: "🔴",
    AlertSeverity.IMPORTANTE: "🟡",
    AlertSeverity.INFORMATIVO: "🔵",
}


async def enviar_alerta(phones: List[str], titulo: str, mensaje: str,
                         severidad: AlertSeverity = AlertSeverity.INFORMATIVO):
    """Envía alerta a una lista de teléfonos del staff."""
    emoji = SEVERITY_EMOJI.get(severidad, "ℹ️")
    texto = f"{emoji} *{titulo}*\n\n{mensaje}"
    for phone in phones:
        await send_text(phone, texto)
    logger.info("Alerta enviada (%s) a %d destinatarios: %s",
                severidad.value, len(phones), titulo)


async def alerta_stock_bajo(phones: List[str], producto: str,
                             stock_actual: float, sucursal: str):
    """Alerta de stock bajo."""
    sev = AlertSeverity.CRITICO if stock_actual <= 0 else AlertSeverity.IMPORTANTE
    await enviar_alerta(phones,
        "Stock bajo" if stock_actual > 0 else "Producto agotado",
        f"*{producto}*\n"
        f"Stock actual: {stock_actual:.1f}\n"
        f"Sucursal: {sucursal}",
        severidad=sev)


async def alerta_cancelaciones(phones: List[str], usuario: str,
                                cantidad: int, periodo: str):
    """Alerta de cancelaciones frecuentes."""
    await enviar_alerta(phones,
        "Cancelaciones frecuentes",
        f"El usuario *{usuario}* ha cancelado {cantidad} ventas {periodo}.\n"
        f"Verificar posible mal uso del sistema.",
        severidad=AlertSeverity.IMPORTANTE)


async def alerta_forecast(phones: List[str], productos: List[dict],
                           sucursal: str):
    """Sugerencia de compra del módulo forecast."""
    lines = [f"Sucursal: *{sucursal}*\n"]
    for p in productos[:10]:
        lines.append(f"• {p['nombre']}: comprar {p['cantidad_sugerida']} {p.get('unidad','kg')}")
    await enviar_alerta(phones,
        "Sugerencia de compra",
        "\n".join(lines),
        severidad=AlertSeverity.INFORMATIVO)


async def alerta_pedidos_pendientes(phones: List[str],
                                     cantidad: int, sucursal: str):
    """Alerta de pedidos WA pendientes de procesar."""
    if cantidad > 5:
        sev = AlertSeverity.CRITICO
    elif cantidad > 2:
        sev = AlertSeverity.IMPORTANTE
    else:
        sev = AlertSeverity.INFORMATIVO
    await enviar_alerta(phones,
        f"{cantidad} pedidos pendientes",
        f"Hay *{cantidad}* pedidos de WhatsApp sin procesar en *{sucursal}*.",
        severidad=sev)
