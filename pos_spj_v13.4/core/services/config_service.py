
# core/services/config_service.py
import logging

logger = logging.getLogger(__name__)

class ConfigService:
    """
    Gestor central de configuraciones.
    Mantiene los ajustes en RAM (Caché) para lecturas a velocidad de la luz.
    """
    def __init__(self, settings_repo):
        self.repo = settings_repo
        self._cache = {}
        self.refresh_cache() # Carga todo a RAM en cuanto el sistema arranca

    def refresh_cache(self):
        """Lee la BD y actualiza la RAM."""
        self._cache = self.repo.get_all_settings()
        logger.info(f"Configuración cargada: {len(self._cache)} parámetros en memoria.")

    def get(self, key: str, default_value=None):
        """
        Obtiene una configuración al instante desde la RAM.
        Si no existe, devuelve el valor por defecto provisto.
        """
        return self._cache.get(key, default_value)

    def set(self, key: str, value):
        """
        Actualiza una configuración tanto en RAM como en la BD.
        """
        self._cache[key] = value
        # Se guarda como string en la BD
        # ConfigRepository uses save_setting() (UPSERT into configuraciones)
        self.repo.save_setting(key, str(value))
        logger.debug(f"Configuración '{key}' actualizada a: {value}")
        
    # --- Métodos Auxiliares de Conveniencia (Feature Toggles) ---
    
    @property
    def is_scale_enabled(self) -> bool:
        return self.get('scale_enabled', False)

    @property
    def is_loyalty_enabled(self) -> bool:
        return self.get('enable_loyalty', False)
        
    @property
    def get_ticket_printer(self) -> str:
        return self.get('ticket_printer', 'Ninguna')