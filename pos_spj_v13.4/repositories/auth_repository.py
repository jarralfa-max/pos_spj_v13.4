# repositories/auth_repository.py — SPJ POS v13.30
"""
Capa de acceso a datos para autenticación.
v13.30: Retorna sucursal_nombre + sucursales disponibles para el usuario.
"""
import logging

logger = logging.getLogger(__name__)


class AuthRepository:

    def __init__(self, db_conn):
        self.db = db_conn

    def get_user_by_username(self, username: str) -> dict:
        """
        Busca un usuario activo. Retorna datos + nombre de sucursal.
        Maneja dinámicamente la columna de contraseña por compatibilidad.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("PRAGMA table_info(usuarios)")
            columnas = [col[1] for col in cursor.fetchall()]

            col_pass = "contrasena"
            for nombre in ["contrasena", "password", "password_hash", "clave"]:
                if nombre in columnas:
                    col_pass = nombre
                    break

            # v13.30: JOIN con sucursales para obtener nombre
            has_suc = "sucursal_id" in columnas
            if has_suc:
                query = (
                    f"SELECT u.id, u.usuario, u.{col_pass}, u.rol, u.nombre, "
                    f"u.sucursal_id, COALESCE(s.nombre, 'Principal') as sucursal_nombre "
                    f"FROM usuarios u "
                    f"LEFT JOIN sucursales s ON s.id = u.sucursal_id "
                    f"WHERE u.usuario = ? AND u.activo = 1"
                )
            else:
                query = (
                    f"SELECT u.id, u.usuario, u.{col_pass}, u.rol, u.nombre "
                    f"FROM usuarios u "
                    f"WHERE u.usuario = ? AND u.activo = 1"
                )

            row = self.db.execute(query, (username,)).fetchone()
            if not row:
                return None

            user_data = {
                'id': row['id'],
                'username': row['usuario'],
                'password_hash': row[col_pass],
                'rol': row['rol'].lower() if row['rol'] else 'vendedor',
                'nombre': row['nombre'],
                'sucursal_id': row['sucursal_id'] if has_suc else 1,
                'sucursal_nombre': row['sucursal_nombre'] if has_suc else 'Principal',
            }

            # v13.30: Cargar sucursales disponibles para este usuario
            user_data['sucursales_disponibles'] = self._get_sucursales_usuario(
                user_data['id'], user_data['rol'], user_data['sucursal_id'])

            return user_data

        except Exception as e:
            logger.error(f"Error consultando usuario {username}: {str(e)}")
            raise RuntimeError("Error de base de datos al consultar el usuario.")

    def _get_sucursales_usuario(self, user_id: int, rol: str, default_suc: int) -> list:
        """
        Retorna lista de sucursales a las que el usuario tiene acceso.
        - admin/gerente: todas las activas
        - otros: solo la suya
        """
        try:
            if rol in ('admin', 'gerente', 'gerente_rh', 'superadmin'):
                rows = self.db.execute(
                    "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
                ).fetchall()
                if rows:
                    return [{'id': r['id'], 'nombre': r['nombre']} for r in rows]
            # Single branch user — retornar solo la suya
            row = self.db.execute(
                "SELECT id, nombre FROM sucursales WHERE id=?", (default_suc,)
            ).fetchone()
            if row:
                return [{'id': row['id'], 'nombre': row['nombre']}]
            return [{'id': default_suc, 'nombre': 'Principal'}]
        except Exception as e:
            logger.debug("_get_sucursales_usuario: %s", e)
            return [{'id': default_suc, 'nombre': 'Principal'}]
