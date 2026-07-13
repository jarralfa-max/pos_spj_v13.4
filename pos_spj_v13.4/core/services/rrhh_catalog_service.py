# core/services/rrhh_catalog_service.py
"""
RRHHCatalogService — lecturas y escrituras operativas de RRHH (Remediación F).

Ruta canónica: ModuloRRHH (UI) → RRHHCatalogService → DB. Extrae el SQL que vivía
embebido en modulos/rrhh.py para catálogos (roles de turno, puestos), KPIs del
tablero, vacaciones, evaluaciones, recibo de nómina y reglas laborales. El SQL se
preserva EXACTO salvo un bugfix de identidad born-clean documentado abajo.

Bugfix (born-clean): el INSERT de turno_roles omitía `id` (TEXT PRIMARY KEY sin
default), insertando filas con id=NULL — imposibles de eliminar de forma individual.
El servicio genera `new_uuid()` como hacen ya puestos y evaluaciones.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.services.rrhh_catalog")


class RRHHCatalogService:
    def __init__(self, db):
        self.db = db

    # ── KPIs del tablero ────────────────────────────────────────────────────────
    # Consultas individuales (el SQL se preserva verbatim). La UI las llama en
    # secuencia dentro de un único try/except, igual que antes: si una columna no
    # existe en el esquema, el KPI correspondiente queda con su valor por defecto.
    def contar_empleados_activos(self) -> int:
        r = self.db.execute("SELECT COUNT(*) FROM personal WHERE activo=1").fetchone()
        return int(r[0] or 0)

    def contar_en_turno(self) -> int:
        r = self.db.execute("SELECT COUNT(*) FROM personal WHERE activo=1 AND en_turno=1").fetchone()
        return int(r[0] or 0)

    def sumar_nomina_activos(self) -> float:
        r = self.db.execute("SELECT COALESCE(SUM(salario),0) FROM personal WHERE activo=1").fetchone()
        return float(r[0] or 0)

    def contar_ausencias_hoy(self) -> int:
        r = self.db.execute(
            "SELECT COUNT(*) FROM asistencias WHERE DATE(fecha)=DATE('now') AND tipo='ausencia'"
        ).fetchone()
        return int(r[0] or 0)

    def contar_en_vacaciones(self) -> int:
        r = self.db.execute("SELECT COUNT(*) FROM personal WHERE activo=1 AND en_vacaciones=1").fetchone()
        return int(r[0] or 0)

    # ── Roles de turno ──────────────────────────────────────────────────────────
    def listar_roles_turno(self) -> list:
        return self.db.execute(
            "SELECT id, nombre, hora_inicio, hora_fin, COALESCE(color,'#3498db') "
            "FROM turno_roles ORDER BY nombre"
        ).fetchall()

    def crear_rol_turno(self, nombre: str, hora_inicio: str, hora_fin: str, color: str) -> str:
        from backend.shared.ids import new_uuid
        rid = new_uuid()
        self.db.execute(
            "INSERT INTO turno_roles(id,nombre,hora_inicio,hora_fin,color) VALUES(?,?,?,?,?)",
            (rid, nombre, hora_inicio, hora_fin, color))
        self.db.commit()
        return rid

    def eliminar_rol_turno(self, rid) -> None:
        self.db.execute("DELETE FROM turno_roles WHERE id=?", (rid,))
        self.db.commit()

    # ── Puestos ─────────────────────────────────────────────────────────────────
    def listar_puestos(self) -> list:
        return self.db.execute(
            "SELECT id,nombre,COALESCE(descripcion,'') FROM puestos WHERE activo=1 ORDER BY nombre"
        ).fetchall()

    def obtener_puesto(self, puesto_id):
        return self.db.execute(
            "SELECT nombre,descripcion FROM puestos WHERE id=?", (puesto_id,)
        ).fetchone()

    def actualizar_puesto(self, puesto_id, nombre: str, descripcion: str) -> None:
        self.db.execute(
            "UPDATE puestos SET nombre=?,descripcion=? WHERE id=?",
            (nombre, descripcion, puesto_id))
        self.db.commit()

    def crear_puesto(self, nombre: str, descripcion: str) -> str:
        from backend.shared.ids import new_uuid
        pid = new_uuid()
        self.db.execute(
            "INSERT INTO puestos(id,nombre,descripcion) VALUES(?,?,?)", (pid, nombre, descripcion))
        self.db.commit()
        return pid

    def desactivar_puesto(self, puesto_id) -> None:
        self.db.execute("UPDATE puestos SET activo=0 WHERE id=?", (puesto_id,))
        self.db.commit()

    # ── Vacaciones ──────────────────────────────────────────────────────────────
    def actualizar_estado_vacacion(self, vac_id, nuevo_estado: str) -> None:
        self.db.execute(
            "UPDATE vacaciones_personal SET estado=? WHERE id=?", (nuevo_estado, vac_id))
        self.db.commit()

    # ── Evaluaciones ────────────────────────────────────────────────────────────
    def listar_evaluaciones(self) -> list:
        return self.db.execute("""
            SELECT p.nombre||' '||COALESCE(p.apellidos,''),
                   e.periodo, e.calificacion, e.evaluador, e.fecha
            FROM evaluaciones_personal e
            JOIN personal p ON p.id=e.personal_id
            ORDER BY e.fecha DESC LIMIT 200
        """).fetchall()

    def crear_evaluacion(self, personal_id, periodo: str, calificacion, evaluador: str) -> str:
        from backend.shared.ids import new_uuid
        eid = new_uuid()
        self.db.execute(
            "INSERT INTO evaluaciones_personal(id,personal_id,periodo,calificacion,evaluador,fecha) "
            "VALUES(?,?,?,?,?,date('now'))",
            (eid, personal_id, periodo, calificacion, evaluador))
        self.db.commit()
        return eid

    # ── Recibo de nómina ────────────────────────────────────────────────────────
    def obtener_pago_por_id(self, pago_id):
        return self.db.execute(
            "SELECT np.*, p.nombre, p.apellidos, p.puesto, p.rfc "
            "FROM nomina_pagos np JOIN personal p ON p.id=np.empleado_id "
            "WHERE np.id=?", (pago_id,)
        ).fetchone()

    def obtener_ultimo_pago_empleado(self, empleado_id):
        return self.db.execute(
            "SELECT np.*, p.nombre, p.apellidos, p.puesto, p.rfc "
            "FROM nomina_pagos np JOIN personal p ON p.id=np.empleado_id "
            "WHERE np.empleado_id=? ORDER BY np.fecha DESC LIMIT 1",
            (empleado_id,)
        ).fetchone()

    def obtener_nombre_empresa(self):
        return self.db.execute(
            "SELECT valor FROM configuraciones WHERE clave='nombre_empresa'"
        ).fetchone()

    # ── Reglas laborales (tabla configuraciones) ────────────────────────────────
    def obtener_config(self, clave: str):
        return self.db.execute(
            "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
        ).fetchone()

    def guardar_config(self, clave: str, valor: str, descripcion: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO configuraciones "
            "(clave, valor, descripcion) VALUES (?,?,?)",
            (clave, valor, descripcion))
        self.db.commit()
