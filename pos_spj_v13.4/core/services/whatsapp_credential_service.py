# core/services/whatsapp_credential_service.py
"""Gestión segura de credenciales Meta/Twilio para WhatsApp."""
from __future__ import annotations
import logging
import json
import urllib.request
import urllib.error
from typing import Optional, Dict

from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository

logger = logging.getLogger("spj.service.wa_credentials")

# Longitud mínima esperada de un token Bearer de Meta
_META_TOKEN_MIN_LEN = 20


class WhatsAppCredentialService:
    def __init__(self, conn):
        self._repo = WhatsAppConfigRepository(conn)

    # ── Guardar ───────────────────────────────────────────────────────────────

    def save_credentials(self, sucursal_id: Optional[int], canal: str,
                         proveedor: str, numero: str,
                         meta_token: str, meta_phone_id: str,
                         twilio_sid: str = "", twilio_token: str = "",
                         rasa_url: str = "http://localhost:5005",
                         rasa_activo: bool = False,
                         activo: bool = True,
                         nombre_sucursal: Optional[str] = None,
                         row_id: Optional[int] = None) -> bool:
        data = {
            "sucursal_id":    sucursal_id,
            "canal":          canal,
            "proveedor":      proveedor,
            "numero_negocio": numero,
            "meta_phone_id":  meta_phone_id,
            "meta_token":     meta_token,
            "twilio_sid":     twilio_sid,
            "rasa_url":       rasa_url or "http://localhost:5005",
            "rasa_activo":    1 if rasa_activo else 0,
            "activo":         1 if activo else 0,
            "nombre_sucursal": nombre_sucursal,
        }
        return self._repo.save_numero(data, row_id)

    # ── Leer enmascarado ───────────────────────────────────────────────────────

    def get_masked_credentials(self, row_id: int) -> Optional[Dict]:
        """Devuelve credenciales con token enmascarado (nunca el token completo)."""
        data = self._repo.get_numero(row_id)
        if not data:
            return None
        token = data.get("meta_token") or ""
        data["meta_token"] = self._mask_token(token)
        twilio = data.get("twilio_sid") or ""
        if twilio:
            data["twilio_sid"] = self._mask_token(twilio)
        return data

    @staticmethod
    def _mask_token(token: str) -> str:
        if not token or len(token) < 8:
            return "***"
        return token[:4] + "*" * (len(token) - 8) + token[-4:]

    # ── Validar token Meta ─────────────────────────────────────────────────────

    def validate_meta_credentials(self, token: str,
                                  phone_number_id: str) -> Dict:
        """
        Validación mínima:
        1. token y phone_number_id no vacíos y longitud mínima.
        2. Llamada de verificación a Graph API (debug_token o get phone endpoint).
        Nunca loguea el token completo.
        """
        if not token or len(token) < _META_TOKEN_MIN_LEN:
            return {"valid": False, "error": "Token vacío o demasiado corto"}
        if not phone_number_id or not phone_number_id.strip():
            return {"valid": False, "error": "Phone Number ID vacío"}

        # Llamada de verificación real a Graph API
        try:
            url = (f"https://graph.facebook.com/v21.0/{phone_number_id}"
                   f"?fields=id,display_phone_number"
                   f"&access_token={token}")
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = json.loads(resp.read().decode())
                if body.get("id"):
                    return {
                        "valid": True,
                        "phone": body.get("display_phone_number", ""),
                        "id": body.get("id"),
                    }
                return {"valid": False, "error": "Respuesta inesperada de Meta"}
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                err_body = json.loads(e.read().decode())
                msg = err_body.get("error", {}).get("message", str(e))
            except Exception:
                msg = str(e)
            logger.warning("Meta credential validation HTTP %d", code)
            return {"valid": False, "error": f"Meta API {code}: {msg}"}
        except urllib.error.URLError as e:
            logger.warning("Meta credential validation network error: %s", type(e).__name__)
            return {"valid": False, "error": "Sin conexión a Meta Graph API"}
        except Exception as e:
            logger.warning("Meta credential validation error: %s", type(e).__name__)
            return {"valid": False, "error": str(e)}

    # ── Validar verify_token ───────────────────────────────────────────────────

    def validate_webhook_token(self, verify_token: str) -> Dict:
        if not verify_token or len(verify_token) < 4:
            return {"valid": False, "error": "Verify token demasiado corto (mín 4 chars)"}
        if len(verify_token) > 128:
            return {"valid": False, "error": "Verify token demasiado largo (máx 128 chars)"}
        return {"valid": True}

    # ── Rotar token ───────────────────────────────────────────────────────────

    def rotate_token(self, row_id: int, new_token: str) -> bool:
        """Reemplaza solo el meta_token de un número."""
        if not new_token or len(new_token) < _META_TOKEN_MIN_LEN:
            logger.warning("rotate_token: token inválido para row_id=%d", row_id)
            return False
        existing = self._repo.get_numero(row_id)
        if not existing:
            return False
        existing["meta_token"] = new_token
        return self._repo.save_numero(existing, row_id)
