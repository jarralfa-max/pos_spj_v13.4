# core/services/loyalty_service.py — SPJ POS v13.30 — FASE 2
"""
LoyaltyService — servicio ÚNICO de fidelización.
Wraps GrowthEngine, conecta al flujo de cobro, registra pasivo financiero.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("spj.loyalty")


class LoyaltyService:
    """Servicio central de fidelización. Delega a GrowthEngine."""

    def __init__(self, db_conn, sucursal_id: int = 1,
                 module_config=None, whatsapp_service=None):
        self.db = db_conn
        self.sucursal_id = sucursal_id
        self._module_config = module_config
        self._engine = None
        self._init_engine(whatsapp_service)
        self._ensure_tables()

    def _init_engine(self, wa=None):
        try:
            from modulos.growth_engine import GrowthEngine
            self._engine = GrowthEngine(
                self.db, sucursal_id=self.sucursal_id, whatsapp_service=wa)
            logger.info("LoyaltyService: GrowthEngine conectado (suc=%d)", self.sucursal_id)
        except Exception as e:
            logger.warning("LoyaltyService: GrowthEngine no disponible: %s", e)

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('loyalty')
        return True

    def set_sucursal(self, sucursal_id: int):
        self.sucursal_id = sucursal_id
        if self._engine:
            self._engine.sucursal_id = sucursal_id

    # ── Acreditar puntos al completar venta ───────────────────────────────────

    def acreditar_venta(self, cliente_id: int, venta_id, cajero: str,
                        total: float, telefono: str = "",
                        nombre: str = "") -> Dict:
        """Acredita estrellas tras completar venta."""
        empty = {"estrellas_ganadas": 0, "saldo_actual": 0, "mensaje_gamificacion": ""}
        if not self.enabled or not cliente_id or not self._engine:
            return empty
        try:
            cajero_id = self._get_cajero_id(cajero)
            resultado = self._engine.procesar_venta(
                cliente_id=cliente_id, ticket_id=venta_id,
                cajero_id=cajero_id, subtotal=total,
                telefono=telefono, nombre=nombre)
            estrellas = resultado.get("estrellas_ganadas", 0)
            if estrellas > 0:
                self._registrar_pasivo(estrellas, venta_id, "acreditar")
            return resultado
        except Exception as e:
            logger.error("acreditar_venta: %s", e)
            return empty

    # ── Canjear estrellas como descuento ───────────────────────────────────────

    def canjear(self, cliente_id: int, cajero_id: int,
                subtotal: float, estrellas: int,
                venta_id: int = 0, otp: str = "") -> Dict:
        """Canjea estrellas como descuento. Cap: máx 50% del subtotal."""
        if not self.enabled or not self._engine:
            return {"ok": False, "error": "Fidelización deshabilitada"}
        resultado = self._engine.canjear_estrellas(
            cliente_id=cliente_id, cajero_id=cajero_id,
            subtotal=subtotal, estrellas_a_canjear=estrellas,
            ticket_id=venta_id, otp_codigo=otp)
        if resultado.get("ok"):
            canjeadas = resultado.get("estrellas_canjeadas", 0)
            if canjeadas > 0:
                self._registrar_pasivo(-canjeadas, venta_id, "canje")
        return resultado

    # ── Consultas ─────────────────────────────────────────────────────────────

    def saldo(self, cliente_id: int) -> int:
        if not self._engine:
            return 0
        return self._engine.saldo_cliente(cliente_id)

    def pasivo_financiero(self) -> Dict:
        if not self._engine:
            return {"total_estrellas": 0, "valor_monetario": 0.0}
        return self._engine.pasivo_financiero()

    def solicitar_otp(self, cliente_id: int, estrellas: int, telefono: str) -> str:
        if not self._engine:
            return ""
        return self._engine.generar_otp(cliente_id, estrellas, telefono)

    # ── Pasivo financiero ─────────────────────────────────────────────────────

    def _registrar_pasivo(self, estrellas: int, referencia, tipo: str):
        try:
            valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
            monto = estrellas * valor
            self.db.execute(
                "INSERT INTO loyalty_pasivo_log "
                "(fecha, tipo, estrellas, valor_unitario, monto_total, referencia, sucursal_id) "
                "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)",
                (tipo, estrellas, valor, monto, str(referencia), self.sucursal_id))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_registrar_pasivo: %s", e)

    def _ensure_tables(self):
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS loyalty_pasivo_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT DEFAULT (datetime('now')),
                    tipo TEXT NOT NULL,
                    estrellas INTEGER DEFAULT 0,
                    valor_unitario REAL DEFAULT 0.10,
                    monto_total REAL DEFAULT 0.0,
                    referencia TEXT DEFAULT '',
                    sucursal_id INTEGER DEFAULT 1
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    def _get_cajero_id(self, nombre: str) -> int:
        try:
            row = self.db.execute(
                "SELECT id FROM usuarios WHERE nombre=? LIMIT 1",
                (nombre,)).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _cfg(self, key: str, default: str = "") -> str:
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?",
                (key,)).fetchone()
            return row[0] if row and row[0] else default
        except Exception:
            return default
