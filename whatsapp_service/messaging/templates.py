# messaging/templates.py — Templates pre-aprobados para ventana 24h
"""
WhatsApp solo permite templates aprobados fuera de la ventana de 24h.
Este módulo mapea eventos del ERP a templates.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from messaging.sender import send_template

# ── Registro de templates ─────────────────────────────────────────────────────
# Nombre del template tal como está registrado en Meta Business
TEMPLATES: Dict[str, dict] = {
    "pedido_confirmado": {
        "name": "pedido_confirmado",
        "language": "es_MX",
        "params": ["folio", "total"],   # Parámetros que acepta
    },
    "pedido_listo": {
        "name": "pedido_listo",
        "language": "es_MX",
        "params": ["folio"],
    },
    "anticipo_requerido": {
        "name": "anticipo_requerido",
        "language": "es_MX",
        "params": ["folio", "monto", "link_pago"],
    },
    "recordatorio_anticipo": {
        "name": "recordatorio_anticipo",
        "language": "es_MX",
        "params": ["folio", "fecha_entrega"],
    },
    "pago_recibido": {
        "name": "pago_recibido",
        "language": "es_MX",
        "params": ["folio", "monto"],
    },
    "entrega_en_camino": {
        "name": "entrega_en_camino",
        "language": "es_MX",
        "params": ["folio"],
    },
    "stock_bajo": {
        "name": "alerta_stock_bajo",
        "language": "es_MX",
        "params": ["producto", "stock_actual", "sucursal"],
    },
    "rrhh_vacaciones": {
        "name": "rrhh_vacaciones_aprobadas",
        "language": "es_MX",
        "params": ["nombre", "fecha_inicio", "fecha_fin"],
    },
    "rrhh_nomina": {
        "name": "rrhh_recibo_nomina",
        "language": "es_MX",
        "params": ["nombre", "periodo"],
    },
}


async def send_event_template(to: str, event_name: str,
                               params: Dict[str, str]) -> bool:
    """Envía un template basado en un evento del ERP."""
    tmpl = TEMPLATES.get(event_name)
    if not tmpl:
        return False

    components = []
    if params:
        body_params = []
        for param_name in tmpl["params"]:
            body_params.append({
                "type": "text",
                "text": str(params.get(param_name, "")),
            })
        if body_params:
            components.append({
                "type": "body",
                "parameters": body_params,
            })

    return await send_template(
        to=to,
        template_name=tmpl["name"],
        language=tmpl["language"],
        components=components,
    )
