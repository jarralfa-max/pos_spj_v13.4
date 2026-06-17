import logging
from uuid import UUID

from backend.shared.ids import new_uuid
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS, normalize_permission

logger = logging.getLogger(__name__)


class ConfigRepository:
    """Acceso a datos para Configuración con contratos canónicos UUID."""

    def __init__(self, db_conn):
        self.db = db_conn

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            pass

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

    def _uuid_column(self, table_name: str) -> str | None:
        return "uuid" if self._column_exists(table_name, "uuid") else None

    def _require_uuid_column(self, table_name: str) -> str:
        uuid_column = self._uuid_column(table_name)
        if not uuid_column:
            logger.warning(
                "%s: uuid column not found — falling back to integer id (run migrations 101-103)",
                table_name,
            )
            return "id"
        return uuid_column

    def _require_uuidv7(self, value: str, field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        try:
            parsed = UUID(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7") from exc
        if parsed.version != 7 or normalized != str(parsed):
            raise ValueError(f"{field_name} must be a canonical lowercase UUIDv7")
        return normalized

    def _select_identity_sql(self, table_name: str, *, alias: str = "id") -> str:
        uuid_column = self._require_uuid_column(table_name)
        return f"{uuid_column} AS {alias}"

    def _row_id_from_uuid(self, table_name: str, entity_id: str | None) -> int | None:
        if not entity_id:
            return None
        uuid_column = self._require_uuid_column(table_name)
        row = self.db.execute(f"SELECT id FROM {table_name} WHERE {uuid_column}=?", (entity_id,)).fetchone()
        return int(row[0]) if row else None

    def _uuid_from_row_id(self, table_name: str, row_id: int | None) -> str | None:
        if row_id is None:
            return None
        uuid_column = self._require_uuid_column(table_name)
        row = self.db.execute(f"SELECT {uuid_column} FROM {table_name} WHERE id=?", (row_id,)).fetchone()
        return str(row[0]) if row and row[0] else None

    def _resolve_db_identifier(self, table_name: str, entity_id: str) -> tuple[str, object]:
        uuid_column = self._require_uuid_column(table_name)
        return uuid_column, self._require_uuidv7(entity_id, f"{table_name}.id")

    def _resolve_branch_row(self, branch_id: str | None) -> tuple[int | None, str | None]:
        if not branch_id:
            return None, None
        branch_uuid = self._require_uuidv7(branch_id, "branch_id")
        row_id = self._row_id_from_uuid("sucursales", branch_uuid)
        if row_id is None:
            raise ValueError("branch_id must reference an existing branch UUID")
        return row_id, branch_uuid

    def _resolve_role_row(self, role_id: str) -> tuple[int | None, str | None]:
        role_uuid = self._require_uuidv7(role_id, "role_id")
        row_id = self._row_id_from_uuid("roles", role_uuid)
        if row_id is None:
            raise ValueError("role_id must reference an existing role UUID")
        return row_id, role_uuid

    def _resolve_user_row(self, user_id: str) -> tuple[int | None, str | None]:
        user_uuid = self._require_uuidv7(user_id, "user_id")
        row_id = self._row_id_from_uuid("usuarios", user_uuid)
        if row_id is None:
            raise ValueError("user_id must reference an existing user UUID")
        return row_id, user_uuid

    # --- SUCURSALES ---
    def get_all_branches(self) -> list:
        identity = self._select_identity_sql("sucursales")
        rows = self.db.execute(
            f"SELECT {identity}, nombre, direccion, telefono, activa FROM sucursales WHERE activa = 1"
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
        self._commit()

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
        self._commit()

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
        self._commit()

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
        branch_row_id, branch_uuid = self._resolve_branch_row(branch_id)
        if branch_id is not None:
            assignments = ["nombre=?", "direccion=?", "telefono=?", "activa=?"]
            params: list[object] = [name, address, phone, 1 if active else 0]
            assignments.insert(0, "uuid=?")
            params.insert(0, branch_uuid)
            params.append(branch_uuid)
            self.db.execute(f"UPDATE sucursales SET {', '.join(assignments)} WHERE uuid=?", tuple(params))
            self._commit()
            return str(branch_uuid)

        new_branch_uuid = new_uuid()
        fields = ["nombre", "direccion", "telefono", "activa"]
        values: list[object] = [name, address, phone, 1 if active else 0]
        self._require_uuid_column("sucursales")
        fields.insert(0, "uuid")
        values.insert(0, new_branch_uuid)
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO sucursales ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        self._commit()
        return new_branch_uuid

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
        branch_row_id, branch_uuid = self._resolve_branch_row(branch_id)
        if branch_id is not None:
            params: list[object] = [
                name,
                address,
                phone,
                opening_time,
                closing_time,
                operation_days,
                1 if accepts_after_hours_orders else 0,
                after_hours_message,
            ]
            sql = """
                UPDATE sucursales SET nombre=?, direccion=?, telefono=?,
                    hora_apertura=?, hora_cierre=?, dias_operacion=?,
                    acepta_pedidos_fuera_horario=?, mensaje_fuera_horario=?
            """
            sql += ", uuid=? WHERE uuid=?"
            params.extend([branch_uuid, branch_uuid])
            self.db.execute(sql, tuple(params))
            self._commit()
            return str(branch_uuid)

        new_branch_uuid = new_uuid()
        fields = [
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
        self._require_uuid_column("sucursales")
        fields.insert(0, "uuid")
        values.insert(0, new_branch_uuid)
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO sucursales ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        self._commit()
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
        """Return (id_expr, branch_expr, join_sql) for happy_hour_rules queries.

        All column references use table aliases to avoid ambiguous column name errors
        when sucursales also has a uuid column.
        """
        has_hhr_uuid = self._column_exists("happy_hour_rules", "uuid")
        has_sucursal_uuid = self._column_exists("happy_hour_rules", "sucursal_uuid")
        has_s_uuid = self._column_exists("sucursales", "uuid")

        id_expr = "h.uuid AS id" if has_hhr_uuid else "h.id AS id"

        if has_sucursal_uuid and has_s_uuid:
            branch_expr = "COALESCE(h.sucursal_uuid, s.uuid) AS sucursal_id"
            join_sql = "LEFT JOIN sucursales AS s ON s.uuid = h.sucursal_uuid"
        elif has_sucursal_uuid:
            branch_expr = "h.sucursal_uuid AS sucursal_id"
            join_sql = ""
        else:
            logger.warning(
                "happy_hour_rules.sucursal_uuid not found — run migration 103; "
                "sucursal_id will be integer"
            )
            branch_expr = "CAST(h.sucursal_id AS TEXT) AS sucursal_id"
            join_sql = "LEFT JOIN sucursales AS s ON s.id = h.sucursal_id"

        return id_expr, branch_expr, join_sql

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
        branch_row_id, branch_uuid = self._resolve_branch_row(str(rule.get("sucursal_id") or "").strip() or None)
        rule_uuid = str(rule.get("id") or "").strip() or new_uuid()
        values: list[object] = [
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
        ]
        has_sucursal_uuid_col = self._column_exists("happy_hour_rules", "sucursal_uuid")
        if has_sucursal_uuid_col:
            values.append(branch_uuid or "")
        columns = [
            "nombre", "hora_inicio", "hora_fin", "dias_semana",
            "tipo_descuento", "valor", "aplica_a", "aplica_valor",
            "mensaje_wa", "activo",
        ]
        if has_sucursal_uuid_col:
            columns.append("sucursal_uuid")
        elif self._column_exists("happy_hour_rules", "sucursal_id") and branch_row_id is not None:
            columns.append("sucursal_id")
            values.append(branch_row_id)
        has_hhr_uuid = self._column_exists("happy_hour_rules", "uuid")
        if has_hhr_uuid:
            columns.insert(0, "uuid")
            values.insert(0, rule_uuid)

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
        self._commit()
        return rule_uuid

    def set_happy_hour_rule_active(self, rule_id: str, active: bool) -> None:
        column, value = self._resolve_db_identifier("happy_hour_rules", rule_id)
        self.db.execute(
            f"UPDATE happy_hour_rules SET activo=? WHERE {column}=?",
            (1 if active else 0, value),
        )
        self._commit()

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
        branch_row_id, branch_uuid = self._resolve_branch_row(branch_id)
        fields = ["periodo", "cerrado_por", "total_ventas", "total_compras", "total_merma"]
        values: list[object] = [period, closed_by, totals["sales"], totals["purchases"], totals["waste"]]
        if self._column_exists("cierre_mensual", "uuid"):
            fields.insert(0, "uuid")
            values.insert(0, new_uuid())
        if self._column_exists("cierre_mensual", "sucursal_uuid"):
            fields.append("sucursal_uuid")
            values.append(branch_uuid or "")
        elif self._column_exists("cierre_mensual", "sucursal_id") and branch_row_id is not None:
            fields.append("sucursal_id")
            values.append(branch_row_id)
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(
            f"INSERT INTO cierre_mensual ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        self._commit()

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
            f"SELECT {self._select_identity_sql('sucursales')}, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
        ).fetchall()
        return [(str(row[0]), row[1]) for row in rows]

    def branches_for_company_settings(self) -> list[tuple[str, str]]:
        return self.active_branches_for_selector()

    def list_branch_delivery_rows(self) -> list[tuple]:
        rows = self.db.execute(
            f"""
            SELECT {self._select_identity_sql('sucursales')}, nombre, COALESCE(direccion,''),
                   COALESCE(hora_apertura,''), COALESCE(hora_cierre,''),
                   COALESCE(dias_operacion,''), activa
            FROM sucursales ORDER BY nombre
            """
        ).fetchall()
        return [tuple(row) for row in rows]

    def list_users_v13(self) -> list[tuple]:
        has_user_uuid = self._column_exists("usuarios", "uuid")
        has_sucursal_uuid = (
            self._column_exists("usuarios", "sucursal_uuid")
            and self._column_exists("sucursales", "uuid")
        )
        user_id_expr = "u.uuid AS id" if has_user_uuid else "u.id AS id"
        user_uuid_expr = "u.uuid AS usuario_uuid" if has_user_uuid else "NULL AS usuario_uuid"
        branch_uuid_expr = (
            "s.uuid AS sucursal_uuid_val"
            if self._column_exists("sucursales", "uuid")
            else "NULL AS sucursal_uuid_val"
        )
        if not has_sucursal_uuid:
            logger.warning("usuarios.sucursal_uuid not found — run migration 102; using integer join")
        branch_join = (
            "LEFT JOIN sucursales s ON s.uuid = u.sucursal_uuid"
            if has_sucursal_uuid
            else "LEFT JOIN sucursales s ON s.id = u.sucursal_id"
        )
        return self.db.execute(
            f"""
            SELECT {user_id_expr}, u.usuario, u.nombre,
                   COALESCE(r.nombre,'cajero') AS rol,
                   COALESCE(s.nombre,'Principal') AS sucursal,
                   u.activo, {user_uuid_expr}, {branch_uuid_expr}
            FROM usuarios u
            LEFT JOIN roles r ON r.nombre = u.rol
            {branch_join}
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
        branch_column = (
            "sucursal_uuid" if self._column_exists("usuarios", "sucursal_uuid") else "sucursal_id"
        )
        return self.db.execute(
            f"SELECT usuario,nombre,email,rol,{branch_column},activo,empleado_id FROM usuarios WHERE {column}=?",
            (value,),
        ).fetchone()

    def username_for_uuid(self, user_id: str) -> str | None:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        row = self.db.execute(f"SELECT usuario FROM usuarios WHERE {column}=?", (value,)).fetchone()
        return str(row[0]) if row else None

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
        branch_row_id, branch_uuid = self._resolve_branch_row(branch_id)
        has_user_uuid = self._column_exists("usuarios", "uuid")
        has_sucursal_uuid = self._column_exists("usuarios", "sucursal_uuid")
        persisted_user_id = user_id or new_uuid()
        role_fields = ["usuario", "nombre", "email", "rol", "activo", "empleado_id"]
        role_values: list[object] = [username, name, email, role, 1 if active else 0, employee_id]
        if has_user_uuid:
            role_fields.insert(0, "uuid")
            role_values.insert(0, persisted_user_id)
        else:
            logger.warning("usuarios: uuid column not found — saving without uuid (run migrations 101-103)")
        if password_hash is not None:
            role_fields.append("password_hash")
            role_values.append(password_hash)
        if has_sucursal_uuid:
            role_fields.append("sucursal_uuid")
            role_values.append(branch_uuid or "")
        else:
            logger.warning("usuarios.sucursal_uuid not found — run migration 102; field skipped")
            # Fall back to integer sucursal_id
            if self._column_exists("usuarios", "sucursal_id") and branch_row_id is not None:
                role_fields.append("sucursal_id")
                role_values.append(branch_row_id)

        existing = None
        if user_id:
            column, value = self._resolve_db_identifier("usuarios", user_id)
            existing = self.db.execute(f"SELECT id FROM usuarios WHERE {column}=?", (value,)).fetchone()
        if existing:
            assignments = ",".join(f"{field}=?" for field in role_fields)
            where_col = "uuid" if has_user_uuid else "id"
            update_id = persisted_user_id if has_user_uuid else existing[0]
            params = list(role_values) + [update_id]
            self.db.execute(f"UPDATE usuarios SET {assignments} WHERE {where_col}=?", tuple(params))
            user_row_id = int(existing[0])
        else:
            placeholders = ",".join("?" for _ in role_fields)
            cursor = self.db.execute(
                f"INSERT INTO usuarios({','.join(role_fields)}) VALUES({placeholders})",
                tuple(role_values),
            )
            user_row_id = (
                self._row_id_from_uuid("usuarios", persisted_user_id)
                if has_user_uuid
                else cursor.lastrowid
            )
        if employee_id and user_row_id is not None:
            self.db.execute("UPDATE personal SET usuario_id=? WHERE id=?", (user_row_id, employee_id))
        self._commit()
        if not has_user_uuid and user_row_id is not None:
            return str(user_row_id)
        return persisted_user_id

    def set_user_active(self, user_id: str, active: bool) -> None:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        self.db.execute(f"UPDATE usuarios SET activo=? WHERE {column}=?", (1 if active else 0, value))
        self._commit()

    def list_roles_v13(self) -> list[tuple]:
        identity = self._select_identity_sql("roles")
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
        # If uuid column exists, look up uuid; otherwise pass integer id as string for fallback
        role_uuid_or_id = self._uuid_from_row_id("roles", self._to_int(row[0])) or str(row[0])
        return self.permission_codes_for_role_id(role_uuid_or_id)

    def permission_codes_for_role_id(self, role_id: str) -> set[str]:
        role_row_id, role_uuid = self._resolve_role_row(role_id)
        if self._column_exists("rol_permisos", "rol_uuid") and role_uuid:
            rows = self.db.execute(
                "SELECT modulo, accion FROM rol_permisos WHERE rol_uuid=? AND permitido=1",
                (role_uuid,),
            ).fetchall()
        elif role_row_id is not None and self._column_exists("rol_permisos", "rol_id"):
            rows = self.db.execute(
                "SELECT modulo, accion FROM rol_permisos WHERE rol_id=? AND permitido=1",
                (role_row_id,),
            ).fetchall()
        else:
            logger.warning("rol_permisos: no usable identity column found — run migrations; returning empty")
            return set()
        return {normalize_permission(f"{row[0]}.{row[1]}") for row in rows}

    def permission_codes_for_user(self, user_id: str, branch_id: str | None = None) -> set[str]:
        column, value = self._resolve_db_identifier("usuarios", user_id)
        row = self.db.execute(f"SELECT id, rol FROM usuarios WHERE {column}=?", (value,)).fetchone()
        if not row:
            logger.warning("User not found while resolving permissions: %s", user_id)
            return set()
        normalized_role = self._normalize_role(row[1])
        if normalized_role in {"admin", "superadmin", "administrador"}:
            return {"*"}
        int_id = int(row[0])
        permissions = set(self.permission_codes_for_role_name(normalized_role))
        permissions = self._apply_user_permission_overrides(int_id, permissions)
        permissions = self._apply_branch_permission_restrictions(int_id, branch_id, permissions)
        return {normalize_permission(permission) for permission in permissions}

    def _apply_user_permission_overrides(self, user_row_id: int, permissions: set[str]) -> set[str]:
        if not self._table_exists("usuario_permisos"):
            return permissions
        rows = self.db.execute(
            """
            SELECT modulo, accion, permitido
            FROM usuario_permisos
            WHERE usuario_id=? AND COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            """,
            (user_row_id,),
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
        self, user_row_id: int, branch_id: str | None, permissions: set[str]
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
            (user_row_id, branch_row_id),
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

    def role_name_for_id(self, role_id: str) -> str | None:
        column, value = self._resolve_db_identifier("roles", role_id)
        row = self.db.execute(f"SELECT nombre FROM roles WHERE {column}=?", (value,)).fetchone()
        return str(row[0]) if row else None

    def role_permissions(self, role_id: str) -> dict[tuple[str, str], bool]:
        role_row_id, role_uuid = self._resolve_role_row(role_id)
        if self._column_exists("rol_permisos", "rol_uuid") and role_uuid:
            rows = self.db.execute(
                "SELECT modulo, accion, permitido FROM rol_permisos WHERE rol_uuid=?",
                (role_uuid,),
            ).fetchall()
        elif role_row_id is not None and self._column_exists("rol_permisos", "rol_id"):
            rows = self.db.execute(
                "SELECT modulo, accion, permitido FROM rol_permisos WHERE rol_id=?",
                (role_row_id,),
            ).fetchall()
        else:
            logger.warning("rol_permisos: no usable identity column found — run migrations; returning empty")
            return {}
        return {(row[0], row[1]): bool(row[2]) for row in rows}

    def save_role_permissions(self, role_id: str, permissions: dict[tuple[str, str], bool]) -> None:
        role_row_id, role_uuid = self._resolve_role_row(role_id)
        if self._column_exists("rol_permisos", "rol_uuid") and role_uuid:
            self.db.execute("DELETE FROM rol_permisos WHERE rol_uuid=?", (role_uuid,))
            insert_sql = "INSERT INTO rol_permisos(rol_uuid,modulo,accion,permitido) VALUES(?,?,?,?)"
            for (module, action), allowed in permissions.items():
                self.db.execute(insert_sql, (role_uuid, module, action, 1 if allowed else 0))
        elif role_row_id is not None and self._column_exists("rol_permisos", "rol_id"):
            self.db.execute("DELETE FROM rol_permisos WHERE rol_id=?", (role_row_id,))
            insert_sql = "INSERT INTO rol_permisos(rol_id,modulo,accion,permitido) VALUES(?,?,?,?)"
            for (module, action), allowed in permissions.items():
                self.db.execute(insert_sql, (role_row_id, module, action, 1 if allowed else 0))
        else:
            logger.warning("rol_permisos: no usable identity column found — run migrations; permissions not saved")
            return
        self._commit()

    def audit_log_rows(self, limit: int = 200) -> list[tuple]:
        return self.db.execute(
            "SELECT fecha, usuario, modulo, accion, COALESCE(detalles,'') FROM audit_logs ORDER BY fecha DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def save_role(self, *, role_id: str | None, name: str, description: str) -> str:
        persisted_role_id = role_id or new_uuid()
        role_fields = ["nombre", "descripcion"]
        role_values: list[object] = [name, description]
        self._require_uuid_column("roles")
        role_fields.insert(0, "uuid")
        role_values.insert(0, persisted_role_id)
        existing = None
        if role_id:
            column, value = self._resolve_db_identifier("roles", role_id)
            existing = self.db.execute(f"SELECT id FROM roles WHERE {column}=?", (value,)).fetchone()
        if existing:
            assignments = ",".join(f"{field}=?" for field in role_fields)
            params = list(role_values) + [persisted_role_id]
            self.db.execute(f"UPDATE roles SET {assignments} WHERE uuid=?", tuple(params))
        else:
            placeholders = ",".join("?" for _ in role_fields)
            self.db.execute(
                f"INSERT INTO roles({','.join(role_fields)}) VALUES({placeholders})",
                tuple(role_values),
            )
        self._commit()
        return persisted_role_id
