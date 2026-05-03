
# repositories/security_repository.py
import logging

logger = logging.getLogger(__name__)

class SecurityRepository:
    """
    Capa de acceso a datos para RBAC (Role-Based Access Control).
    Extrae los permisos exactos de un usuario según su rol en una sucursal.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_user_permissions(self, usuario_id: int, sucursal_id: int) -> set:
        """
        Devuelve un Set (conjunto) con los códigos de permiso del usuario.
        Ejemplo: {'cancel_sale', 'adjust_inventory', 'edit_price'}
        """
        query = """
            SELECT DISTINCT p.codigo
            FROM permisos p
            INNER JOIN roles_permisos rp ON p.id = rp.permiso_id
            INNER JOIN usuarios_roles ur ON rp.rol_id = ur.rol_id
            WHERE ur.usuario_id = ? AND ur.sucursal_id = ?
        """
        try:
            rows = self.db.execute(query, (usuario_id, sucursal_id)).fetchall()
            return {row['codigo'] for row in rows}
        except Exception as e:
            logger.error(f"Error al consultar permisos para usuario {usuario_id}: {str(e)}")
            return set()