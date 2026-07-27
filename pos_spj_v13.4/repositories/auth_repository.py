# repositories/auth_repository.py — SPJ POS v13.30
"""
Capa de acceso a datos para autenticación.
v13.30: Retorna sucursal_nombre + sucursales disponibles para el usuario.
Born-clean UUIDv7: sin fallbacks a 'Principal' ni a IDs enteros inventados;
la sucursal activa de terminal la resuelve la configuración de instalación,
no este repositorio.
"""
import logging

logger = logging.getLogger(__name__)

# Filtro canónico de identidad válida (mismo contrato que ConfigRepository).
_VALID_BRANCH_ID_SQL = (
    "id IS NOT NULL AND TRIM(id) != '' "
    "AND LOWER(TRIM(id)) NOT IN ('none','null')"
)


def _is_invalid_identity(value) -> bool:
    return value is None or str(value).strip().lower() in ("", "none", "null")


class AuthRepository:

    def __init__(self, db_conn):
        self.db = db_conn

    def _detect_password_column(self) -> str:
        """Detecta la columna de contraseña por compatibilidad legacy."""
        cursor = self.db.cursor()
        cursor.execute("PRAGMA table_info(usuarios)")
        columnas = [col[1] for col in cursor.fetchall()]
        for nombre in ["password_hash", "contrasena", "password", "clave"]:
            if nombre in columnas:
                return nombre
        return "contrasena"

    def get_user_by_username(self, username: str) -> dict:
        """
        Busca un usuario activo. Retorna datos + nombre de sucursal.
        Maneja dinámicamente la columna de contraseña por compatibilidad.
        Si la sucursal del usuario no resuelve, sucursal_id/nombre quedan
        vacíos: NO se inventa 'Principal'.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("PRAGMA table_info(usuarios)")
            columnas = [col[1] for col in cursor.fetchall()]
            col_pass = self._detect_password_column()

            # v13.30: JOIN con sucursales para obtener nombre
            has_suc = "sucursal_id" in columnas
            if has_suc:
                query = (
                    f"SELECT u.id, u.usuario, u.{col_pass}, u.rol, u.nombre, "
                    f"u.sucursal_id, COALESCE(s.nombre, '') as sucursal_nombre "
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

            suc_id = row['sucursal_id'] if has_suc else None
            if _is_invalid_identity(suc_id):
                suc_id = ""
                suc_nombre = ""
            else:
                suc_id = str(suc_id)
                suc_nombre = (row['sucursal_nombre'] if has_suc else '') or ""

            user_data = {
                'id': row['id'],
                'username': row['usuario'],
                'password_hash': row[col_pass],
                'rol': row['rol'].lower() if row['rol'] else 'vendedor',
                'nombre': row['nombre'],
                'sucursal_id': suc_id,
                'sucursal_nombre': suc_nombre,
                'password_column': col_pass,
            }

            # v13.30: Cargar sucursales disponibles para este usuario
            user_data['sucursales_disponibles'] = self._get_sucursales_usuario(
                user_data['id'], user_data['rol'], user_data['sucursal_id'])

            return user_data

        except Exception as e:
            logger.error(f"Error consultando usuario {username}: {str(e)}")
            raise RuntimeError("Error de base de datos al consultar el usuario.")

    def migrate_password_hash(self, user_id: str, new_hash: str) -> bool:
        """
        Migra hash de contraseña a formato fuerte (bcrypt).
        """
        try:
            col_pass = self._detect_password_column()
            self.db.execute(
                f"UPDATE usuarios SET {col_pass}=? WHERE id=?",
                (new_hash, str(user_id)),
            )
            try:
                self.db.commit()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning("No se pudo migrar password_hash usuario %s: %s", user_id, e)
            return False

    def _get_sucursales_usuario(self, user_id: str, rol: str, user_suc_id: str) -> list:
        """
        Retorna lista de sucursales a las que el usuario tiene acceso.
        - admin/gerente: todas las activas con UUID válido
        - otros: solo la suya (si resuelve a una sucursal real)
        Nunca inventa una sucursal 'Principal' ni IDs por default.
        """
        try:
            if rol in ('admin', 'gerente', 'gerente_rh', 'superadmin'):
                rows = self.db.execute(
                    f"SELECT id, nombre FROM sucursales "
                    f"WHERE activa=1 AND {_VALID_BRANCH_ID_SQL} ORDER BY nombre"
                ).fetchall()
                if rows:
                    return [{'id': str(r['id']), 'nombre': r['nombre']} for r in rows]
            # Usuario de una sola sucursal — retornar solo la suya si es válida
            if not _is_invalid_identity(user_suc_id):
                row = self.db.execute(
                    f"SELECT id, nombre FROM sucursales "
                    f"WHERE {_VALID_BRANCH_ID_SQL} AND id=?",
                    (str(user_suc_id),),
                ).fetchone()
                if row:
                    return [{'id': str(row['id']), 'nombre': row['nombre']}]
            logger.warning(
                "_get_sucursales_usuario: usuario %s sin sucursal válida "
                "(sucursal_id=%r); lista vacía.", user_id, user_suc_id,
            )
            return []
        except Exception as e:
            logger.debug("_get_sucursales_usuario: %s", e)
            return []
