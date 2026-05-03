# core/services/comisiones_service.py — SPJ POS v12
"""
Servicio de comisiones para vendedores/cajeros.

- Configurable por usuario: pct_comision, activo
- Acumula automáticamente al completar una venta
- Visible en widget del cajero durante el turno
- Se integra con nómina (RRHHService)
"""
from __future__ import annotations
import logging
from datetime import date
logger = logging.getLogger("spj.comisiones")


class ComisionesService:
    """Gestión de comisiones por venta para cajeros y vendedores."""

    def __init__(self, db_conn):
        self.db = db_conn

    # ── Config ──────────────────────────────────────────────────────────────

    def get_config(self, usuario: str) -> dict | None:
        """Retorna configuración de comisión del usuario o None si no tiene."""
        try:
            row = self.db.execute(
                "SELECT pct_comision, activo FROM comisiones_config "
                "WHERE usuario=?", (usuario,)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def set_config(self, usuario: str, pct: float, activo: bool = True,
                   sucursal_id: int = 1) -> None:
        """Crea o actualiza la configuración de comisión de un usuario."""
        self.db.execute("""
            INSERT INTO comisiones_config (usuario, pct_comision, activo, sucursal_id)
            VALUES (?,?,?,?)
            ON CONFLICT(usuario) DO UPDATE SET
                pct_comision=excluded.pct_comision,
                activo=excluded.activo
        """, (usuario, round(float(pct), 4), int(activo), sucursal_id))
        try: self.db.commit()
        except Exception: pass
        logger.info("Comisión config: usuario=%s pct=%.2f%% activo=%s", usuario, pct, activo)

    def toggle_activo(self, usuario: str, activo: bool) -> None:
        """Habilita o deshabilita comisiones para un usuario."""
        self.db.execute(
            "UPDATE comisiones_config SET activo=? WHERE usuario=?",
            (int(activo), usuario))
        try: self.db.commit()
        except Exception: pass

    def get_todos(self) -> list:
        """Lista toda la configuración de comisiones."""
        try:
            rows = self.db.execute(
                "SELECT usuario, pct_comision, activo, sucursal_id "
                "FROM comisiones_config ORDER BY usuario"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Acumulación automática ───────────────────────────────────────────────

    def registrar_comision(self, usuario: str, venta_id: int,
                           total_venta: float, sucursal_id: int = 1) -> float:
        """
        Registra la comisión de una venta completada.
        Retorna el monto de la comisión (0 si no aplica).
        Llamado automáticamente desde SalesService.
        """
        cfg = self.get_config(usuario)
        if not cfg or not cfg['activo']:
            return 0.0

        pct   = float(cfg['pct_comision'])
        monto = round(total_venta * pct / 100, 2)
        if monto <= 0:
            return 0.0

        try:
            self.db.execute("""
                INSERT INTO comisiones_acumuladas
                    (usuario, venta_id, total_venta, pct, monto, sucursal_id)
                VALUES (?,?,?,?,?,?)
            """, (usuario, venta_id, total_venta, pct, monto, sucursal_id))
            try: self.db.commit()
            except Exception: pass
            logger.debug("Comisión: usuario=%s venta=%d monto=$%.2f", usuario, venta_id, monto)
        except Exception as e:
            logger.warning("registrar_comision: %s", e)

        return monto

    # ── Consultas ────────────────────────────────────────────────────────────

    def get_comision_turno(self, usuario: str,
                           fecha: str = None) -> dict:
        """Comisión acumulada en el turno de hoy (o fecha dada)."""
        fecha = fecha or date.today().isoformat()
        try:
            row = self.db.execute("""
                SELECT COUNT(*) as ventas,
                       COALESCE(SUM(total_venta), 0) as total_vendido,
                       COALESCE(SUM(monto), 0) as comision
                FROM comisiones_acumuladas
                WHERE usuario=? AND turno_fecha=? AND pagado=0
            """, (usuario, fecha)).fetchone()
            return dict(row) if row else {'ventas':0,'total_vendido':0,'comision':0}
        except Exception:
            return {'ventas':0,'total_vendido':0,'comision':0}

    def get_comision_periodo(self, usuario: str,
                             fecha_ini: str, fecha_fin: str) -> dict:
        """Comisiones del período para liquidación de nómina."""
        try:
            row = self.db.execute("""
                SELECT COALESCE(SUM(total_venta),0) as total_vendido,
                       COALESCE(SUM(monto),0) as comision_total,
                       COUNT(*) as num_ventas
                FROM comisiones_acumuladas
                WHERE usuario=? AND turno_fecha BETWEEN ? AND ?
            """, (usuario, fecha_ini, fecha_fin)).fetchone()
            return dict(row) if row else {}
        except Exception:
            return {}

    def marcar_pagadas(self, usuario: str, fecha_ini: str,
                       fecha_fin: str) -> int:
        """Marca las comisiones como pagadas al procesar nómina."""
        n = self.db.execute("""
            UPDATE comisiones_acumuladas SET pagado=1
            WHERE usuario=? AND turno_fecha BETWEEN ? AND ? AND pagado=0
        """, (usuario, fecha_ini, fecha_fin)).rowcount
        try: self.db.commit()
        except Exception: pass
        return n
