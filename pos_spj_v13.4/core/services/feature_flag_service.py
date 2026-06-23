
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

    def get_branch_flags(self, branch_id) -> dict:
        """Carga (si hace falta) y devuelve una copia de los flags de la sucursal.

        Pensado para que la UI lea los toggles sin tocar SQL ni la caché interna.
        """
        self.load_branch_flags(branch_id)
        return dict(self._cache.get(branch_id, {}))

    def set_enabled(self, feature_name: str, branch_id, enabled: bool) -> None:
        """Activa/desactiva un módulo para una sucursal e invalida la caché.

        Ruta canónica para la UI de Configuración de Módulos: evita que PyQt
        ejecute SQL o haga commit directamente.
        """
        self.repo.set_flag(feature_name, branch_id, bool(enabled))
        self._cache.pop(branch_id, None)

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