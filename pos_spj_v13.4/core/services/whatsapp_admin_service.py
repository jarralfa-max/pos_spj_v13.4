# core/services/whatsapp_admin_service.py
"""Servicio de administración del módulo WhatsApp."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository
from core.repositories.whatsapp_history_repository import WhatsAppHistoryRepository
from core.repositories.whatsapp_metrics_repository import WhatsAppMetricsRepository

logger = logging.getLogger("spj.service.whatsapp_admin")


class WhatsAppAdminService:
    """
    Fachada de administración para el módulo WhatsApp.
    La UI llama solo a este servicio; nunca accede a DB directamente.
    """

    def __init__(self, db):
        self._cfg_repo = WhatsAppConfigRepository(db)
        self._hist_repo = WhatsAppHistoryRepository(db)
        self._met_repo = WhatsAppMetricsRepository(db)

    # ── Números por sucursal ──────────────────────────────────────────────────

    def get_numeros(self) -> List[Tuple]:
        return self._cfg_repo.get_numeros()

    def get_numero_by_id(self, numero_id: int) -> Optional[tuple]:
        return self._cfg_repo.get_numero_by_id(numero_id)

    def save_numero(self, *, numero_id: Optional[int] = None, suc_id, canal, proveedor,
                    numero, phone_id, token, sid, rasa_url, rasa_act, activo,
                    suc_nombre) -> None:
        if numero_id:
            self._cfg_repo.update_numero(
                numero_id, suc_id, canal, proveedor, numero, phone_id,
                token, sid, rasa_url, rasa_act, activo, suc_nombre)
        else:
            self._cfg_repo.insert_numero(
                suc_id, canal, proveedor, numero, phone_id,
                token, sid, rasa_url, rasa_act, activo, suc_nombre)

    def delete_numero(self, numero_id: int) -> None:
        self._cfg_repo.delete_numero(numero_id)

    def get_sucursales_activas(self) -> List[tuple]:
        return self._cfg_repo.get_sucursales_activas()

    # ── Configuración del bot ─────────────────────────────────────────────────

    _BOT_DEFAULTS = {
        "bot_nombre":     "Asistente SPJ",
        "bot_activo":     "0",
        "rasa_activo":    "0",
        "rasa_url":       "http://localhost:5005",
        "timeout":        "30",
        "msg_bienvenida": "Hola, bienvenido a nuestro servicio.",
        "cotizaciones":   "1",
        "rrhh_notif":     "1",
    }

    def get_bot_config(self) -> Dict:
        raw = self._cfg_repo.get_configs(
            list(self._BOT_DEFAULTS.keys()), dict(self._BOT_DEFAULTS))
        return {
            "bot_nombre":     raw["bot_nombre"],
            "bot_activo":     raw["bot_activo"] == "1",
            "rasa_activo":    raw["rasa_activo"] == "1",
            "rasa_url":       raw["rasa_url"],
            "timeout":        int(raw["timeout"]),
            "msg_bienvenida": raw["msg_bienvenida"],
            "cotizaciones":   raw["cotizaciones"] == "1",
            "rrhh_notif":     raw["rrhh_notif"] == "1",
        }

    def save_bot_config(self, config: Dict) -> None:
        s = self._cfg_repo.set_config
        s("bot_nombre",     config.get("bot_nombre", ""))
        s("bot_activo",     "1" if config.get("bot_activo") else "0")
        s("rasa_activo",    "1" if config.get("rasa_activo") else "0")
        s("rasa_url",       config.get("rasa_url", ""))
        s("timeout",        str(config.get("timeout", 30)))
        s("msg_bienvenida", config.get("msg_bienvenida", ""))
        s("cotizaciones",   "1" if config.get("cotizaciones") else "0")
        s("rrhh_notif",     "1" if config.get("rrhh_notif") else "0")
        # Legacy key without prefix
        self._cfg_repo.set_config_raw("rasa_url", config.get("rasa_url", ""))
        self._cfg_repo.commit()

    def get_config_value(self, key: str, default: str = "") -> str:
        return self._cfg_repo.get_config(key, default)

    def save_webhook_config(self, verify_token: str) -> None:
        self._cfg_repo.set_config_raw("wa_verify_token", verify_token)
        self._cfg_repo.commit()

    # ── Historial ─────────────────────────────────────────────────────────────

    def get_history(self, buscar: str = "") -> List[Tuple]:
        return self._hist_repo.get_history(buscar)

    # ── Métricas ──────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict:
        return self._met_repo.get_metrics()

    # ── Test de conexión ──────────────────────────────────────────────────────

    def test_connection(self, wa_service=None) -> bool:
        if wa_service and hasattr(wa_service, "test_connection"):
            return wa_service.test_connection()
        try:
            from core.integrations.whatsapp_client import WhatsAppClient
            client = WhatsAppClient()
            return client.health_check()
        except Exception as e:
            logger.debug("test_connection: %s", e)
            return False
