
# core/services/feature_flag_service.py
import logging

logger = logging.getLogger(__name__)

class FeatureFlagService:
    """
    Servicio de control de Módulos (Feature Flags).
    Mantiene un caché en memoria por sucursal para consultas instantáneas.
    """
    def __init__(self, repo):
        self.repo = repo
        # Estructura del caché: { branch_id: {'delivery': True, 'whatsapp': False} }
        self._cache = {}

    def load_branch_flags(self, branch_id: int):
        """Carga los flags de una sucursal desde la BD a la RAM."""
        flags = self.repo.get_flags_by_branch(branch_id)
        self._cache[branch_id] = flags
        logger.debug(f"Feature flags cargados para la sucursal {branch_id}: {flags}")

    def is_enabled(self, feature_name: str, branch_id: int) -> bool:
        """
        Verifica si una característica está encendida.
        Si la sucursal no está en caché, la carga automáticamente.
        """
        if branch_id not in self._cache:
            self.load_branch_flags(branch_id)
            
        branch_flags = self._cache.get(branch_id, {})
        
        # Si el flag no existe en la BD, por seguridad asumimos que está apagado (False)
        return branch_flags.get(feature_name, False)

    def require_feature(self, feature_name: str, branch_id: int):
        """
        Método duro para el Backend: Lanza un error si el módulo está apagado.
        Ideal para blindar servicios (ej. evitar procesar un pedido de WhatsApp si no está pagado).
        """
        if not self.is_enabled(feature_name, branch_id):
            raise PermissionError(f"El módulo '{feature_name}' no está habilitado para esta sucursal.")