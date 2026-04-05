
# core/services/alertas_service.py — SPJ POS v10
"""
Sistema de alertas configurables.
Tipos: stock_bajo, caducidad_proxima, venta_inusual, meta_ventas,
       empleado_tardanza, mantenimiento_pendiente, saldo_caja_bajo.
Canales: UI (popup), WhatsApp, log.
"""
from __future__ import annotations
import logging
from datetime import datetime
from core.db.connection import get_connection

logger = logging.getLogger("spj.alertas")

TIPOS_ALERTA = {
    "stock_bajo":          "Stock por debajo del minimo configurado",
    "caducidad_proxima":   "Lote caduca en <= N dias",
    "venta_inusual":       "Venta supera el umbral configurado",
    "meta_ventas":         "Ventas del dia superaron la meta",
    "caja_saldo_bajo":     "Saldo de caja por debajo del minimo",
    "lote_caducado":       "Lote marcado como caducado",
    "orden_sin_recibir":   "Orden de compra enviada hace > N dias sin recibirse",
}


class AlertasService:
    def __init__(self, conn=None, sucursal_id: int = 1):
        self.conn = conn or get_connection()
        self.sucursal_id = sucursal_id
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS alertas_config (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo        TEXT NOT NULL,
                activa      INTEGER DEFAULT 1,
                umbral      DECIMAL(12,2),   -- valor numerico del trigger
                canal       TEXT DEFAULT 'ui',  -- ui|whatsapp|ambos
                sucursal_id INTEGER DEFAULT 1,
                descripcion TEXT
            );
            CREATE TABLE IF NOT EXISTS alertas_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo        TEXT,
                mensaje     TEXT,
                datos       TEXT,  -- JSON
                leida       INTEGER DEFAULT 0,
                canal_enviado TEXT,
                sucursal_id INTEGER DEFAULT 1,
                fecha       DATETIME DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_alertas_no_leidas
                ON alertas_log(leida, fecha) WHERE leida=0;
        """)
        # Seed alertas default
        defaults = [
            ("stock_bajo",        1, 0,    "ui",        "Stock bajo minimo"),
            ("caducidad_proxima", 1, 3,    "ui",        "Caduca en 3 dias"),
            ("venta_inusual",     1, 5000, "ui",        "Venta > $5,000"),
            ("caja_saldo_bajo",   1, 500,  "ui",        "Caja < $500"),
            ("lote_caducado",     1, 0,    "ambos",     "Lote vencido"),
        ]
        for tipo, activa, umbral, canal, desc in defaults:
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO alertas_config(tipo,activa,umbral,canal,descripcion) VALUES(?,?,?,?,?)",
                    (tipo, activa, umbral, canal, desc))
            except Exception: pass
        try: self.conn.commit()
        except Exception: pass

    def get_config(self) -> list:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM alertas_config ORDER BY tipo").fetchall()]

    def update_config(self, alerta_id: int, activa: bool,
                      umbral: float = None, canal: str = None):
        updates = {"activa": 1 if activa else 0}
        if umbral is not None: updates["umbral"] = umbral
        if canal:              updates["canal"]  = canal
        sets = ",".join(f"{k}=?" for k in updates)
        self.conn.execute(
            f"UPDATE alertas_config SET {sets} WHERE id=?",
            (*updates.values(), alerta_id))
        try: self.conn.commit()
        except Exception: pass

    def disparar(self, tipo: str, mensaje: str, datos: dict = None) -> bool:
        cfg = self.conn.execute(
            "SELECT * FROM alertas_config WHERE tipo=? AND activa=1 AND sucursal_id=?",
            (tipo, self.sucursal_id)).fetchone()
        if not cfg:
            return False
        cfg = dict(cfg)
        import json
        self.conn.execute("""INSERT INTO alertas_log
            (tipo,mensaje,datos,canal_enviado,sucursal_id)
            VALUES(?,?,?,?,?)""",
            (tipo, mensaje, json.dumps(datos or {}),
             cfg["canal"], self.sucursal_id))
        try: self.conn.commit()
        except Exception: pass
        # Canal WhatsApp
        if cfg["canal"] in ("whatsapp","ambos"):
            try:
                from integrations.whatsapp_service import WhatsAppService
                wa = WhatsAppService(self.conn)
                wa.send_message(tipo, {"descripcion": mensaje})
            except Exception as e:
                logger.debug("WhatsApp alerta: %s", e)
        logger.info("Alerta [%s]: %s", tipo, mensaje)
        return True

    def get_no_leidas(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM alertas_log WHERE leida=0 AND sucursal_id=? ORDER BY fecha DESC LIMIT 50",
            (self.sucursal_id,)).fetchall()
        return [dict(r) for r in rows]

    def marcar_leida(self, alerta_id: int = None):
        if alerta_id:
            self.conn.execute("UPDATE alertas_log SET leida=1 WHERE id=?", (alerta_id,))
        else:
            self.conn.execute("UPDATE alertas_log SET leida=1 WHERE sucursal_id=?", (self.sucursal_id,))
        try: self.conn.commit()
        except Exception: pass

    # ── Checks automaticos ─────────────────────────────────────────
    def run_checks(self):
        """Ejecutar todas las verificaciones automaticas. Llamar periodicamente."""
        self._check_stock_bajo()
        self._check_caducidades()
        self._check_caja()
        self._check_ordenes_sin_recibir()

    def _check_stock_bajo(self):
        try:
            rows = self.conn.execute("""
                SELECT nombre, existencia, stock_minimo FROM productos
                WHERE activo=1 AND existencia <= stock_minimo AND stock_minimo > 0
            """).fetchall()
            for r in rows:
                self.disparar("stock_bajo",
                    f"Stock bajo: {r[0]} — {float(r[1]):.2f} (min: {float(r[2]):.2f})",
                    {"producto": r[0], "existencia": float(r[1])})
        except Exception as e: logger.debug("check_stock: %s", e)

    def _check_caducidades(self):
        try:
            cfg = self.conn.execute(
                "SELECT umbral FROM alertas_config WHERE tipo='caducidad_proxima' AND activa=1"
            ).fetchone()
            dias = int(float(cfg[0])) if cfg else 3
            from core.services.lote_service import LoteService
            ls    = LoteService(self.conn, self.sucursal_id)
            prox  = ls.get_alertas_caducidad()
            for lote in prox:
                msg = (f"VENCIDO: {lote['producto_nombre']} lote {lote['numero_lote']}"
                       if lote["vencido"] else
                       f"Caduca en {lote['dias_para_caducar']}d: {lote['producto_nombre']}")
                tipo = "lote_caducado" if lote["vencido"] else "caducidad_proxima"
                self.disparar(tipo, msg, lote)
        except Exception as e: logger.debug("check_caducidades: %s", e)

    def _check_caja(self):
        try:
            cfg = self.conn.execute(
                "SELECT umbral FROM alertas_config WHERE tipo='caja_saldo_bajo' AND activa=1"
            ).fetchone()
            if not cfg: return
            umbral = float(cfg[0])
            saldo = float(self.conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN tipo='INGRESO' THEN monto ELSE -monto END),0) "
                "FROM movimientos_caja WHERE DATE(fecha)=DATE('now')"
            ).fetchone()[0])
            if saldo < umbral:
                self.disparar("caja_saldo_bajo",
                    f"Saldo de caja: ${saldo:.2f} (umbral: ${umbral:.2f})",
                    {"saldo": saldo, "umbral": umbral})
        except Exception as e: logger.debug("check_caja: %s", e)

    def _check_ordenes_sin_recibir(self):
        try:
            rows = self.conn.execute("""
                SELECT folio, fecha_creacion FROM ordenes_compra
                WHERE estado='enviada'
                  AND JULIANDAY('now') - JULIANDAY(fecha_creacion) > 7
            """).fetchall()
            for r in rows:
                self.disparar("orden_sin_recibir",
                    f"OC {r[0]} enviada hace 7+ dias sin recibirse", {"folio": r[0]})
        except Exception as e: logger.debug("check_ordenes: %s", e)
