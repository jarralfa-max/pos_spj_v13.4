import logging
from uuid import UUID

from backend.shared.ids import new_uuid
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS, normalize_permission

logger = logging.getLogger(__name__)


class ConfigRepository:
    """Acceso a datos para Configuración con contratos canónicos UUID."""

    def __init__(self, db_conn):
        self.db = db_conn

    @property
    def connection(self):
        """Expose the underlying connection so the owning service/use case can
        drive the UnitOfWork transaction boundary. The repository itself never
        commits or rolls back."""
        return self.db

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return bool(row)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        try:
            rows = self.db.execute(f"PRAGMA table_info({table_name})").fetchall()
        except Exception:
            return False
        return any(str(row[1]) == column_name for row in rows)

    def _uuid_column(self, table_name: str) -> str:
        # Born-clean: id ES el UUID canónico; no existe columna uuid dual.
        return "id"

    def _require_uuid_column(self, table_name: str) -> str:
        return "id"

    # Identidades corruptas que jamás deben circular como id de sucursal:
    # NULL, cadena vacía, o los literales "None"/"null" (str(None) accidental).
    @staticmethod
    def _is_invalid_identity(value) -> bool:
        return value is None or str(value).strip().lower() in ("", "none", "null")

    # Filtro SQL equivalente para lecturas (selectores nunca reciben filas corruptas).
    _VALID_BRANCH_ID_SQL = (
        "id IS NOT NULL AND TRIM(id) != '' "
        "AND LOWER(TRIM(id)) NOT IN ('none','null')"
    )

    def _require_uuidv7(self, value: str, field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        try:
            parsed = UUID(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7") from exc
        if parsed.version != 7 or normalized != str(parsed):
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7")
        return normalized

    def _select_identity_sql(self, table_name: str, *, alias: str = "id", table_alias: str | None = None) -> str:
        uuid_column = self._require_uuid_column(table_name)
        qualified = f"{table_alias}.{uuid_column}" if table_alias else uuid_column
        return f"{qualified} AS {alias}"

    def _row_id_from_uuid(self, table_name: str, entity_id: str | None) -> str | None:
        """Born-clean: id ES el UUID; devuelve el id si la fila existe."""
        if not entity_id:
            return None
        row = self.db.execute(f"SELECT id FROM {table_name} WHERE id=?", (entity_id,)).fetchone()
        return str(row[0]) if row else None

    def _uuid_from_row_id(self, table_name: str, row_id) -> str | None:
        if row_id is None:
            return None
        row = self.db.execute(f"SELECT id FROM {table_name} WHERE id=?", (row_id,)).fetchone()
        return str(row[0]) if row else None

    def _resolve_db_identifier(self, table_name: str, entity_id: str) -> tuple[str, object]:
        uuid_column = self._require_uuid_column(table_name)
        return uuid_column, self._require_uuidv7(entity_id, f"{table_name}.id")

    def _resolve_branch_row(self, branch_id: str | None) -> tuple[str | None, str | None]:
        if self._is_invalid_identity(branch_id):
            return None, None
        branch_uuid = self._require_uuidv7(branch_id, "branch_id")
        if self._row_id_from_uuid("sucursales", branch_uuid) is None:
            raise ValueError("branch_id must reference an existing branch UUID")
        return branch_uuid, branch_uuid

    def _resolve_role_row(self, role_id: str) -> tuple[int | None, str | None]:
        role_uuid = self._require_uuidv7(role_id, "role_id")
        if self._row_id_from_uuid("roles", role_uuid) is None:
            raise ValueError("role_id must reference an existing role UUID")
        return role_uuid, role_uuid

    def _resolve_user_row(self, user_id: str) -> tuple[int | None, str | None]:
        user_uuid = self._require_uuidv7(user_id, "user_id")
        row_id = self._row_id_from_uuid("usuarios", user_uuid)  # id == uuid
        if row_id is None:
            raise ValueError("user_id must reference an existing user UUID")
        return row_id, user_uuid

    # --- SUCURSALES ---
    def get_all_branches(self) -> list:
        rows = self.db.execute(
            f"SELECT id, nombre, direccion, telefono, activa FROM sucursales "
            f"WHERE activa = 1 AND {self._VALID_BRANCH_ID_SQL}"
        ).fetchall()
        return [dict(row) for row in rows]

    # --- AJUSTES GLOBALES (Key-Value) ---
    def get_setting(self, key: str, default_value: str = "") -> str:
        row = self.db.execute("SELECT valor FROM configuraciones WHERE clave = ?", (key,)).fetchone()
        return row["valor"] if row else default_value

    def save_setting(self, key: str, value: str):
        self.db.execute(
            """
            INSERT INTO configuraciones (clave, valor) VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """,
            (key, str(value)),
        )

    def get_all_settings(self) -> dict:
        rows = self.db.execute("SELECT clave, valor FROM configuraciones").fetchall()
        return {row["clave"]: row["valor"] for row in rows}

    def settings_schema_is_ready(self) -> bool:
        required_tables = {
            "configuraciones",
            "sucursales",
            "usuarios",
            "roles",
            "rol_permisos",
            "personal",
            "audit_logs",
            "cierre_mensual",
            "happy_hour_rules",
        }
        rows = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (%s)"
            % ",".join("?" for _ in required_tables),
            tuple(required_tables),
        ).fetchall()
        existing = {row[0] for row in rows}
        return required_tables.issubset(existing)

    # --- CONFIGURACIÓN FASE 7 / MÓDULO CONFIGURACIÓN ---
    def get_settings(self, keys: list[str]) -> dict:
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        rows = self.db.execute(
            f"SELECT clave, valor FROM configuraciones WHERE clave IN ({placeholders})",
            tuple(keys),
        ).fetchall()
        return {row["clave"]: row["valor"] for row in rows}

    def get_loyalty_program_config(self) -> dict | None:
        row = self.db.execute(
            """
            SELECT id, nombre_programa, puntos_por_peso, niveles, requisitos, descuentos, activo
            FROM config_programa_fidelidad
            WHERE id = 1
            """
        ).fetchone()
        return dict(row) if row else None

    def save_loyalty_program_config(
        self,
        *,
        name: str,
        points_per_peso: float,
        levels: str | None = None,
        requirements: str | None = None,
        discounts: str | None = None,
        active: bool = True,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO config_programa_fidelidad
                (id, nombre_programa, puntos_por_peso, niveles, requisitos, descuentos, activo)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nombre_programa=excluded.nombre_programa,
                puntos_por_peso=excluded.puntos_por_peso,
                niveles=excluded.niveles,
                requisitos=excluded.requisitos,
                descuentos=excluded.descuentos,
                activo=excluded.activo
            """,
            (name, points_per_peso, levels, requirements, discounts, 1 if active else 0),
        )

    def get_module_toggles(self) -> dict[str, bool]:
        rows = self.db.execute("SELECT clave, activo FROM module_toggles").fetchall()
        return {row["clave"]: bool(row["activo"]) for row in rows}

    def set_module_toggle(self, key: str, enabled: bool) -> None:
        self.db.execute(
            """
            INSERT INTO module_toggles(clave, activo)
            VALUES(?, ?)
            ON CONFLICT(clave) DO UPDATE SET activo=excluded.activo
            """,
            (key, 1 if enabled else 0),
        )

    def permission_matrix(self) -> list[tuple[str, list[str]]]:
        matrix: dict[str, list[str]] = {
            module: list(actions)
            for module, actions in CANONICAL_MODULE_PERMISSIONS.items()
        }
        rows = self.db.execute(
            """
            SELECT DISTINCT modulo, accion
            FROM rol_permisos
            WHERE COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            ORDER BY modulo, accion
            """
        ).fetchall()
        for row in rows:
            module = str(row[0]).strip().upper()
            action = str(row[1]).strip().lower()
            if action and action not in matrix.setdefault(module, []):
                matrix[module].append(action)
        if self._table_exists("permisos"):
            permission_rows = self.db.execute(
                """
                SELECT modulo, codigo
                FROM permisos
                WHERE COALESCE(modulo, '') != '' AND COALESCE(codigo, '') != ''
                ORDER BY modulo, codigo
                """
            ).fetchall()
            for row in permission_rows:
                module = str(row[0]).strip().upper()
                code = str(row[1])
                action = code.split(".")[-1].strip().lower() if "." in code else code.strip().lower()
                if action and action not in matrix.setdefault(module, []):
                    matrix[module].append(action)
        return [(module, actions) for module, actions in matrix.items()]

    def get_branch(self, branch_id: str) -> dict | None:
        column, value = self._resolve_db_identifier("sucursales", branch_id)
        row = self.db.execute(f"SELECT * FROM sucursales WHERE {column}=?", (value,)).fetchone()
        return dict(row) if row else None

    def save_branch(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        active: bool,
        branch_id: str | None = None,
    ) -> str:
        if self._is_invalid_identity(branch_id):
            branch_id = None  # "None"/""/null jamás son identidad: creación nueva
        _, branch_uuid = self._resolve_branch_row(branch_id)
        if branch_id is not None:
            self.db.execute(
                "UPDATE sucursales SET nombre=?, direccion=?, telefono=?, activa=? WHERE id=?",
                (name, address, phone, 1 if active else 0, branch_uuid),
            )
            return str(branch_uuid)

        new_branch_uuid = new_uuid()
        fields = ["id", "nombre", "direccion", "telefono", "activa"]
        values: list[object] = [new_branch_uuid, name, address, phone, 1 if active else 0]
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO sucursales ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        return new_branch_uuid

    # --- SUCURSAL DE LA INSTALACIÓN ---
    INSTALLATION_BRANCH_KEY = "sucursal_instalacion_id"

    def get_installation_branch(self) -> tuple[str, str] | None:
        """(id, nombre) de la sucursal anclada a ESTA instalación, o None."""
        row = self.db.execute(
            """
            SELECT s.id, s.nombre FROM sucursales s
            JOIN configuraciones c ON c.clave=? AND c.valor = s.id
            LIMIT 1
            """,
            (self.INSTALLATION_BRANCH_KEY,),
        ).fetchone()
        return (str(row[0]), str(row[1])) if row else None

    def set_installation_branch(self, branch_id: str) -> tuple[str, str]:
        """Ancla esta instalación a la sucursal indicada (UUID, activa).

        El login y el AppContainer leen esta clave para fijar la sucursal
        activa de la sesión. Valida UUIDv7 + existencia + activa.
        """
        _, branch_uuid = self._resolve_branch_row(branch_id)
        row = self.db.execute(
            "SELECT id, nombre FROM sucursales WHERE id=? AND COALESCE(activa,1)=1",
            (branch_uuid,),
        ).fetchone()
        if not row:
            raise ValueError("La sucursal debe existir y estar activa.")
        self.save_setting(self.INSTALLATION_BRANCH_KEY, str(row[0]))
        return str(row[0]), str(row[1])

    def get_branch_delivery_profile(self, branch_id: str) -> dict | None:
        column, value = self._resolve_db_identifier("sucursales", branch_id)
        row = self.db.execute(
            f"""
            SELECT nombre, direccion, telefono, hora_apertura, hora_cierre,
                   dias_operacion, acepta_pedidos_fuera_horario, mensaje_fuera_horario
            FROM sucursales
            WHERE {column}=?
            """,
            (value,),
        ).fetchone()
        return dict(row) if row else None

    def save_branch_delivery_profile(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        opening_time: str,
        closing_time: str,
        operation_days: str,
        accepts_after_hours_orders: bool,
        after_hours_message: str,
        branch_id: str | None = None,
    ) -> str:
        _, branch_uuid = self._resolve_branch_row(branch_id)
        if branch_id is not None:
            self.db.execute(
                """
                UPDATE sucursales SET nombre=?, direccion=?, telefono=?,
                    hora_apertura=?, hora_cierre=?, dias_operacion=?,
                    acepta_pedidos_fuera_horario=?, mensaje_fuera_horario=?
                WHERE id=?
                """,
                (name, address, phone, opening_time, closing_time, operation_days,
                 1 if accepts_after_hours_orders else 0, after_hours_message, branch_uuid),
            )
            return str(branch_uuid)

        new_branch_uuid = new_uuid()
        fields = [
            "id",
            "nombre",
            "direccion",
            "telefono",
            "hora_apertura",
            "hora_cierre",
            "dias_operacion",
            "acepta_pedidos_fuera_horario",
            "mensaje_fuera_horario",
            "activa",
        ]
        values: list[object] = [
            new_branch_uuid,
            name,
            address,
            phone,
            opening_time,
            closing_time,
            operation_days,
            1 if accepts_after_hours_orders else 0,
            after_hours_message,
            1,
        ]
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO sucursales ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        return new_branch_uuid

    def _happy_hour_row_to_dict(self, row) -> dict:
        keys = [
            "id",
            "nombre",
            "hora_inicio",
            "hora_fin",
            "dias_semana",
            "tipo_descuento",
            "valor",
            "aplica_a",
            "aplica_valor",
            "mensaje_wa",
            "activo",
            "sucursal_id",
        ]
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        return {key: row[index] for index, key in enumerate(keys) if index < len(row)}

    def _hhr_select_parts(self) -> tuple[str, str, str]:
        """(id_expr, branch_expr, join_sql) para happy_hour_rules — born-clean:
        h.id es la identidad y h.sucursal_id es el UUID de la sucursal."""
        return (
            "h.id AS id",
            "h.sucursal_id AS sucursal_id",
            "LEFT JOIN sucursales AS s ON s.id = h.sucursal_id",
        )

    def list_happy_hour_rules(self) -> list[dict]:
        id_expr, branch_expr, join_sql = self._hhr_select_parts()
        sql = f"""
            SELECT {id_expr}, h.nombre, h.hora_inicio, h.hora_fin, h.dias_semana,
                   h.tipo_descuento, h.valor, h.aplica_a, h.aplica_valor,
                   h.mensaje_wa, h.activo, {branch_expr}
            FROM happy_hour_rules AS h
            {join_sql}
            ORDER BY h.nombre
        """
        logger.debug("list_happy_hour_rules SQL: %s", sql.strip())
        rows = self.db.execute(sql).fetchall()
        return [self._happy_hour_row_to_dict(row) for row in rows]

    def get_happy_hour_rule(self, rule_id: str) -> dict | None:
        column, value = self._resolve_db_identifier("happy_hour_rules", rule_id)
        id_expr, branch_expr, join_sql = self._hhr_select_parts()
        sql = f"""
            SELECT {id_expr}, h.nombre, h.hora_inicio, h.hora_fin, h.dias_semana,
                   h.tipo_descuento, h.valor, h.aplica_a, h.aplica_valor,
                   h.mensaje_wa, h.activo, {branch_expr}
            FROM happy_hour_rules AS h
            {join_sql}
            WHERE h.{column}=?
        """
        logger.debug("get_happy_hour_rule SQL: %s | params: %s", sql.strip(), (value,))
        row = self.db.execute(sql, (value,)).fetchone()
        return self._happy_hour_row_to_dict(row) if row else None

    def save_happy_hour_rule(self, rule: dict) -> str:
        _, branch_uuid = self._resolve_branch_row(str(rule.get("sucursal_id") or "").strip() or None)
        rule_uuid = str(rule.get("id") or "").strip() or new_uuid()
        columns = [
            "id", "nombre", "hora_inicio", "hora_fin", "dias_semana",
            "tipo_descuento", "valor", "aplica_a", "aplica_valor",
            "mensaje_wa", "activo", "sucursal_id",
        ]
        values: list[object] = [
            rule_uuid,
            rule["nombre"],
            rule["hora_inicio"],
            rule["hora_fin"],
            rule["dias_semana"],
            rule["tipo_descuento"],
            float(rule["valor"]),
            rule["aplica_a"],
            rule.get("aplica_valor") or "",
            rule.get("mensaje_wa") or "",
            1 if rule.get("activo") else 0,
            branch_uuid,
        ]

        existing_column, existing_value = self._resolve_db_identifier("happy_hour_rules", rule_uuid)
        existing = None
        if rule.get("id"):
            existing = self.db.execute(f"SELECT 1 FROM happy_hour_rules WHERE {existing_column}=?", (existing_value,)).fetchone()
        if existing:
            assignments = ",".join(f"{column}=?" for column in columns)
            update_params = list(values)
            update_params.append(existing_value)
            self.db.execute(f"UPDATE happy_hour_rules SET {assignments} WHERE {existing_column}=?", tuple(update_params))
        else:
            placeholders = ",".join("?" for _ in columns)
            self.db.execute(
                f"INSERT INTO happy_hour_rules ({','.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
        return rule_uuid

    def set_happy_hour_rule_active(self, rule_id: str, active: bool) -> None:
        column, value = self._resolve_db_identifier("happy_hour_rules", rule_id)
        self.db.execute(
            f"UPDATE happy_hour_rules SET activo=? WHERE {column}=?",
            (1 if active else 0, value),
        )

    # --- CONFIGURATION MODULE READ/WRITE ADAPTERS ---
    def monthly_close_exists(self, period: str) -> bool:
        row = self.db.execute("SELECT 1 FROM cierre_mensual WHERE periodo=?", (period,)).fetchone()
        return bool(row)

    def calculate_monthly_close_totals(self, start_date: str, end_date: str) -> dict[str, float]:
        sales = self.db.execute(
            "SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha>=? AND fecha<? AND estado='completada'",
            (start_date, end_date),
        ).fetchone()
        purchases = self.db.execute(
            "SELECT COALESCE(SUM(total),0) FROM compras WHERE fecha>=? AND fecha<?",
            (start_date, end_date),
        ).fetchone()
        waste = self.db.execute(
            """
            SELECT COALESCE(SUM(m.cantidad * COALESCE(p.precio_compra, 0)), 0)
            FROM mermas m
            LEFT JOIN productos p ON p.id = m.producto_id
            WHERE m.created_at >= ? AND m.created_at < ?
            """,
            (start_date, end_date),
        ).fetchone()
        return {
            "sales": float(sales[0] if sales else 0),
            "purchases": float(purchases[0] if purchases else 0),
            "waste": float(waste[0] if waste else 0),
        }

    def save_monthly_close(self, *, period: str, closed_by: str, totals: dict[str, float], branch_id: str) -> None:
        _, branch_uuid = self._resolve_branch_row(branch_id)
        fields = ["id", "periodo", "cerrado_por", "total_ventas", "total_compras",
                  "total_merma", "sucursal_id"]
        values: list[object] = [new_uuid(), period, closed_by, totals["sales"],
                                totals["purchases"], totals["waste"], branch_uuid]
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO cierre_mensual ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )

    def get_monthly_closures(self, limit: int = 24) -> list[tuple]:
        return self.db.execute(
            """
            SELECT periodo, cerrado_por, fecha_cierre, total_ventas, total_compras, total_merma
            FROM cierre_mensual
            ORDER BY periodo DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def active_branches_for_selector(self) -> list[tuple[str, str]]:
        rows = self.db.execute(
            f"SELECT id, nombre FROM sucursales "
            f"WHERE activa=1 AND {self._VALID_BRANCH_ID_SQL} ORDER BY nombre"
        ).fetchall()
        return [(str(row[0]), row[1]) for row in rows]

    def branches_for_company_settings(self) -> list[tuple[str, str]]:
        return self.active_branches_for_selector()

    def list_branch_delivery_rows(self) -> list[tuple]:
        rows = self.db.execute(
            f"""
            SELECT id, nombre, COALESCE(direccion,''),
                   COALESCE(hora_apertura,''), COALESCE(hora_cierre,''),
                   COALESCE(dias_operacion,''), activa
            FROM sucursales WHERE {self._VALID_BRANCH_ID_SQL} ORDER BY nombre
            """
        ).fetchall()
        return [tuple(row) for row in rows]

    def list_users_v13(self) -> list[tuple]:
        # Born-clean: usuarios.id y sucursales.id son la identidad UUIDv7 única.
        return self.db.execute(
            """
            SELECT u.id AS id, u.usuario, u.nombre,
                   COALESCE(r.nombre,'cajero') AS rol,
                   COALESCE(s.nombre,'') AS sucursal,
                   u.activo, u.id AS usuario_uuid, s.id AS sucursal_uuid_val
            FROM usuarios u
            LEFT JOIN roles r ON r.nombre = u.rol
            LEFT JOIN sucursales s ON s.id = u.sucursal_id
            ORDER BY u.nombre LIMIT 200
            """
        ).fetchall()

    def role_names(self) -> list[str]:
        rows = self.db.execute("SELECT nombre FROM roles ORDER BY nombre").fetchall()
        return [row[0] for row in rows]

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        rows = self.db.execute(
            "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        return [(row[0], str(row[1]).strip()) for row in rows]

    def get_user_form_data(self, user_id: str) -> tuple | None:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        branch_column = "sucursal_id"  # born-clean: UUID de la sucursal
        return self.db.execute(
            f"SELECT usuario,nombre,email,rol,{branch_column},activo,empleado_id FROM usuarios WHERE {column}=?",
            (value,),
        ).fetchone()

    def username_for_uuid(self, user_id: str) -> str | None:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        row = self.db.execute(f"SELECT usuario FROM usuarios WHERE {column}=?", (value,)).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _looks_like_uuid(value) -> bool:
        try:
            UUID(str(value))
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    def _resolve_label(self, table: str, label_column: str, entity_id) -> str | None:
        """Resolve a human label for an entity from either its uuid or row id.

        Used to enrich domain events with names (e.g. ``usuario``/``nombre``)
        instead of exposing integer identifiers. This is a read-only label
        lookup, not an identity contract, so it accepts the internal id the
        caller already holds during the transitional dual-column period.
        """
        if entity_id is None or entity_id == "":
            return None
        row = self.db.execute(
            f"SELECT {label_column} FROM {table} WHERE id=?", (entity_id,)
        ).fetchone()
        return str(row[0]) if row else None

    def username_for_id(self, user_id) -> str | None:
        """Resolve a username from a uuid or integer row id (event label)."""
        return self._resolve_label("usuarios", "usuario", user_id)

    def save_user_v13(
        self,
        *,
        user_id: str | None,
        username: str,
        name: str,
        email: str,
        role: str,
        branch_id: str,
        active: bool,
        employee_id: int | None,
        password_hash: str | None,
    ) -> str:
        # Born-clean: usuarios.id ES el UUID; sucursal_id es el UUID de la sucursal.
        _, branch_uuid = self._resolve_branch_row(branch_id)
        persisted_user_id = user_id or new_uuid()
        fields = ["usuario", "nombre", "email", "rol", "activo", "empleado_id", "sucursal_id"]
        values: list[object] = [username, name, email, role, 1 if active else 0,
                                employee_id, branch_uuid or ""]
        if password_hash is not None:
            fields.append("password_hash")
            values.append(password_hash)

        existing = None
        if user_id:
            _, value = self._resolve_db_identifier("usuarios", user_id)
            existing = self.db.execute("SELECT id FROM usuarios WHERE id=?", (value,)).fetchone()
        if existing:
            assignments = ",".join(f"{field}=?" for field in fields)
            self.db.execute(
                f"UPDATE usuarios SET {assignments} WHERE id=?",
                tuple(values) + (persisted_user_id,),
            )
        else:
            fields.insert(0, "id")
            values.insert(0, persisted_user_id)
            placeholders = ",".join("?" for _ in fields)
            self.db.execute(
                f"INSERT INTO usuarios({','.join(fields)}) VALUES({placeholders})",
                tuple(values),
            )
        if employee_id:
            self.db.execute("UPDATE personal SET usuario_id=? WHERE id=?",
                            (persisted_user_id, employee_id))
        return persisted_user_id

    def set_user_active(self, user_id: str, active: bool) -> None:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        self.db.execute(f"UPDATE usuarios SET activo=? WHERE {column}=?", (1 if active else 0, value))

    def list_roles_v13(self) -> list[tuple]:
        identity = self._select_identity_sql("roles", table_alias="r")
        return self.db.execute(
            f"""
            SELECT {identity}, r.nombre, r.descripcion, COUNT(u.id) as num_usuarios
            FROM roles r
            LEFT JOIN usuarios u ON u.rol=r.nombre AND u.activo=1
            GROUP BY r.id ORDER BY r.nombre
            """
        ).fetchall()

    def _normalize_role(self, role_name: str | None) -> str:
        return str(role_name or "").strip().lower()

    def permission_codes_for_role_name(self, role_name: str) -> set[str]:
        normalized_role = self._normalize_role(role_name)
        if normalized_role in {"admin", "superadmin", "administrador"}:
            return {"*"}
        row = self.db.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?", (normalized_role,)).fetchone()
        if not row:
            logger.warning("Role not found while resolving permissions: %s", role_name)
            return set()
        # Born-clean: roles.id ES el UUID y rol_permisos referencia rol_id (UUID).
        return self._role_permissions_by_row_id(str(row[0]))

    def _role_permissions_by_row_id(self, role_row_id: str | None) -> set[str]:
        """Resuelve permisos por rol_id (UUID de roles.id)."""
        if not role_row_id:
            logger.warning("rol_permisos: rol sin identidad — returning empty")
            return set()
        rows = self.db.execute(
            "SELECT modulo, accion FROM rol_permisos WHERE rol_id=? AND permitido=1",
            (role_row_id,),
        ).fetchall()
        return {normalize_permission(f"{row[0]}.{row[1]}") for row in rows}

    def permission_codes_for_role_id(self, role_id: str) -> set[str]:
        role_uuid, _ = self._resolve_role_row(role_id)
        return self._role_permissions_by_row_id(role_uuid)

    def permission_codes_for_user(self, user_id: str, branch_id: str | None = None) -> set[str]:
        # usuarios.id es la identidad canónica del usuario: UUIDv7 TEXT.
        # Nunca se convierte a entero (REGLA CERO de identidad).
        user_id_str = str(user_id or "").strip()
        if not user_id_str:
            logger.warning("permission_codes_for_user: invalid user_id %r — returning empty set", user_id)
            return set()
        row = self.db.execute("SELECT id, rol FROM usuarios WHERE id=?", (user_id_str,)).fetchone()
        if not row:
            logger.warning("User not found while resolving permissions: %s", user_id)
            return set()
        normalized_role = self._normalize_role(row[1])
        if normalized_role in {"admin", "superadmin", "administrador"}:
            return {"*"}
        user_uuid = str(row[0]).strip()
        permissions = set(self.permission_codes_for_role_name(normalized_role))
        permissions = self._apply_user_permission_overrides(user_uuid, permissions)
        permissions = self._apply_branch_permission_restrictions(user_uuid, branch_id, permissions)
        return {normalize_permission(permission) for permission in permissions}

    def _apply_user_permission_overrides(self, user_id: str, permissions: set[str]) -> set[str]:
        if not self._table_exists("usuario_permisos"):
            return permissions
        rows = self.db.execute(
            """
            SELECT modulo, accion, permitido
            FROM usuario_permisos
            WHERE usuario_id=? AND COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            """,
            (user_id,),
        ).fetchall()
        resolved = set(permissions)
        for row in rows:
            code = normalize_permission(f"{row[0]}.{row[1]}")
            if bool(row[2]):
                resolved.add(code)
            else:
                resolved.discard(code)
        return resolved

    def _apply_branch_permission_restrictions(
        self, user_id: str, branch_id: str | None, permissions: set[str]
    ) -> set[str]:
        if branch_id is None or not self._table_exists("usuario_sucursal_permisos"):
            return permissions
        branch_row_id, _ = self._resolve_branch_row(branch_id)
        rows = self.db.execute(
            """
            SELECT modulo, accion, permitido
            FROM usuario_sucursal_permisos
            WHERE usuario_id=? AND sucursal_id=?
              AND COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            """,
            (user_id, branch_row_id),
        ).fetchall()
        if not rows:
            return permissions
        resolved = set(permissions)
        for row in rows:
            code = normalize_permission(f"{row[0]}.{row[1]}")
            if bool(row[2]):
                resolved.add(code)
            else:
                resolved.discard(code)
        return resolved

    def role_name_for_id(self, role_id) -> str | None:
        """Resolve a role name from a uuid or integer row id (event label)."""
        return self._resolve_label("roles", "nombre", role_id)

    def role_permissions(self, role_id: str) -> dict[tuple[str, str], bool]:
        role_uuid, _ = self._resolve_role_row(role_id)
        rows = self.db.execute(
            "SELECT modulo, accion, permitido FROM rol_permisos WHERE rol_id=?",
            (role_uuid,),
        ).fetchall()
        return {(row[0], row[1]): bool(row[2]) for row in rows}

    def save_role_permissions(self, role_id: str, permissions: dict[tuple[str, str], bool]) -> None:
        role_uuid, _ = self._resolve_role_row(role_id)
        self.db.execute("DELETE FROM rol_permisos WHERE rol_id=?", (role_uuid,))
        insert_sql = "INSERT INTO rol_permisos(id,rol_id,modulo,accion,permitido) VALUES(?,?,?,?,?)"
        for (module, action), allowed in permissions.items():
            self.db.execute(insert_sql, (new_uuid(), role_uuid, module, action, 1 if allowed else 0))

    def audit_log_rows(self, limit: int = 200) -> list[tuple]:
        return self.db.execute(
            "SELECT fecha, usuario, modulo, accion, COALESCE(detalles,'') FROM audit_logs ORDER BY fecha DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def save_role(self, *, role_id: str | None, name: str, description: str) -> str:
        persisted_role_id = role_id or new_uuid()
        existing = None
        if role_id:
            _, value = self._resolve_db_identifier("roles", role_id)
            existing = self.db.execute("SELECT id FROM roles WHERE id=?", (value,)).fetchone()
        if existing:
            self.db.execute("UPDATE roles SET nombre=?, descripcion=? WHERE id=?",
                            (name, description, persisted_role_id))
        else:
            self.db.execute("INSERT INTO roles(id, nombre, descripcion) VALUES(?,?,?)",
                            (persisted_role_id, name, description))
        return persisted_role_id
