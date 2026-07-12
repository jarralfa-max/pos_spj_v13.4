# core/services/rrhh_turnos_service.py
"""
RRHHTurnosService — programación de turnos y notificaciones (Remediación F).

Ruta canónica: ModuloRRHHTurnos (UI) → RRHHTurnosService → DB. Extrae el SQL
embebido en modulos/rrhh_turnos.py: roles de turno (CRUD), asignaciones (CRUD),
config de notificaciones y bitácora de envíos. El SQL se preserva EXACTO salvo
dos bugfixes de identidad born-clean documentados abajo.

Bugfix (born-clean): los INSERT de turno_roles y turno_asignaciones omitían `id`
(TEXT PRIMARY KEY sin default) → filas con id=NULL, imposibles de editar/eliminar
individualmente. El servicio genera `new_uuid()` (como ya hacía la bitácora de
notificaciones).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.services.rrhh_turnos")


class RRHHTurnosService:
    def __init__(self, db):
        self.db = db

    # ── Roles de turno ──────────────────────────────────────────────────────────
    def listar_roles_activos(self) -> list:
        return self.db.execute(
            "SELECT id,nombre,hora_inicio||'-'||hora_fin,COALESCE(descripcion,'') "
            "FROM turno_roles WHERE activo=1 ORDER BY nombre"
        ).fetchall()

    def obtener_rol(self, rol_id):
        return self.db.execute(
            "SELECT nombre,hora_inicio,hora_fin,descripcion FROM turno_roles WHERE id=?",
            (rol_id,)
        ).fetchone()

    def crear_rol(self, nombre: str, hora_inicio: str, hora_fin: str, descripcion: str) -> str:
        from backend.shared.ids import new_uuid
        rid = new_uuid()
        self.db.execute(
            "INSERT INTO turno_roles(id,nombre,hora_inicio,hora_fin,descripcion) VALUES(?,?,?,?,?)",
            (rid, nombre, hora_inicio, hora_fin, descripcion))
        self.db.commit()
        return rid

    def actualizar_rol(self, rol_id, nombre: str, hora_inicio: str, hora_fin: str, descripcion: str) -> None:
        self.db.execute(
            "UPDATE turno_roles SET nombre=?,hora_inicio=?,hora_fin=?,descripcion=? WHERE id=?",
            (nombre, hora_inicio, hora_fin, descripcion, rol_id))
        self.db.commit()

    def desactivar_rol(self, rid) -> None:
        self.db.execute("UPDATE turno_roles SET activo=0 WHERE id=?", (rid,))
        self.db.commit()

    def listar_roles_lookup(self) -> list:
        return self.db.execute(
            "SELECT id, nombre FROM turno_roles WHERE activo=1 ORDER BY nombre"
        ).fetchall()

    # ── Empleados (lookup para asignación) ──────────────────────────────────────
    def listar_empleados_lookup(self) -> list:
        return self.db.execute(
            "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal WHERE activo=1 ORDER BY nombre"
        ).fetchall()

    # ── Asignaciones ────────────────────────────────────────────────────────────
    def listar_asignaciones(self) -> list:
        return self.db.execute("""
            SELECT ta.id,
                   p.nombre||' '||COALESCE(p.apellidos,''),
                   tr.nombre,
                   ta.dia_descanso,
                   ta.fecha_inicio,
                   COALESCE(ta.fecha_fin,'Sin fin')
            FROM turno_asignaciones ta
            JOIN personal p ON p.id=ta.personal_id
            JOIN turno_roles tr ON tr.id=ta.turno_rol_id
            WHERE ta.activo=1
            ORDER BY p.nombre
        """).fetchall()

    def crear_asignacion(self, personal_id, turno_rol_id, fecha_inicio, fecha_fin,
                         dia_descanso, rotacion_dias, notif_semana, notif_dia) -> str:
        from backend.shared.ids import new_uuid
        aid = new_uuid()
        self.db.execute("""INSERT INTO turno_asignaciones
            (id,personal_id,turno_rol_id,fecha_inicio,fecha_fin,dia_descanso,rotacion_dias,notif_semana,notif_dia)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (aid, personal_id, turno_rol_id, fecha_inicio, fecha_fin,
             dia_descanso, rotacion_dias, notif_semana, notif_dia))
        self.db.commit()
        return aid

    def actualizar_asignacion(self, asig_id, personal_id, turno_rol_id, fecha_inicio,
                              fecha_fin, dia_descanso, rotacion_dias, notif_semana, notif_dia) -> None:
        self.db.execute("""UPDATE turno_asignaciones SET personal_id=?,turno_rol_id=?,
            fecha_inicio=?,fecha_fin=?,dia_descanso=?,rotacion_dias=?,
            notif_semana=?,notif_dia=? WHERE id=?""",
            (personal_id, turno_rol_id, fecha_inicio, fecha_fin,
             dia_descanso, rotacion_dias, notif_semana, notif_dia, asig_id))
        self.db.commit()

    def desactivar_asignacion(self, aid) -> None:
        self.db.execute("UPDATE turno_asignaciones SET activo=0 WHERE id=?", (aid,))
        self.db.commit()

    def listar_asignaciones_para_notificar(self, fecha_hoy: str) -> list:
        return self.db.execute("""
            SELECT ta.id, p.nombre, p.telefono, ta.dia_descanso,
                   ta.notif_semana, ta.notif_dia
            FROM turno_asignaciones ta
            JOIN personal p ON p.id=ta.personal_id
            WHERE ta.activo=1
              AND (ta.fecha_fin IS NULL OR ta.fecha_fin >= ?)
        """, (fecha_hoy,)).fetchall()

    def registrar_notificacion(self, personal_id, tipo: str, mensaje: str) -> None:
        """Registra un envío en la bitácora. Hace commit por fila (cada envío es
        independiente y ya venía envuelto en su propio try/except en la UI)."""
        from backend.shared.ids import new_uuid
        self.db.execute(
            "INSERT INTO turno_notificaciones_log(id,personal_id,tipo,mensaje) VALUES(?,?,?,?)",
            (new_uuid(), personal_id, tipo, mensaje))
        self.db.commit()

    # ── Config de notificaciones (tabla configuraciones) ────────────────────────
    def obtener_config(self, clave: str):
        return self.db.execute(
            "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
        ).fetchone()

    def guardar_config(self, clave: str, valor: str) -> None:
        self.db.execute(
            "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, valor))
        self.db.commit()
