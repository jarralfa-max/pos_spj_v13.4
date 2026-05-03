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
                 module_config=None, whatsapp_service=None,
                 finance_service=None):
        self.db = db_conn
        self.sucursal_id = sucursal_id
        self._module_config = module_config
        self._finance = finance_service
        self._engine = None
        self._bus = None
        self._init_engine(whatsapp_service)
        self._init_bus()
        self._ensure_tables()

    def _init_bus(self):
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass

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
                self._publish_puntos(cliente_id, estrellas,
                                     resultado.get("saldo_actual", 0), venta_id)
                # Ledger unificado Fase 2
                self.registrar_en_ledger(
                    cliente_id=cliente_id,
                    tipo="acumulacion",
                    puntos=estrellas,
                    referencia=str(venta_id),
                    descripcion=f"Acumulación venta #{venta_id}",
                    usuario=cajero,
                )
            return resultado
        except Exception as e:
            logger.error("acreditar_venta: %s", e)
            return empty

    def process_loyalty_for_sale(self, client_id: int,
                                  total_sale: float,
                                  branch_id: int = 1) -> Dict:
        """
        API unificada llamada por wiring.py, use_cases/venta.py y sales_service.py.

        Mapea a acreditar_venta() y normaliza las claves de retorno para que
        todos los consumidores reciban: puntos_ganados, puntos_totales, nivel, mensaje.
        """
        resultado = self.acreditar_venta(
            cliente_id=client_id,
            venta_id=0,
            cajero="Sistema",
            total=total_sale,
        )
        estrellas = resultado.get("estrellas_ganadas", 0)
        saldo = resultado.get("saldo_actual", 0)

        # Calcular nivel con la regla de dominio centralizada
        nivel = "Bronce"
        try:
            from core.domain.models import LoyaltySnapshot
            nivel = LoyaltySnapshot.calcular_nivel(saldo)
        except Exception:
            pass

        return {
            # Claves legacy (GrowthEngine)
            "estrellas_ganadas":    estrellas,
            "saldo_actual":         saldo,
            "mensaje_gamificacion": resultado.get("mensaje_gamificacion", ""),
            # Claves normalizadas (use_cases/venta.py, sales_service.py)
            "puntos_ganados":       estrellas,
            "puntos_totales":       saldo,
            "nivel":                nivel,
            "mensaje":              resultado.get("mensaje_gamificacion", ""),
        }

    def _publish_puntos(self, cliente_id: int, estrellas: int,
                        saldo: int, venta_id) -> None:
        """Publica PUNTOS_ACUMULADOS y NIVEL_CAMBIADO al EventBus."""
        if not self._bus:
            return
        try:
            from core.events.event_bus import PUNTOS_ACUMULADOS
            self._bus.publish(PUNTOS_ACUMULADOS, {
                "cliente_id":    cliente_id,
                "estrellas":     estrellas,
                "saldo_actual":  saldo,
                "venta_id":      venta_id,
                "sucursal_id":   self.sucursal_id,
            }, async_=True)
        except Exception:
            pass
        try:
            from core.events.event_bus import NIVEL_CAMBIADO
            from core.domain.models import LoyaltySnapshot
            nivel_actual = LoyaltySnapshot.calcular_nivel(saldo)
            nivel_previo = LoyaltySnapshot.calcular_nivel(max(0, saldo - estrellas))
            if nivel_actual != nivel_previo:
                self._bus.publish(NIVEL_CAMBIADO, {
                    "cliente_id":   cliente_id,
                    "nivel_previo": nivel_previo,
                    "nivel_nuevo":  nivel_actual,
                    "saldo":        saldo,
                    "sucursal_id":  self.sucursal_id,
                }, async_=True)
        except Exception:
            pass

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
                # Ledger unificado Fase 2
                self.registrar_en_ledger(
                    cliente_id=cliente_id,
                    tipo="canje",
                    puntos=-canjeadas,
                    referencia=str(venta_id),
                    descripcion=f"Canje venta #{venta_id}",
                    usuario=str(cajero_id),
                )
                # Asiento contable (CLAUDE.md regla 8: todo impacto financiero)
                if self._finance:
                    try:
                        valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
                        monto = canjeadas * valor
                        self._finance.registrar_asiento(
                            debe="215.1-pasivo-fidelizacion",
                            haber="401.1-descuento-clientes",
                            concepto=f"Canje estrellas venta #{venta_id}",
                            monto=monto,
                            modulo="loyalty",
                            referencia_id=venta_id,
                            usuario_id=cajero_id,
                            sucursal_id=self.sucursal_id,
                            evento="LOYALTY_CANJE",
                        )
                    except Exception as exc:
                        logger.debug("loyalty registrar_asiento: %s", exc)
        return resultado

    # ── Consultas ─────────────────────────────────────────────────────────────

    def compute_redemption_discount(self, pts: int, subtotal: float) -> float:
        """
        Calcula el descuento monetario por canje de `pts` puntos/estrellas.
        Cap: máximo 50% del subtotal.
        Puro (sin efectos secundarios) — seguro para llamar pre-pago.
        """
        if pts <= 0 or subtotal <= 0:
            return 0.0
        valor_por_estrella = float(self._cfg("loyalty_valor_estrella", "0.10"))
        descuento = pts * valor_por_estrella
        return round(min(descuento, subtotal * 0.5), 2)

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

    # ── Ledger unificado (Fase 2 — Plan Maestro SPJ v13.4) ───────────────────

    def registrar_en_ledger(self, cliente_id: int, tipo: str,
                             puntos: int, referencia: str = "",
                             descripcion: str = "", usuario: str = "",
                             monto_equiv: float = 0.0) -> bool:
        """
        Registra un movimiento en loyalty_ledger (tabla unificada Fase 2).
        tipo: 'acumulacion' | 'canje' | 'reversa' | 'ajuste'
        puntos: positivo para acumulacion/ajuste, negativo para canje/reversa.
        """
        try:
            saldo_actual = self.saldo(cliente_id)
            saldo_post = saldo_actual + puntos
            if monto_equiv == 0.0 and puntos != 0:
                try:
                    valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
                    monto_equiv = abs(puntos) * valor
                except Exception:
                    pass
            self.db.execute("""
                INSERT INTO loyalty_ledger
                    (cliente_id, tipo, puntos, monto_equiv, saldo_post,
                     referencia, descripcion, sucursal_id, usuario)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                cliente_id, tipo, puntos, monto_equiv, saldo_post,
                str(referencia), descripcion, self.sucursal_id, usuario,
            ))
            try:
                self.db.commit()
            except Exception:
                pass
            return True
        except Exception as exc:
            logger.debug("registrar_en_ledger: %s", exc)
            return False

    def reversar_canje(self, cliente_id: int, puntos_canjeados: int,
                       referencia: str = "", usuario: str = "") -> Dict:
        """
        Reversa un canje de puntos: devuelve puntos al cliente y
        registra el movimiento como 'reversa' en loyalty_ledger y pasivo.
        Fase 2 — Plan Maestro SPJ v13.4.
        """
        if not self.enabled or puntos_canjeados <= 0 or not cliente_id:
            return {"ok": False, "error": "Parámetros inválidos"}
        try:
            # Devolver puntos al cliente
            self.db.execute(
                "UPDATE clientes SET puntos = COALESCE(puntos, 0) + ? WHERE id = ?",
                (puntos_canjeados, cliente_id))
            # Registrar en ledger unificado (reversa = +puntos devueltos)
            self.registrar_en_ledger(
                cliente_id=cliente_id,
                tipo="reversa",
                puntos=puntos_canjeados,
                referencia=referencia,
                descripcion=f"Reversa de canje — ref:{referencia}",
                usuario=usuario,
            )
            # Ajustar pasivo financiero
            self._registrar_pasivo(puntos_canjeados, referencia, "reversa")
            try:
                self.db.commit()
            except Exception:
                pass
            nuevo_saldo = self.saldo(cliente_id)
            logger.info("Reversa canje cliente=%d puntos=%d ref=%s",
                        cliente_id, puntos_canjeados, referencia)
            return {
                "ok": True,
                "puntos_devueltos": puntos_canjeados,
                "saldo_nuevo": nuevo_saldo,
            }
        except Exception as exc:
            logger.error("reversar_canje: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_ledger_cliente(self, cliente_id: int, limit: int = 50) -> list:
        """Retorna los últimos movimientos del loyalty_ledger para un cliente."""
        try:
            rows = self.db.execute("""
                SELECT tipo, puntos, monto_equiv, saldo_post,
                       referencia, descripcion, created_at
                FROM loyalty_ledger
                WHERE cliente_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (cliente_id, limit)).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.debug("get_ledger_cliente: %s", exc)
            return []

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
