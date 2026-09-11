"""Directorio de usuarios y roles — lo que administra Configuración → Seguridad.

Reemplaza la parte de `repositories/config_repository.py` (fuera de las raíces
válidas, §1) que atendía a `UserManagementService`/`RoleManagementService`. No
es una copia: se reescribió contra el esquema real, reutilizando
`validate_uuidv7()` de `backend/shared/ids.py` en vez de repetir la validación
de identidad, y sin la indirección `_uuid_column()`/`_select_identity_sql()`
que el original arrastraba — en el modelo born-clean `id` ES el UUID, así que
aquellas funciones devolvían siempre la constante `"id"`.

REGLA CERO de identidad: `usuarios.id`, `roles.id` y `sucursales.id` son UUIDv7
TEXT. Nunca se convierten a entero ni se aceptan como `"1"`. La excepción es
`personal.id` (empleados), que en este esquema sigue siendo entero: el selector
de empleados lo devuelve tal cual porque es lo que guarda
`usuarios.empleado_id`.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import new_uuid, validate_uuidv7

#: Filtro de lectura contra identidades corruptas. No basta con `IS NOT NULL`:
#: lo que aparece en la práctica son los literales `'None'`/`'null'` de un
#: `str(None)` accidental, que sí pasarían ese filtro y llegarían a un selector
#: como si fueran sucursales reales.
_VALID_ID_SQL = (
    "id IS NOT NULL AND TRIM(id) != '' "
    "AND LOWER(TRIM(id)) NOT IN ('none','null')"
)


class SqliteUserDirectoryRepository(SettingsRepositoryBase):
    # ── usuarios ─────────────────────────────────────────────────────────
    def list_users(self, limit: int = 200) -> list[tuple]:
        """Filas para la tabla de usuarios de Configuración.

        `intentos_fallidos` y `bloqueado_hasta` viajan en la fila porque son lo
        que alimenta el desbloqueo manual de una cuenta desde esa misma
        pantalla; sin ellos la tabla no puede decir por qué alguien no entra.
        """
        return self._conn.execute(
            """
            SELECT u.id, u.usuario, u.nombre,
                   COALESCE(r.nombre, 'cajero') AS rol,
                   COALESCE(s.nombre, '')       AS sucursal,
                   u.activo,
                   u.id                          AS usuario_uuid,
                   s.id                          AS sucursal_uuid,
                   COALESCE(u.intentos_fallidos, 0),
                   u.bloqueado_hasta
            FROM usuarios u
            LEFT JOIN roles r      ON r.nombre = u.rol
            LEFT JOIN sucursales s ON s.id = u.sucursal_id
            ORDER BY u.nombre
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_user_form_data(self, user_id: str) -> tuple | None:
        return self._conn.execute(
            "SELECT usuario, nombre, email, rol, sucursal_id, activo, empleado_id"
            " FROM usuarios WHERE id = ?",
            (validate_uuidv7(user_id),),
        ).fetchone()

    def save_user(
        self, *, user_id: str | None, username: str, name: str, email: str,
        role: str, branch_id: str, active: bool, employee_id: int | None,
        password_hash: str | None,
    ) -> str:
        """Alta o edición. Devuelve el id del usuario persistido.

        `password_hash` a `None` significa "no tocar la contraseña", no
        "ponerla vacía": la columna se omite del UPDATE en ese caso. Incluirla
        siempre habría borrado la contraseña en cada edición del formulario que
        no la rellena, que es la mayoría.
        """
        branch_uuid = self._require_existing_branch(branch_id)
        persisted_id = validate_uuidv7(user_id) if user_id else new_uuid()

        fields = ["usuario", "nombre", "email", "rol", "activo", "empleado_id", "sucursal_id"]
        values: list[object] = [
            username, name, email, role, 1 if active else 0, employee_id, branch_uuid,
        ]
        if password_hash is not None:
            fields.append("password_hash")
            values.append(password_hash)

        if user_id and self._exists("usuarios", persisted_id):
            assignments = ", ".join(f"{field} = ?" for field in fields)
            self._conn.execute(
                f"UPDATE usuarios SET {assignments} WHERE id = ?",
                (*values, persisted_id),
            )
        else:
            columns = ["id", *fields]
            placeholders = ", ".join("?" for _ in columns)
            self._conn.execute(
                f"INSERT INTO usuarios ({', '.join(columns)}) VALUES ({placeholders})",
                (persisted_id, *values),
            )

        if employee_id:
            # El vínculo es bidireccional: `personal.usuario_id` es lo que lee
            # el módulo de RRHH para saber qué empleado corresponde a la cuenta.
            self._conn.execute(
                "UPDATE personal SET usuario_id = ? WHERE id = ?",
                (persisted_id, employee_id),
            )
        return persisted_id

    def set_user_active(self, user_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE usuarios SET activo = ? WHERE id = ?",
            (1 if active else 0, validate_uuidv7(user_id)),
        )

    # ── roles ────────────────────────────────────────────────────────────
    def list_roles(self) -> list[tuple]:
        """`(id, nombre, descripcion, num_usuarios)` por rol.

        El conteo cuenta sólo usuarios ACTIVOS: la pantalla usa ese número para
        avisar de que un rol está en uso antes de tocarlo, y un rol que sólo
        tiene cuentas dadas de baja no está en uso.
        """
        return self._conn.execute(
            """
            SELECT r.id, r.nombre, r.descripcion, COUNT(u.id) AS num_usuarios
            FROM roles r
            LEFT JOIN usuarios u ON u.rol = r.nombre AND u.activo = 1
            GROUP BY r.id
            ORDER BY r.nombre
            """
        ).fetchall()

    def role_names(self) -> list[str]:
        rows = self._conn.execute("SELECT nombre FROM roles ORDER BY nombre").fetchall()
        return [row[0] for row in rows]

    def save_role(self, *, role_id: str | None, name: str, description: str) -> str:
        persisted_id = validate_uuidv7(role_id) if role_id else new_uuid()
        if role_id and self._exists("roles", persisted_id):
            self._conn.execute(
                "UPDATE roles SET nombre = ?, descripcion = ? WHERE id = ?",
                (name, description, persisted_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO roles (id, nombre, descripcion) VALUES (?, ?, ?)",
                (persisted_id, name, description),
            )
        return persisted_id

    # ── selectores de formulario ─────────────────────────────────────────
    def active_branches_for_selector(self) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            f"SELECT id, nombre FROM sucursales"
            f" WHERE activa = 1 AND {_VALID_ID_SQL} ORDER BY nombre"
        ).fetchall()
        return [(str(row[0]), row[1]) for row in rows]

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT id, nombre || ' ' || COALESCE(apellidos, '')"
            " FROM personal WHERE activo = 1 ORDER BY nombre"
        ).fetchall()
        return [(row[0], str(row[1]).strip()) for row in rows]

    # ── helpers ──────────────────────────────────────────────────────────
    def _exists(self, table: str, entity_id: str) -> bool:
        return bool(self._conn.execute(
            f"SELECT 1 FROM {table} WHERE id = ?", (entity_id,)).fetchone())

    def _require_existing_branch(self, branch_id: str) -> str:
        """Valida que la sucursal exista antes de asociar un usuario a ella.

        Sin esta comprobación, un `branch_id` con forma de UUIDv7 pero sin fila
        detrás se guardaría igual, y el usuario quedaría asignado a una
        sucursal inexistente: entraría sin sucursal activa y el shell no le
        mostraría ningún módulo, sin ningún error que explicara por qué.
        """
        branch_uuid = validate_uuidv7(branch_id)
        if not self._exists("sucursales", branch_uuid):
            raise ValueError("branch_id debe referenciar una sucursal existente")
        return branch_uuid
