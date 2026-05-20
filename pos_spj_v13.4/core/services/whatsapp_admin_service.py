# core/services/whatsapp_admin_service.py
"""Facade de administración WhatsApp. La UI solo llama este servicio."""
from __future__ import annotations
import logging
from typing import Optional, List, Dict

from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository
from core.repositories.whatsapp_history_repository import WhatsAppHistoryRepository
from core.repositories.whatsapp_metrics_repository import WhatsAppMetricsRepository

logger = logging.getLogger("spj.service.wa_admin")


class WhatsAppAdminService:
    def __init__(self, conn):
        self.conn = conn
        self._cfg_repo = WhatsAppConfigRepository(conn)
        self._hist_repo = WhatsAppHistoryRepository(conn)
        self._metrics_repo = WhatsAppMetricsRepository(conn)

    # ── Números / sucursales ───────────────────────────────────────────────────

    def list_numeros(self) -> List[Dict]:
        return self._cfg_repo.list_numeros()

    def get_numero(self, row_id: int) -> Optional[Dict]:
        return self._cfg_repo.get_numero(row_id)

    def save_numero(self, data: Dict, row_id: Optional[int] = None) -> bool:
        return self._cfg_repo.save_numero(data, row_id)

    def delete_numero(self, row_id: int) -> bool:
        return self._cfg_repo.delete_numero(row_id)

    def list_sucursales(self) -> List[Dict]:
        return self._cfg_repo.list_sucursales_activas()

    # ── Configuración bot ──────────────────────────────────────────────────────

    def get_config(self, key: str, default: str = "") -> str:
        return self._cfg_repo.get_config(key, default)

    def save_bot_config(self, cfg: Dict[str, str]) -> None:
        self._cfg_repo.set_config_batch(cfg)
        # Keep legacy key rasa_url in sync
        if "rasa_url" in cfg:
            try:
                self.conn.execute(
                    "INSERT INTO configuraciones(clave,valor) VALUES('rasa_url',?) "
                    "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                    (cfg["rasa_url"],))
                self.conn.commit()
            except Exception:
                pass

    # ── Historial ──────────────────────────────────────────────────────────────

    def get_history(self, search: str = "", limit: int = 200) -> List[Dict]:
        return self._hist_repo.get_history(search, limit)

    # ── Métricas ───────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict:
        m = self._metrics_repo.get_metrics()
        m["bot_activo"] = self.get_config("bot_activo", "0") == "1"
        m["rasa_activo"] = self.get_config("rasa_activo", "0") == "1"
        m["cotizaciones"] = self.get_config("cotizaciones", "1") == "1"
        m["rasa_url"] = self.get_config("rasa_url", "")
        return m

    # ── Test conexión ──────────────────────────────────────────────────────────

    def test_connection(self) -> bool:
        """Delega al WhatsAppService canónico."""
        try:
            from core.services.whatsapp_service import WhatsAppService
            svc = WhatsAppService(self.conn)
            if hasattr(svc, "test_connection"):
                return svc.test_connection()
            # Verificación mínima: credenciales cargadas
            return bool(svc.config.meta_token and svc.config.meta_phone_id)
        except Exception as e:
            logger.debug("test_connection: %s", e)
            return False
