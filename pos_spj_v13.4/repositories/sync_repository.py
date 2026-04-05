# repositories/sync_repository.py — DEPRECADO en v13.2
"""
Cuarto sistema de sync — abandonado a mitad.
get_pending_events() retorna None (nunca completado).
Mantenido como stub para no romper imports.
Usar sync.event_logger.EventLogger en código nuevo.
"""
import warnings
import logging
logger = logging.getLogger("spj.sync_repo")


class SyncRepository:
    """DEPRECATED — stub vacío. Usa sync.event_logger.EventLogger."""

    def __init__(self, db_conn):
        self.db = db_conn

    def insert_event(self, tipo, entidad, entidad_id=None, payload=None,
                     sucursal_id=1, usuario="Sistema") -> int:
        """Delegado a EventLogger."""
        try:
            from sync.event_logger import EventLogger
            return EventLogger(self.db).registrar(
                tipo=tipo, entidad=entidad, entidad_id=entidad_id,
                payload=payload or {}, sucursal_id=sucursal_id, usuario=usuario
            )
        except Exception as e:
            logger.debug("SyncRepository.insert_event delegated: %s", e)
            return -1

    def get_pending_events(self, limit=100):
        """Previously returned None. Now delegates to EventLogger."""
        try:
            from sync.event_logger import EventLogger
            return EventLogger(self.db).pendientes(limit)
        except Exception:
            return []

    def mark_as_synced(self, event_id: int) -> None:
        try:
            from sync.event_logger import EventLogger
            EventLogger(self.db).marcar_sincronizado(event_id)
        except Exception as e:
            logger.debug("SyncRepository.mark_as_synced: %s", e)
