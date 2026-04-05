
# core/services/security_service.py
import logging

logger = logging.getLogger(__name__)

class PermissionDeniedError(Exception):
    """Excepción personalizada para rechazar operaciones no autorizadas."""
    pass

class SecurityService:
    """
    Orquestador de Seguridad y RBAC.
    Evalúa si una acción está permitida para el usuario actual.
    """
    def __init__(self, security_repo):
        self.repo = security_repo
        # Caché temporal en RAM: {(usuario_id, sucursal_id): {'cancel_sale', 'issue_refund'}}
        self._permissions_cache = {}

    def load_permissions(self, usuario_id: int, sucursal_id: int):
        """Carga los permisos desde la BD y los guarda en RAM."""
        perms = self.repo.get_user_permissions(usuario_id, sucursal_id)
        self._permissions_cache[(usuario_id, sucursal_id)] = perms
        return perms

    def has_permission(self, usuario_id: int, sucursal_id: int, required_permission: str) -> bool:
        """Verifica si el usuario tiene el permiso. Si no está en caché, lo busca."""
        cache_key = (usuario_id, sucursal_id)
        
        if cache_key not in self._permissions_cache:
            self.load_permissions(usuario_id, sucursal_id)
            
        user_perms = self._permissions_cache.get(cache_key, set())
        
        # Si tiene el permiso maestro 'admin_all', se le permite todo
        if 'admin_all' in user_perms:
            return True
            
        return required_permission in user_perms

    def enforce(self, usuario_id: int, sucursal_id: int, required_permission: str):
        """Si no tiene permiso, lanza una excepción que detiene la ejecución inmediatamente."""
        if not self.has_permission(usuario_id, sucursal_id, required_permission):
            logger.warning(f"Intento de acceso denegado: Usuario {usuario_id} intentó '{required_permission}'")
            raise PermissionDeniedError(f"No tienes autorización para realizar esta acción: {required_permission}")
        
    def clear_cache(self, usuario_id: int = None, sucursal_id: int = None):
        """Limpia la caché (útil si se le cambian los roles a un usuario en vivo)."""
        if usuario_id and sucursal_id:
            self._permissions_cache.pop((usuario_id, sucursal_id), None)
        else:
            self._permissions_cache.clear()