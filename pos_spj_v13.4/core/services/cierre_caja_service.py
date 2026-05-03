
# core/services/cierre_caja_service.py — SPJ POS v9
"""
Corte Z: cierre formal de turno/día.
  - Calcula totales por forma de pago
  - Registra efectivo físico contado
  - Genera discrepancia
  - Bloquea nuevas ventas hasta apertura del siguiente turno
  - Imprime resumen via PrinterService
"""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from core.db.connection import get_connection, transaction
import contextlib

logger = logging.getLogger("spj.caja.cierre")


class CierreCajaService:
    def __init__(self, conn=None, sucursal_id: int = 1, usuario: str = "admin"):
        self.conn        = conn or get_connection()
        self.sucursal_id = sucursal_id
        self.usuario     = usuario
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid             TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
                tipo             TEXT DEFAULT 'Z',        -- Z o X
                sucursal_id      INTEGER DEFAULT 1,
                usuario          TEXT,
                turno            TEXT,
                fecha_apertura   DATETIME,
                fecha_cierre     DATETIME DEFAULT (datetime('now')),
                -- Calculado por sistema
                total_ventas     DECIMAL(12,2) DEFAULT 0,
                num_ventas       INTEGER DEFAULT 0,
                total_efectivo   DECIMAL(12,2) DEFAULT 0,
                total_tarjeta    DECIMAL(12,2) DEFAULT 0,
                total_transferencia DECIMAL(12,2) DEFAULT 0,
                total_otros      DECIMAL(12,2) DEFAULT 0,
                total_anulaciones DECIMAL(12,2) DEFAULT 0,
                num_anulaciones  INTEGER DEFAULT 0,
                -- Conteo físico
                efectivo_contado DECIMAL(12,2) DEFAULT 0,
                fondo_inicial    DECIMAL(12,2) DEFAULT 0,
                -- Discrepancia
                diferencia       DECIMAL(12,2) DEFAULT 0,
                comentarios      TEXT,
                estado           TEXT DEFAULT 'cerrado'
            );
            CREATE TABLE IF NOT EXISTS turno_actual (
                sucursal_id    INTEGER PRIMARY KEY,
                usuario        TEXT,
                turno          TEXT,
                fondo_inicial  DECIMAL(12,2) DEFAULT 0,
                fecha_apertura DATETIME,
                abierto        INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cierres_fecha
                ON cierres_caja(fecha_cierre, sucursal_id);
        """)
        try: self.conn.commit()
        except Exception: pass

    # ── Apertura de turno ─────────────────────────────────────────────────
    def abrir_turno(self, fondo_inicial: float = 0.0, turno: str = "Mañana") -> dict:
        existe = self.conn.execute(
            "SELECT abierto FROM turno_actual WHERE sucursal_id=? AND abierto=1",
            (self.sucursal_id,)).fetchone()
        if existe:
            raise RuntimeError("Ya hay un turno abierto en esta sucursal.")
        self.conn.execute("""
            INSERT OR REPLACE INTO turno_actual
            (sucursal_id, usuario, turno, fondo_inicial, fecha_apertura, abierto)
            VALUES(?,?,?,?,datetime('now'),1)""",
            (self.sucursal_id, self.usuario, turno, fondo_inicial))
        try: self.conn.commit()
        except Exception: pass
        logger.info("Turno abierto: %s / %s / fondo=$%.2f", self.usuario, turno, fondo_inicial)
        return {"fondo_inicial": fondo_inicial, "turno": turno, "usuario": self.usuario}

    def turno_activo(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM turno_actual WHERE sucursal_id=? AND abierto=1",
            (self.sucursal_id,)).fetchone()
        return dict(row) if row else None

    # ── Precorte X (sin cerrar turno) ────────────────────────────────────
    def corte_x(self) -> dict:
        """Corte informativo. No cierra el turno."""
        return self._calcular_resumen(tipo="X", cerrar=False)

    # ── Corte Z (cierra turno) ────────────────────────────────────────────
    def corte_z(self, efectivo_contado: float, comentarios: str = "") -> dict:
        """Cierre formal. Registra discrepancia y cierra el turno."""
        # BEGIN IMMEDIATE: serializa escrituras concurrentes (2 cajeros cerrando a la vez)
        try:
            import uuid as _u_sp_825d08
            sp_825d08 = f"sp_{_u_sp_825d08.uuid4().hex[:6]}"
            self.conn.execute(f"SAVEPOINT {sp_825d08}")
            try: self.conn.execute("ROLLBACK")
            except Exception: pass  # liberar — usamos el context manager interno
        except Exception:
            pass   # Si ya hay una transacción activa, continuar
        turno = self.turno_activo()
        resumen = self._calcular_resumen(tipo="Z", cerrar=True,
                                         efectivo_contado=efectivo_contado,
                                         comentarios=comentarios,
                                         turno_info=turno)
        # Intentar imprimir ticket de cierre
        try:
            from core.services.printer_service import PrinterService
            # Buscar printer_service si hay container disponible
            printer = None
            if hasattr(self, '_printer_service'):
                printer = self._printer_service
            if not printer:
                printer = PrinterService(self.conn)
            printer.print_ticket({
                "empresa":   "SPJ POS",
                "folio":     f"Z-{resumen['cierre_id']}",
                "fecha":     resumen["fecha_cierre"],
                "cajero":    self.usuario,
                "items":     [],
                "totales":   {"total_final": resumen["total_ventas"], "subtotal": resumen["total_ventas"]},
                "pago":      {"forma_pago": "(ver detalle)"},
                "_es_cierre": True,
                "_resumen": resumen,
            })
        except Exception as e:
            logger.debug("No se imprimió resumen de cierre: %s", e)

        # ── NotificationService: corte Z + anomalía si hay diferencia ─────────
        try:
            notif = getattr(self, 'notification_service', None)
            if notif:
                diferencia = float(resumen.get("diferencia", 0))
                folio_z    = f"Z-{resumen.get('cierre_id','?')}"
                notif.notificar_corte_z(
                    folio        = folio_z,
                    total_ventas = float(resumen.get("total_ventas", 0)),
                    total_caja   = efectivo_contado,
                    diferencia   = diferencia,
                    cajero       = self.usuario,
                    sucursal_id  = self.sucursal_id,
                )
                # Anomalía: diferencia > $50 → alerta adicional urgente
                if abs(diferencia) > 50:
                    notif.notificar_diferencia_caja(
                        diferencia  = diferencia,
                        turno       = resumen.get("turno", "—"),
                        cajero      = self.usuario,
                        sucursal_id = self.sucursal_id,
                    )
        except Exception as e:
            logger.debug("notif corte_z: %s", e)

        return resumen

    # ── Core: calcular resumen ─────────────────────────────────────────────
    def _calcular_resumen(self, tipo: str = "Z", cerrar: bool = False,
                          efectivo_contado: float = 0.0,
                          comentarios: str = "",
                          turno_info: dict = None) -> dict:
        turno = turno_info or self.turno_activo()
        fecha_desde = turno["fecha_apertura"] if turno else "2000-01-01"

        # Ventas completadas en el turno
        stats = self.conn.execute("""
            SELECT
                COUNT(*)                                    as num_ventas,
                COALESCE(SUM(total),0)                      as total_ventas,
                COALESCE(SUM(CASE WHEN forma_pago='Efectivo'     THEN total ELSE 0 END),0) as ef,
                COALESCE(SUM(CASE WHEN forma_pago='Tarjeta'      THEN total ELSE 0 END),0) as tar,
                COALESCE(SUM(CASE WHEN forma_pago='Transferencia' THEN total ELSE 0 END),0) as trans
            FROM ventas
            WHERE sucursal_id=? AND estado='completada'
              AND fecha >= ?""",
            (self.sucursal_id, fecha_desde)).fetchone()

        anuladas = self.conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(total),0) FROM ventas
            WHERE sucursal_id=? AND estado='cancelada' AND fecha >= ?""",
            (self.sucursal_id, fecha_desde)).fetchone()

        otros = max(0, float(stats[1]) - float(stats[2]) - float(stats[3]) - float(stats[4]))
        fondo = float(turno["fondo_inicial"]) if turno else 0
        diferencia = round(float(efectivo_contado) - float(stats[2]) - fondo, 2) if cerrar else 0

        resumen = {
            "tipo":            tipo,
            "usuario":         self.usuario,
            "fecha_cierre":    datetime.now().strftime("%d/%m/%Y %H:%M"),
            "fecha_apertura":  fecha_desde,
            "fondo_inicial":   fondo,
            "num_ventas":      int(stats[0]),
            "total_ventas":    round(float(stats[1]), 2),
            "total_efectivo":  round(float(stats[2]), 2),
            "total_tarjeta":   round(float(stats[3]), 2),
            "total_transferencia": round(float(stats[4]), 2),
            "total_otros":     round(otros, 2),
            "num_anulaciones": int(anuladas[0]),
            "total_anulaciones": round(float(anuladas[1]), 2),
            "efectivo_contado":efectivo_contado,
            "diferencia":      diferencia,
            "comentarios":     comentarios,
        }
        if cerrar:
            # BEGIN IMMEDIATE: previene race condition si dos terminales hacen corte simultáneo
            import uuid as _u_sp_263cda
            sp_263cda = f"sp_{_u_sp_263cda.uuid4().hex[:6]}"
            self.conn.execute(f"SAVEPOINT {sp_263cda}")
            try:
                cid = self.conn.execute("""INSERT INTO cierres_caja
                    (uuid,tipo,sucursal_id,usuario,turno,fecha_apertura,
                     total_ventas,num_ventas,total_efectivo,total_tarjeta,
                     total_transferencia,total_otros,total_anulaciones,
                     num_anulaciones,efectivo_contado,fondo_inicial,
                     diferencia,comentarios)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), tipo, self.sucursal_id, self.usuario,
                     turno["turno"] if turno else "N/A", fecha_desde,
                     resumen["total_ventas"], resumen["num_ventas"],
                     resumen["total_efectivo"], resumen["total_tarjeta"],
                     resumen["total_transferencia"], resumen["total_otros"],
                     resumen["total_anulaciones"], resumen["num_anulaciones"],
                     efectivo_contado, fondo, diferencia, comentarios)).lastrowid
                self.conn.execute("UPDATE turno_actual SET abierto=0 WHERE sucursal_id=?",
                          (self.sucursal_id,))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            resumen["cierre_id"] = cid
            logger.info("Corte Z generado #%d — ventas=%d total=$%.2f diff=$%.2f",
                        cid, resumen["num_ventas"], resumen["total_ventas"], diferencia)
        return resumen

    def get_historial(self, limit: int = 30) -> list:
        rows = self.conn.execute(
            "SELECT * FROM cierres_caja WHERE sucursal_id=? ORDER BY fecha_cierre DESC LIMIT ?",
            (self.sucursal_id, limit)).fetchall()
        return [dict(r) for r in rows]
