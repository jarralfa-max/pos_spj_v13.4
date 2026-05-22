# core/integrations/whatsapp_client.py — Cliente REST para WhatsApp microservicio
"""
Cliente que permite al POS core comunicarse con el microservicio WhatsApp
via REST. Usado por handlers de eventos y módulos de gestión.

La autenticación interna se maneja con `X-Internal-Key`.
La key se resuelve en este orden:

1. Parámetro explícito `internal_key`
2. Variables de entorno `WA_INTERNAL_API_KEY` o `INTERNAL_API_KEY`
3. Archivo `<repo>/whatsapp_service/.env`

Así el ERP no necesita pedir la key en UI si ya existe en el `.env` del
microservicio.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger("spj.integrations.whatsapp")

_DEFAULT_WA_URL = "http://localhost:8000"


def _read_env_file_value(path: Path, key: str) -> str:
    """Lee una variable simple KEY=value de un archivo .env sin dependencias."""
    try:
        if not path.exists():
            return ""
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    except Exception as exc:
        logger.debug("No se pudo leer %s desde %s: %s", key, path, exc)
    return ""


def _resolve_internal_key(explicit: str = "") -> str:
    """Resuelve la key interna usada por `/api/notify/*`."""
    if explicit:
        return explicit.strip()

    env_value = os.getenv("WA_INTERNAL_API_KEY") or os.getenv("INTERNAL_API_KEY")
    if env_value:
        return env_value.strip()

    # Este archivo está en: <repo>/pos_spj_v13.4/core/integrations/whatsapp_client.py
    # Repo root esperado: parents[3]
    try:
        repo_root = Path(__file__).resolve().parents[3]
        env_path = repo_root / "whatsapp_service" / ".env"
        return (
            _read_env_file_value(env_path, "WA_INTERNAL_API_KEY")
            or _read_env_file_value(env_path, "INTERNAL_API_KEY")
        ).strip()
    except Exception as exc:
        logger.debug("No se pudo resolver WA_INTERNAL_API_KEY desde .env: %s", exc)
        return ""


class WhatsAppClient:
    """Cliente HTTP liviano (sin dependencias externas) para el microservicio WA."""

    def __init__(self, base_url: str = _DEFAULT_WA_URL, timeout: int = 5,
                 internal_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._internal_key = _resolve_internal_key(internal_key)

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._internal_key:
            headers["X-Internal-Key"] = self._internal_key
        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST",
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
        result = self._post("/api/notify/send", {"phone": phone, "message": mensaje})
        return result is not None and result.get("ok", False)

    # ── Consultas ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        result = self._get("/health")
        return result is not None

    def get_estado_pedido_wa(self, folio: str) -> Optional[dict]:
        return self._get(f"/api/pedidos/{folio}")
