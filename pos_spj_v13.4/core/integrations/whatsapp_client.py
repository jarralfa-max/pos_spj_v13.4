# core/integrations/whatsapp_client.py — Cliente REST para WhatsApp microservicio
"""
Cliente que permite al POS core comunicarse con el microservicio WhatsApp
via REST. Usado por handlers de eventos y módulos de gestión.
"""
from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

logger = logging.getLogger("spj.integrations.whatsapp")

_DEFAULT_WA_URL = "http://localhost:8000"


class WhatsAppClient:
    """Cliente HTTP liviano (sin dependencias externas) para el microservicio WA."""

    def __init__(self, base_url: str = _DEFAULT_WA_URL, timeout: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            logger.debug("WA client %s: %s", path, e)
            return None
        except Exception as e:
            logger.debug("WA client error %s: %s", path, e)
            return None

    def _get(self, path: str) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.debug("WA client GET %s: %s", path, e)
            return None

    # ── Notificaciones al cliente via WA ──────────────────────────────────────

    def notificar_pedido_listo(self, phone: str, folio: str, sucursal: str = "") -> bool:
        result = self._post("/api/notify/pedido-listo", {
            "phone": phone, "folio": folio, "sucursal": sucursal,
        })
        return result is not None and result.get("ok", False)

    def notificar_anticipo_requerido(self, phone: str, folio: str, monto: float) -> bool:
        result = self._post("/api/notify/anticipo", {
            "phone": phone, "folio": folio, "monto": monto,
        })
        return result is not None and result.get("ok", False)

    def notificar_cotizacion_lista(self, phone: str, folio: str, total: float) -> bool:
        result = self._post("/api/notify/cotizacion", {
            "phone": phone, "folio": folio, "total": total,
        })
        return result is not None and result.get("ok", False)

    def enviar_mensaje(self, phone: str, mensaje: str) -> bool:
        result = self._post("/api/send", {"phone": phone, "message": mensaje})
        return result is not None and result.get("ok", False)

    # ── Consultas ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        result = self._get("/health")
        return result is not None

    def get_estado_pedido_wa(self, folio: str) -> Optional[dict]:
        return self._get(f"/api/pedidos/{folio}")
