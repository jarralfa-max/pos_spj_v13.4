"""SQLite repository adapters for RRHH legacy tables.

Phase 1 extraction rule: these adapters do not create or migrate tables. They
only centralize the same SQL shapes currently embedded in PyQt screens and
services so callers can be moved gradually without changing behavior.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.rrhh.domain import (
    AttendanceRecord,
    Employee,
    LeaveRequest,
    PayrollPayment,
    ShiftAssignment,
    ShiftRole,
)


def _get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        pass
    try:
        keys = row.keys()
        if key in keys:
            return row[key]
    except Exception:
        pass
    return default


def _fetchone(cursor_or_row: Any) -> Any:
    if hasattr(cursor_or_row, "fetchone"):
        return cursor_or_row.fetchone()
    return cursor_or_row


def _commit(db: Any) -> None:
    try:
        db.commit()
    except Exception:
        pass


def _has_column(db: Any, table: str, column: str) -> bool:
    try:
        return any(row[1] == column for row in db.execute(f"PRAGMA table_info({table})"))
    except Exception:
        return False


def _employee_from_row(row: Any) -> Employee:
    return Employee(
        id=int(_get(row, "id", 0) or 0),
        nombre=str(_get(row, "nombre", "") or ""),
        apellidos=str(_get(row, "apellidos", "") or ""),
        puesto=str(_get(row, "puesto", "") or ""),
        salario=float(_get(row, "salario", 0) or 0),
        fecha_ingreso=str(_get(row, "fecha_ingreso", "") or ""),
        activo=bool(_get(row, "activo", 1)),
        telefono=str(_get(row, "telefono", "") or ""),
        email=str(_get(row, "email", "") or ""),
        sucursal_id=_get(row, "sucursal_id"),
    )


def _attendance_from_row(row: Any) -> AttendanceRecord:
    return AttendanceRecord(
        id=int(_get(row, "id", 0) or 0),
        personal_id=int(_get(row, "personal_id", 0) or 0),
        fecha=str(_get(row, "fecha", "") or ""),
        hora_entrada=str(_get(row, "hora_entrada", "") or ""),
        hora_salida=str(_get(row, "hora_salida", "") or ""),
        horas_trabajadas=float(_get(row, "horas_trabajadas", 0) or 0),
        estado=str(_get(row, "estado", "PRESENTE") or "PRESENTE"),
        observaciones=str(_get(row, "observaciones", "") or ""),
    )


def _leave_from_row(row: Any) -> LeaveRequest:
    return LeaveRequest(
        id=int(_get(row, "id", 0) or 0),
        personal_id=int(_get(row, "personal_id", 0) or 0),
        tipo=str(_get(row, "tipo", "vacaciones") or "vacaciones"),
        fecha_inicio=str(_get(row, "fecha_inicio", "") or ""),
        fecha_fin=str(_get(row, "fecha_fin", "") or ""),
        dias=int(_get(row, "dias", 1) or 1),
        estado=str(_get(row, "estado", "aprobado") or "aprobado"),
        notas=str(_get(row, "notas", "") or ""),
    )


def _payment_from_row(row: Any) -> PayrollPayment:
    return PayrollPayment(
        id=int(_get(row, "id", 0) or 0),
        empleado_id=int(_get(row, "empleado_id", 0) or 0),
        periodo_inicio=str(_get(row, "periodo_inicio", "") or ""),
        periodo_fin=str(_get(row, "periodo_fin", "") or ""),
        salario_base=float(_get(row, "salario_base", 0) or 0),
        total=float(_get(row, "total", 0) or 0),
        metodo_pago=str(_get(row, "metodo_pago", "efectivo") or "efectivo"),
        estado=str(_get(row, "estado", "pagado") or "pagado"),
        usuario=str(_get(row, "usuario", "") or ""),
        bonos=float(_get(row, "bonos", 0) or 0),
        deducciones=float(_get(row, "deducciones", 0) or 0),
        fecha=str(_get(row, "fecha", "") or ""),
    )


def _role_from_row(row: Any) -> ShiftRole:
    return ShiftRole(
        id=int(_get(row, "id", 0) or 0),
        nombre=str(_get(row, "nombre", "") or ""),
        hora_inicio=str(_get(row, "hora_inicio", "08:00") or "08:00"),
        hora_fin=str(_get(row, "hora_fin", "16:00") or "16:00"),
        descripcion=str(_get(row, "descripcion", "") or ""),
        color=str(_get(row, "color", "#3498db") or "#3498db"),
        activo=bool(_get(row, "activo", 1)),
    )


def _assignment_from_row(row: Any) -> ShiftAssignment:
    return ShiftAssignment(
        id=int(_get(row, "id", 0) or 0),
        personal_id=int(_get(row, "personal_id", 0) or 0),
        turno_rol_id=int(_get(row, "turno_rol_id", 0) or 0),
        fecha_inicio=str(_get(row, "fecha_inicio", "") or ""),
        fecha_fin=str(_get(row, "fecha_fin", "") or ""),
        dia_descanso=str(_get(row, "dia_descanso", "Domingo") or "Domingo"),
        rotacion_dias=int(_get(row, "rotacion_dias", 7) or 7),
        notif_semana=bool(_get(row, "notif_semana", 1)),
        notif_dia=bool(_get(row, "notif_dia", 1)),
        activo=bool(_get(row, "activo", 1)),
        notas=str(_get(row, "notas", "") or ""),
    )


class SQLiteEmployeeRepository:
    def __init__(self, db: Any):
        self.db = db

    def get_by_id(self, employee_id: int) -> Optional[Employee]:
        row = _fetchone(self.db.execute("SELECT * FROM personal WHERE id=?", (employee_id,)))
        return _employee_from_row(row) if row else None

    def list_active(self, limit: int = 500, search: str = "") -> List[Employee]:
        rows = self.db.execute(
            "SELECT * FROM personal WHERE activo = 1 ORDER BY nombre LIMIT ?",
            (int(limit),),
        ).fetchall()
        employees = [_employee_from_row(r) for r in rows]
        filtro = (search or "").lower().strip()
        if not filtro:
            return employees
        return [
            e for e in employees
            if filtro in f"{e.nombre_completo} {e.puesto} {e.telefono}".lower()
        ]

    def list_for_lookup(self) -> List[Employee]:
        rows = self.db.execute(
            "SELECT * FROM personal WHERE activo = 1 ORDER BY nombre"
        ).fetchall()
        return [_employee_from_row(r) for r in rows]


    def create(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            """
            INSERT INTO personal (nombre, apellidos, puesto, salario, fecha_ingreso, telefono, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                data.get("nombre", ""),
                data.get("apellidos", ""),
                data.get("puesto", ""),
                float(data.get("salario", 0) or 0),
                data.get("fecha_ingreso", ""),
                data.get("telefono", ""),
            ),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def update(self, employee_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            """
            UPDATE personal SET nombre=?, apellidos=?, puesto=?, salario=?, fecha_ingreso=?, telefono=?
            WHERE id=?
            """,
            (
                data.get("nombre", ""),
                data.get("apellidos", ""),
                data.get("puesto", ""),
                float(data.get("salario", 0) or 0),
                data.get("fecha_ingreso", ""),
                data.get("telefono", ""),
                employee_id,
            ),
        )
        _commit(self.db)

    def deactivate(self, employee_id: int) -> None:
        self.db.execute("UPDATE personal SET activo = 0 WHERE id = ?", (employee_id,))
        _commit(self.db)


class SQLiteEmployeeIdentityRepository:
    """SQLite adapter for phase-9 links between personal, usuarios and drivers.

    This adapter does not mutate schema. The nullable link columns are created by
    migration 095 so existing screens can keep working while identity records are
    consolidated incrementally.
    """

    def __init__(self, db: Any):
        self.db = db
        self.employee_repository = SQLiteEmployeeRepository(db)

    def get_employee(self, employee_id: int) -> Optional[Employee]:
        return self.employee_repository.get_by_id(employee_id)

    def user_exists(self, user_id: int) -> bool:
        row = _fetchone(self.db.execute("SELECT 1 FROM usuarios WHERE id=?", (user_id,)))
        return row is not None

    def driver_exists(self, driver_id: int) -> bool:
        row = _fetchone(self.db.execute("SELECT 1 FROM drivers WHERE id=?", (driver_id,)))
        return row is not None

    def get_user_employee_id(self, user_id: int) -> Optional[int]:
        row = _fetchone(self.db.execute("SELECT personal_id FROM usuarios WHERE id=?", (user_id,)))
        value = _get(row, "personal_id") if row else None
        return int(value) if value else None

    def get_driver_employee_id(self, driver_id: int) -> Optional[int]:
        row = _fetchone(self.db.execute("SELECT personal_id FROM drivers WHERE id=?", (driver_id,)))
        value = _get(row, "personal_id") if row else None
        return int(value) if value else None

    def get_user_id_for_employee(self, employee_id: int) -> Optional[int]:
        row = _fetchone(self.db.execute("SELECT id FROM usuarios WHERE personal_id=?", (employee_id,)))
        value = _get(row, "id") if row else None
        return int(value) if value else None

    def get_driver_id_for_employee(self, employee_id: int) -> Optional[int]:
        row = _fetchone(self.db.execute("SELECT id FROM drivers WHERE personal_id=?", (employee_id,)))
        value = _get(row, "id") if row else None
        return int(value) if value else None

    def link_user_to_employee(self, user_id: int, employee_id: int) -> None:
        self.db.execute(
            "UPDATE usuarios SET personal_id=? WHERE id=?",
            (employee_id, user_id),
        )
        _commit(self.db)

    def link_driver_to_employee(self, driver_id: int, employee_id: int) -> None:
        self.db.execute(
            "UPDATE drivers SET personal_id=?, source_module=? WHERE id=?",
            (employee_id, "rrhh", driver_id),
        )
        _commit(self.db)


class SQLiteAttendanceRepository:
    def __init__(self, db: Any):
        self.db = db

    def list_between(self, date_from: str, date_to: str, employee_id: Optional[int] = None, limit: int = 300) -> List[AttendanceRecord]:
        query = """
            SELECT a.*
            FROM asistencias a
            JOIN personal p ON p.id=a.personal_id
            WHERE a.fecha BETWEEN ? AND ?
        """
        params: List[Any] = [date_from, date_to]
        if employee_id:
            query += " AND a.personal_id=?"
            params.append(employee_id)
        query += " ORDER BY a.fecha DESC, p.nombre LIMIT ?"
        params.append(int(limit))
        rows = self.db.execute(query, params).fetchall()
        return [_attendance_from_row(r) for r in rows]


    def list_between_for_table(self, date_from: str, date_to: str, employee_id: Optional[int] = None, limit: int = 300) -> List[tuple]:
        query = """
            SELECT p.nombre||' '||COALESCE(p.apellidos,''),
                   a.fecha, a.hora_entrada, a.hora_salida,
                   ROUND(COALESCE(a.horas_trabajadas,0),2), a.estado
            FROM asistencias a
            JOIN personal p ON p.id=a.personal_id
            WHERE a.fecha BETWEEN ? AND ?
        """
        params: List[Any] = [date_from, date_to]
        if employee_id:
            query += " AND a.personal_id=?"
            params.append(employee_id)
        query += " ORDER BY a.fecha DESC, p.nombre LIMIT ?"
        params.append(int(limit))
        rows = self.db.execute(query, params).fetchall()
        return [tuple(r) for r in rows]

    def get_for_date(self, employee_id: int, fecha: str) -> Optional[AttendanceRecord]:
        row = _fetchone(
            self.db.execute(
                "SELECT * FROM asistencias WHERE personal_id=? AND fecha=?",
                (employee_id, fecha),
            )
        )
        return _attendance_from_row(row) if row else None

    def register_check_in(self, employee_id: int, fecha: str, hora: str, estado: str = "PRESENTE") -> int:
        cur = self.db.execute(
            "INSERT INTO asistencias(personal_id,fecha,hora_entrada,estado) VALUES(?,?,?,?)",
            (employee_id, fecha, hora, estado),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def register_check_out(self, attendance_id: int, hora: str, horas_trabajadas: float) -> None:
        self.db.execute(
            "UPDATE asistencias SET hora_salida=?, horas_trabajadas=? WHERE id=?",
            (hora, round(float(horas_trabajadas), 2), attendance_id),
        )
        _commit(self.db)

    def upsert_manual(self, record: Dict[str, Any]) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO asistencias
                (personal_id,fecha,hora_entrada,hora_salida,horas_trabajadas,estado)
            VALUES(?,?,?,?,?,?)
            """,
            (
                record.get("personal_id"),
                record.get("fecha"),
                record.get("hora_entrada"),
                record.get("hora_salida"),
                record.get("horas_trabajadas"),
                record.get("estado", "PRESENTE"),
            ),
        )
        _commit(self.db)


class SQLiteLeaveRepository:
    def __init__(self, db: Any):
        self.db = db

    def list_recent(self, limit: int = 200) -> List[LeaveRequest]:
        rows = self.db.execute(
            """
            SELECT v.*
            FROM vacaciones_personal v
            JOIN personal p ON p.id=v.personal_id
            ORDER BY v.fecha_inicio DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [_leave_from_row(r) for r in rows]

    def list_recent_for_table(self, limit: int = 200) -> List[tuple]:
        rows = self.db.execute(
            """
            SELECT v.id, p.nombre||' '||COALESCE(p.apellidos,''),
                   v.tipo, v.fecha_inicio, v.fecha_fin, v.dias, v.estado
            FROM vacaciones_personal v
            JOIN personal p ON p.id=v.personal_id
            ORDER BY v.fecha_inicio DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [tuple(r) for r in rows]

    def create(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            """
            INSERT INTO vacaciones_personal
                (personal_id,tipo,fecha_inicio,fecha_fin,dias,estado)
            VALUES(?,?,?,?,?,?)
            """,
            (
                data.get("personal_id"),
                data.get("tipo", "vacaciones"),
                data.get("fecha_inicio"),
                data.get("fecha_fin"),
                int(data.get("dias", 1) or 1),
                data.get("estado", "aprobado"),
            ),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def update_status(self, leave_id: int, status: str) -> None:
        self.db.execute("UPDATE vacaciones_personal SET estado=? WHERE id=?", (status, leave_id))
        _commit(self.db)

    def find_overlaps(self, employee_id: int, date_from: str, date_to: str, exclude_id: Optional[int] = None) -> List[LeaveRequest]:
        query = """
            SELECT * FROM vacaciones_personal
            WHERE personal_id=?
              AND estado IN ('aprobado','pendiente')
              AND date(fecha_inicio) <= date(?)
              AND date(fecha_fin) >= date(?)
        """
        params: List[Any] = [employee_id, date_to, date_from]
        if exclude_id:
            query += " AND id<>?"
            params.append(exclude_id)
        query += " ORDER BY fecha_inicio"
        rows = self.db.execute(query, params).fetchall()
        return [_leave_from_row(r) for r in rows]


class SQLitePayrollRepository:
    def __init__(self, db: Any):
        self.db = db

    def create_payment(self, data: Dict[str, Any]) -> int:
        columns = [
            "empleado_id", "periodo_inicio", "periodo_fin", "salario_base", "bonos",
            "deducciones", "total", "metodo_pago", "estado", "usuario",
        ]
        values: List[Any] = [
            data.get("empleado_id"),
            data.get("periodo_inicio"),
            data.get("periodo_fin"),
            float(data.get("salario_base", 0) or 0),
            float(data.get("bonos", 0) or 0),
            float(data.get("deducciones", 0) or 0),
            float(data.get("total", 0) or 0),
            data.get("metodo_pago", "efectivo"),
            data.get("estado", "pagado"),
            data.get("usuario", ""),
        ]
        for optional_column in ("operation_id", "source_module", "source_id"):
            if optional_column in data and _has_column(self.db, "nomina_pagos", optional_column):
                columns.append(optional_column)
                values.append(data.get(optional_column))

        placeholders = ",".join("?" for _ in columns)
        cur = self.db.execute(
            f"INSERT INTO nomina_pagos ({','.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def get_payment(self, payment_id: int) -> Optional[PayrollPayment]:
        row = _fetchone(self.db.execute("SELECT * FROM nomina_pagos WHERE id=?", (payment_id,)))
        return _payment_from_row(row) if row else None

    def get_payment_by_operation_id(self, operation_id: str) -> Optional[PayrollPayment]:
        if not str(operation_id or "").strip() or not _has_column(self.db, "nomina_pagos", "operation_id"):
            return None
        row = _fetchone(
            self.db.execute("SELECT * FROM nomina_pagos WHERE operation_id=? LIMIT 1", (operation_id,))
        )
        return _payment_from_row(row) if row else None

    def get_latest_payment_for_employee(self, employee_id: int) -> Optional[PayrollPayment]:
        row = _fetchone(
            self.db.execute(
                "SELECT * FROM nomina_pagos WHERE empleado_id=? ORDER BY fecha DESC LIMIT 1",
                (employee_id,),
            )
        )
        return _payment_from_row(row) if row else None

    def sum_paid_between(self, date_from: str, date_to: str) -> float:
        row = _fetchone(
            self.db.execute(
                """
                SELECT COALESCE(SUM(total), 0) AS total
                FROM nomina_pagos
                WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
                  AND estado = 'pagado'
                """,
                (date_from, date_to),
            )
        )
        return float(_get(row, "total", 0) or 0)


class SQLiteShiftRepository:
    def __init__(self, db: Any):
        self.db = db

    def list_roles(self, active_only: bool = True) -> List[ShiftRole]:
        where = "WHERE activo=1" if active_only else ""
        rows = self.db.execute(f"SELECT * FROM turno_roles {where} ORDER BY nombre").fetchall()
        return [_role_from_row(r) for r in rows]

    def create_role(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            "INSERT INTO turno_roles(nombre,hora_inicio,hora_fin,descripcion,color) VALUES(?,?,?,?,?)",
            (
                data.get("nombre", ""),
                data.get("hora_inicio", "08:00"),
                data.get("hora_fin", "16:00"),
                data.get("descripcion", ""),
                data.get("color", "#3498db"),
            ),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def update_role(self, role_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE turno_roles SET nombre=?,hora_inicio=?,hora_fin=?,descripcion=?,color=? WHERE id=?",
            (
                data.get("nombre", ""),
                data.get("hora_inicio", "08:00"),
                data.get("hora_fin", "16:00"),
                data.get("descripcion", ""),
                data.get("color", "#3498db"),
                role_id,
            ),
        )
        _commit(self.db)

    def deactivate_role(self, role_id: int) -> None:
        self.db.execute("UPDATE turno_roles SET activo=0 WHERE id=?", (role_id,))
        _commit(self.db)

    def list_assignments(self, active_only: bool = True) -> List[ShiftAssignment]:
        where = "WHERE activo=1" if active_only else ""
        rows = self.db.execute(f"SELECT * FROM turno_asignaciones {where} ORDER BY personal_id").fetchall()
        return [_assignment_from_row(r) for r in rows]

    def create_assignment(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            """
            INSERT INTO turno_asignaciones
                (personal_id,turno_rol_id,fecha_inicio,fecha_fin,dia_descanso,
                 rotacion_dias,notif_semana,notif_dia)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                data.get("personal_id"),
                data.get("turno_rol_id"),
                data.get("fecha_inicio"),
                data.get("fecha_fin"),
                data.get("dia_descanso", "Domingo"),
                int(data.get("rotacion_dias", 7) or 7),
                1 if data.get("notif_semana", True) else 0,
                1 if data.get("notif_dia", True) else 0,
            ),
        )
        _commit(self.db)
        return int(cur.lastrowid)

    def update_assignment(self, assignment_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            """
            UPDATE turno_asignaciones SET personal_id=?,turno_rol_id=?,
                fecha_inicio=?,fecha_fin=?,dia_descanso=?,rotacion_dias=?,
                notif_semana=?,notif_dia=? WHERE id=?
            """,
            (
                data.get("personal_id"),
                data.get("turno_rol_id"),
                data.get("fecha_inicio"),
                data.get("fecha_fin"),
                data.get("dia_descanso", "Domingo"),
                int(data.get("rotacion_dias", 7) or 7),
                1 if data.get("notif_semana", True) else 0,
                1 if data.get("notif_dia", True) else 0,
                assignment_id,
            ),
        )
        _commit(self.db)

    def deactivate_assignment(self, assignment_id: int) -> None:
        self.db.execute("UPDATE turno_asignaciones SET activo=0 WHERE id=?", (assignment_id,))
        _commit(self.db)
