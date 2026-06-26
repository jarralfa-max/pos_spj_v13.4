
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
from backend.shared.ids import new_uuid

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
    """Business logic for configurable alerts.

    Identity is UUIDv7 (REGLA CERO): ``alertas_config`` and ``alertas_log`` carry
    ``id TEXT PRIMARY KEY`` and ``sucursal_id TEXT``, both owned by
    ``migrations/`` — this service never creates or alters schema. A branch
    identity (UUID string) is mandatory so alerts are correctly scoped.
    """

    # Catálogo de alertas seedeable por sucursal: (tipo, activa, umbral, canal, descripcion)
    DEFAULT_CONFIG = (
        ("stock_bajo",        1, 0,    "ui",    "Stock bajo minimo"),
        ("caducidad_proxima", 1, 3,    "ui",    "Caduca en 3 dias"),
        ("venta_inusual",     1, 5000, "ui",    "Venta > $5,000"),
        ("caja_saldo_bajo",   1, 500,  "ui",    "Caja < $500"),
        ("lote_caducado",     1, 0,    "ambos", "Lote vencido"),
    )

    def __init__(self, conn=None, sucursal_id: str = None):
        self.conn = conn or get_connection()
        if not sucursal_id:
            raise ValueError("AlertasService requiere sucursal_id (UUIDv7 string).")
        self.sucursal_id = str(sucursal_id)
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass

    def seed_defaults(self) -> None:
        """Sembrar el catálogo de alertas para esta sucursal (idempotente).

        Lógica de negocio UUID-safe: cada fila lleva un id UUIDv7 explícito y el
        sucursal_id de la sesión. No crea schema. Llamar al dar de alta una
        sucursal o desde el bootstrap por-sucursal.
        """
        for tipo, activa, umbral, canal, desc in self.DEFAULT_CONFIG:
            exists = self.conn.execute(
                "SELECT 1 FROM alertas_config WHERE tipo=? AND sucursal_id=? LIMIT 1",
                (tipo, self.sucursal_id),
            ).fetchone()
            if exists:
                continue
            self.conn.execute(
                "INSERT INTO alertas_config(id,tipo,activa,umbral,canal,sucursal_id,descripcion) "
                "VALUES(?,?,?,?,?,?,?)",
                (new_uuid(), tipo, activa, umbral, canal, self.sucursal_id, desc),
            )
        try: self.conn.commit()
        except Exception: pass

    def get_config(self) -> list:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM alertas_config ORDER BY tipo").fetchall()]

    def update_config(self, alerta_id: str, activa: bool,
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
            (id,tipo,mensaje,datos,canal_enviado,sucursal_id)
            VALUES(?,?,?,?,?,?)""",
            (new_uuid(), tipo, mensaje, json.dumps(datos or {}),
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
        # Publicar ALERT_CRITICAL al EventBus cuando el canal es whatsapp/ambos
        if self._bus and cfg["canal"] in ("whatsapp", "ambos"):
            try:
                from core.events.event_bus import ALERT_CRITICAL
                self._bus.publish(ALERT_CRITICAL, {
                    "category":    tipo,
                    "severity":    "critical",
                    "title":       tipo,
                    "message":     mensaje,
                    "data":        datos or {},
                    "sucursal_id": self.sucursal_id,
                }, async_=True)
            except Exception:
                pass
        logger.info("Alerta [%s]: %s", tipo, mensaje)
        return True

    def get_no_leidas(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM alertas_log WHERE leida=0 AND sucursal_id=? ORDER BY fecha DESC LIMIT 50",
            (self.sucursal_id,)).fetchall()
        return [dict(r) for r in rows]

    def marcar_leida(self, alerta_id: str = None):
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
