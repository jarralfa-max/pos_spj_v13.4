
# repositories/config_repository.py
import logging

logger = logging.getLogger(__name__)

class ConfigRepository:
    """Acceso a datos para Sucursales y Configuraciones del Sistema."""
    def __init__(self, db_conn):
        self.db = db_conn

    # --- SUCURSALES ---
    def get_all_branches(self) -> list:
        cursor = self.db.cursor()
        rows = cursor.execute("SELECT * FROM sucursales WHERE activa = 1").fetchall()
        return [dict(row) for row in rows]

    def create_branch(self, nombre: str, direccion: str, telefono: str):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO sucursales (nombre, direccion, telefono, activa)
            VALUES (?, ?, ?, 1)
        """, (nombre, direccion, telefono))
        return cursor.lastrowid

    def update_branch(self, branch_id: int, nombre: str, direccion: str, telefono: str):
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE sucursales SET nombre = ?, direccion = ?, telefono = ? WHERE id = ?
        """, (nombre, direccion, telefono, branch_id))

    def disable_branch(self, branch_id: int):
        """Soft Delete para sucursales."""
        cursor = self.db.cursor()
        cursor.execute("UPDATE sucursales SET activa = 0 WHERE id = ?", (branch_id,))

    # --- AJUSTES GLOBALES (Key-Value) ---
    def get_setting(self, key: str, default_value: str = "") -> str:
        cursor = self.db.cursor()
        row = cursor.execute("SELECT valor FROM configuraciones WHERE clave = ?", (key,)).fetchone()
        return row['valor'] if row else default_value

    def save_setting(self, key: str, value: str):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO configuraciones (clave, valor) VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
        """, (key, str(value)))
        self._commit()
        
    def get_all_settings(self) -> dict:
        """
        Obtiene todas las configuraciones de la base de datos 
        y las devuelve como un diccionario para la RAM.
        """
        try:
            cursor = self.db.cursor()
            rows = cursor.execute("SELECT clave, valor FROM configuraciones").fetchall()
            return {row['clave']: row['valor'] for row in rows}
        except Exception as e:
            # Si la tabla no existe aún (por ejemplo en el primer arranque),
            # no crasheamos, simplemente devolvemos un diccionario vacío.
            logger.warning(f"No se pudieron cargar las configuraciones: {e}")
            return {}

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

    def get_branch(self, branch_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM sucursales WHERE id=?", (branch_id,)).fetchone()
        return dict(row) if row else None

    def save_branch(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        active: bool,
        branch_id: int | None = None,
    ) -> int:
        if branch_id is not None:
            self.db.execute(
                "UPDATE sucursales SET nombre=?, direccion=?, telefono=?, activa=? WHERE id=?",
                (name, address, phone, 1 if active else 0, branch_id),
            )
            self._commit()
            return branch_id
        cursor = self.db.execute(
            "INSERT INTO sucursales (nombre, direccion, telefono, activa) VALUES (?, ?, ?, ?)",
            (name, address, phone, 1 if active else 0),
        )
        self._commit()
        return int(cursor.lastrowid)


    def get_branch_delivery_profile(self, branch_id: int) -> dict | None:
        row = self.db.execute(
            """
            SELECT nombre, direccion, telefono, hora_apertura, hora_cierre,
                   dias_operacion, acepta_pedidos_fuera_horario, mensaje_fuera_horario
            FROM sucursales
            WHERE id=?
            """,
            (branch_id,),
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
        branch_id: int | None = None,
    ) -> int:
        if branch_id is not None:
            self.db.execute(
                """
                UPDATE sucursales SET nombre=?, direccion=?, telefono=?,
                    hora_apertura=?, hora_cierre=?, dias_operacion=?,
                    acepta_pedidos_fuera_horario=?, mensaje_fuera_horario=?
                WHERE id=?
                """,
                (
                    name,
                    address,
                    phone,
                    opening_time,
                    closing_time,
                    operation_days,
                    1 if accepts_after_hours_orders else 0,
                    after_hours_message,
                    branch_id,
                ),
            )
            self._commit()
            return branch_id
        cursor = self.db.execute(
            """
            INSERT INTO sucursales
                (nombre, direccion, telefono, hora_apertura, hora_cierre,
                 dias_operacion, acepta_pedidos_fuera_horario, mensaje_fuera_horario, activa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                name,
                address,
                phone,
                opening_time,
                closing_time,
                operation_days,
                1 if accepts_after_hours_orders else 0,
                after_hours_message,
            ),
        )
        self._commit()
        return int(cursor.lastrowid)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            pass

    # --- CONFIGURATION MODULE READ/WRITE ADAPTERS ---






    def monthly_close_exists(self, period: str) -> bool:
        row = self.db.execute("SELECT id FROM cierre_mensual WHERE periodo=?", (period,)).fetchone()
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

    def save_monthly_close(self, *, period: str, closed_by: str, totals: dict[str, float], branch_id: int) -> None:
        self.db.execute(
            """
            INSERT INTO cierre_mensual
                (periodo, cerrado_por, total_ventas, total_compras, total_merma, sucursal_id)
            VALUES (?,?,?,?,?,?)
            """,
            (period, closed_by, totals["sales"], totals["purchases"], totals["waste"], branch_id),
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










    def active_branches_for_selector(self) -> list[tuple[int, str]]:
        rows = self.db.execute("SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY id").fetchall()
        return [(row[0], row[1]) for row in rows]

    def branches_for_company_settings(self) -> list[tuple[int, str]]:
        rows = self.db.execute("SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre").fetchall()
        return [(row[0], row[1]) for row in rows]

    def list_branch_delivery_rows(self) -> list[tuple]:
        return self.db.execute(
            """
            SELECT id,nombre,COALESCE(direccion,''),
                   COALESCE(hora_apertura,'08:00'),COALESCE(hora_cierre,'21:00'),
                   COALESCE(dias_operacion,'1,2,3,4,5,6'),activa
            FROM sucursales ORDER BY nombre
            """
        ).fetchall()

    def list_users_v13(self) -> list[tuple]:
        return self.db.execute(
            """
            SELECT u.id,u.usuario,u.nombre,
                   COALESCE(r.nombre,'cajero') as rol,
                   COALESCE(s.nombre,'Principal') as sucursal,
                   u.activo
            FROM usuarios u
            LEFT JOIN roles r ON r.nombre=u.rol
            LEFT JOIN sucursales s ON s.id=u.sucursal_id
            ORDER BY u.nombre LIMIT 200
            """
        ).fetchall()

    def role_names(self) -> list[str]:
        rows = self.db.execute("SELECT nombre FROM roles ORDER BY id").fetchall()
        return [row[0] for row in rows]

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        rows = self.db.execute(
            "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        return [(row[0], str(row[1]).strip()) for row in rows]

    def get_user_form_data(self, user_id: int) -> tuple | None:
        return self.db.execute(
            "SELECT usuario,nombre,email,rol,sucursal_id,activo,empleado_id FROM usuarios WHERE id=?",
            (user_id,),
        ).fetchone()

    def save_user_v13(self, *, user_id: int | None, username: str, name: str, email: str, role: str,
                      branch_id: int, active: bool, employee_id: int | None, password_hash: str | None) -> None:
        if user_id:
            if password_hash:
                self.db.execute(
                    "UPDATE usuarios SET usuario=?,nombre=?,email=?,rol=?,sucursal_id=?,activo=?,empleado_id=?,password_hash=? WHERE id=?",
                    (username, name, email, role, branch_id, 1 if active else 0, employee_id, password_hash, user_id),
                )
            else:
                self.db.execute(
                    "UPDATE usuarios SET usuario=?,nombre=?,email=?,rol=?,sucursal_id=?,activo=?,empleado_id=? WHERE id=?",
                    (username, name, email, role, branch_id, 1 if active else 0, employee_id, user_id),
                )
        else:
            cursor = self.db.execute(
                "INSERT INTO usuarios(usuario,nombre,email,password_hash,rol,sucursal_id,activo,empleado_id) VALUES(?,?,?,?,?,?,?,?)",
                (username, name, email, password_hash, role, branch_id, 1 if active else 0, employee_id),
            )
            if employee_id:
                self.db.execute("UPDATE personal SET usuario_id=? WHERE id=?", (cursor.lastrowid, employee_id))
        self._commit()

    def set_user_active(self, user_id: int, active: bool) -> None:
        self.db.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if active else 0, user_id))
        self._commit()

    def list_roles_v13(self) -> list[tuple]:
        return self.db.execute(
            """
            SELECT r.id, r.nombre, r.descripcion, COUNT(u.id) as num_usuarios
            FROM roles r
            LEFT JOIN usuarios u ON u.rol=r.nombre AND u.activo=1
            GROUP BY r.id ORDER BY r.id
            """
        ).fetchall()

    def role_permissions(self, role_id: int) -> dict[tuple[str, str], bool]:
        rows = self.db.execute(
            "SELECT modulo, accion, permitido FROM rol_permisos WHERE rol_id=?",
            (role_id,),
        ).fetchall()
        return {(row[0], row[1]): bool(row[2]) for row in rows}

    def save_role_permissions(self, role_id: int, permissions: dict[tuple[str, str], bool]) -> None:
        self.db.execute("DELETE FROM rol_permisos WHERE rol_id=?", (role_id,))
        for (module, action), allowed in permissions.items():
            self.db.execute(
                "INSERT INTO rol_permisos(rol_id,modulo,accion,permitido) VALUES(?,?,?,?)",
                (role_id, module, action, 1 if allowed else 0),
            )
        self._commit()

    def audit_log_rows(self, limit: int = 200) -> list[tuple]:
        return self.db.execute(
            "SELECT fecha, usuario, modulo, accion, COALESCE(detalles,'') FROM audit_logs ORDER BY fecha DESC LIMIT ?",
            (limit,),
        ).fetchall()



    def save_role(self, *, role_id: int | None, name: str, description: str) -> int:
        if role_id is not None:
            self.db.execute(
                "UPDATE roles SET nombre=?, descripcion=? WHERE id=?",
                (name, description, role_id),
            )
            self._commit()
            return role_id
        cursor = self.db.execute(
            "INSERT INTO roles(nombre, descripcion) VALUES(?, ?)",
            (name, description),
        )
        self._commit()
        return int(cursor.lastrowid)
