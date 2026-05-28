# core/services/loyalty_service.py — SPJ POS v13.30 — FASE 2
"""
LoyaltyService — servicio ÚNICO de fidelización.
Usa LoyaltyApplicationService/Repository, conecta al flujo de cobro y registra pasivo financiero.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("spj.loyalty")


def _csv_tokens(raw: Any) -> set[str]:
    return {str(x).strip().lower() for x in str(raw or "").split(",") if str(x).strip()}


class LoyaltyService:
    """Servicio central de fidelización. Sin dependencia a modulos.growth_engine."""

    def __init__(self, db_conn, sucursal_id: int = 1,
                 module_config=None, whatsapp_service=None,
                 finance_service=None):
        self.db = db_conn
        self.sucursal_id = sucursal_id
        self._module_config = module_config
        self._finance = finance_service
        self._engine = None
        self._bus = None
        from application.services.loyalty_application_service import LoyaltyApplicationService
        self._app = LoyaltyApplicationService(self.db)
        self._init_bus()
        self._ensure_tables()

    def _init_bus(self):
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass

    def _init_engine(self, wa=None):
        return None

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('loyalty')
        return True

    def set_sucursal(self, sucursal_id: int):
        self.sucursal_id = sucursal_id

    # ── Acreditar puntos al completar venta ───────────────────────────────────

    def acreditar_venta(self, cliente_id: int, venta_id, cajero: str,
                        total: float, telefono: str = "",
                        nombre: str = "") -> Dict:
        """Acredita estrellas tras completar venta."""
        empty = {"estrellas_ganadas": 0, "saldo_actual": 0, "mensaje_gamificacion": ""}
        if not self.enabled or not cliente_id:
            return empty
        try:
            tasa = float(self._cfg("loyalty_earn_rate", "0.1") or "0.1")
            estrellas = max(0, int(float(total or 0.0) * tasa))
            resultado = self._app.award_points_for_sale(
                cliente_id=int(cliente_id), venta_id=str(venta_id), puntos=estrellas,
                sucursal_id=self.sucursal_id, usuario=str(cajero or ""),
            )
            if estrellas > 0:
                is_idempotent = bool(resultado.get("idempotent"))
                awarded = int(resultado.get("puntos_otorgados", estrellas) or 0)
                if awarded > 0 and not is_idempotent:
                    # La transacción la controla el orquestador superior (SalesService/SAVEPOINT).
                    self._registrar_pasivo(awarded, venta_id, "acreditar", commit=False)
                if not is_idempotent:
                    self._publish_puntos(cliente_id, estrellas,
                                         resultado.get("saldo", 0), venta_id)
                if not is_idempotent and awarded > 0:
                    self._publish_loyalty_fin_event("LOYALTY_POINTS_EARNED", cliente_id, estrellas, venta_id, cajero)
            return {"estrellas_ganadas": estrellas, "saldo_actual": resultado.get("saldo", self.saldo(cliente_id)), "mensaje_gamificacion": ""}
        except Exception as e:
            logger.error("acreditar_venta: %s", e)
            return empty

    def process_loyalty_for_sale(self, client_id: int,
                                  total_sale: float,
                                  branch_id: int = 1,
                                  venta_id=None,
                                  usuario: str = "Sistema") -> Dict:
        """
        API unificada llamada por wiring.py, use_cases/venta.py y sales_service.py.

        Mapea a acreditar_venta() y normaliza las claves de retorno para que
        todos los consumidores reciban: puntos_ganados, puntos_totales, nivel, mensaje.
        """
        resultado = self.acreditar_venta(
            cliente_id=client_id,
            venta_id=(venta_id if venta_id is not None else f"op:{branch_id}:{client_id}:{int(total_sale*100)}"),
            cajero=usuario,
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
        if not self.enabled:
            return {"ok": False, "error": "Fidelización deshabilitada"}
        resultado = self._app.redeem_points_for_sale(
            cliente_id=int(cliente_id), venta_id=str(venta_id), puntos=int(estrellas),
            sucursal_id=self.sucursal_id, usuario=str(cajero_id),
        )
        if resultado.get("ok"):
            is_idempotent = bool(resultado.get("idempotent"))
            canjeadas = int(resultado.get("puntos_canjeados", 0))
            if canjeadas > 0 and not is_idempotent:
                # La transacción la controla el orquestador superior (SalesService/SAVEPOINT).
                self._registrar_pasivo(-canjeadas, venta_id, "canje", commit=False)
                self._publish_loyalty_fin_event("LOYALTY_POINTS_REDEEMED", cliente_id, -canjeadas, venta_id, str(cajero_id))
        return resultado

    def apply_redemption(self, cliente_id: int, venta_id, cajero_id,
                         subtotal: float, puntos: int, otp: str = "") -> Dict:
        """
        Ejecuta el canje real de puntos con referencia de venta.
        Idempotente por (cliente_id, tipo='canje', referencia=venta_id).
        """
        if not cliente_id or not venta_id or puntos <= 0:
            return {"ok": False, "error": "Parámetros inválidos"}
        ref = str(venta_id)
        if self._ledger_exists(cliente_id, "canje", ref):
            return {"ok": True, "idempotent": True, "referencia": ref}
        cajero_num = 0
        try:
            cajero_num = int(cajero_id)
        except Exception:
            try:
                cajero_num = self._get_cajero_id(str(cajero_id))
            except Exception:
                cajero_num = 0
        return self.canjear(
            cliente_id=cliente_id,
            cajero_id=cajero_num,
            subtotal=float(subtotal),
            estrellas=int(puntos),
            venta_id=venta_id,
            otp=otp,
        )

    # ── Consultas ─────────────────────────────────────────────────────────────

    # ── Consultas ricas para la UI ────────────────────────────────────────────

    def preview_redemption(
        self,
        cliente_id: int,
        subtotal: float,
        puntos_solicitados: int | None = None,
    ) -> dict:
        """
        Devuelve un preview de canje sin efectos secundarios.

        Seguro para llamar antes de confirmar el pago — no registra ni
        decrementa puntos.  La UI debe usar este método para poblar el
        diálogo de canje en lugar de calcular los valores localmente.

        Returns:
            {
              "enabled":               bool,
              "cliente_id":            int,
              "puntos_disponibles":    int,
              "valor_por_punto":       float,
              "min_puntos_canje":      int,
              "max_pct_canje":         float,   # 0.5 = 50%
              "puntos_maximos_canjeables": int,
              "descuento_maximo":      float,
              "puntos_solicitados":    int,
              "descuento":             float,
              "total_original":        float,
              "total_con_descuento":   float,
              "nivel":                 str,
              "mensaje":               str,
            }
        """
        if not self.enabled or not cliente_id:
            return self._preview_empty(cliente_id, subtotal, "Fidelización deshabilitada")

        saldo = self.saldo(cliente_id)
        valor_por_punto = float(self._cfg("loyalty_valor_estrella", "0.10"))
        min_pts = int(float(self._cfg("loyalty_min_puntos_canje", "0") or "0"))
        max_pct = float(self._cfg("loyalty_max_pct_canje", "0.5") or "0.5")

        max_pts_por_pct = int(subtotal * max_pct / valor_por_punto) if valor_por_punto > 0 else 0
        # If saldo < min_puntos_canje threshold, client cannot redeem at all
        puede_canjear_minimo = (min_pts == 0 or saldo >= min_pts)
        puntos_max = min(saldo, max_pts_por_pct) if puede_canjear_minimo else 0
        descuento_max = round(puntos_max * valor_por_punto, 2)

        puede_canjear = puede_canjear_minimo and puntos_max > 0

        if puntos_solicitados is None:
            puntos_solicitados = puntos_max if puede_canjear else 0
        else:
            puntos_solicitados = max(0, min(puntos_solicitados, puntos_max))

        descuento = round(puntos_solicitados * valor_por_punto, 2)
        total_con_descuento = round(max(0.0, subtotal - descuento), 2)

        nivel = "Bronce"
        try:
            from core.domain.models import LoyaltySnapshot
            nivel = LoyaltySnapshot.calcular_nivel(saldo)
        except Exception:
            pass

        if not puede_canjear and saldo < min_pts and saldo > 0:
            mensaje = f"Mínimo {min_pts} puntos para canjear (tienes {saldo})"
        elif puntos_solicitados > 0:
            mensaje = f"Canje de {puntos_solicitados} pts → -${descuento:.2f}"
        else:
            mensaje = ""

        return {
            "enabled":                  True,
            "cliente_id":               cliente_id,
            "puntos_disponibles":       saldo,
            "valor_por_punto":          valor_por_punto,
            "min_puntos_canje":         min_pts,
            "max_pct_canje":            max_pct,
            "puntos_maximos_canjeables": puntos_max,
            "descuento_maximo":         descuento_max,
            "puntos_solicitados":       puntos_solicitados,
            "descuento":                descuento,
            "total_original":           subtotal,
            "total_con_descuento":      total_con_descuento,
            "nivel":                    nivel,
            "mensaje":                  mensaje,
        }

    def _preview_empty(self, cliente_id: int, subtotal: float, mensaje: str) -> dict:
        return {
            "enabled":                  False,
            "cliente_id":               cliente_id or 0,
            "puntos_disponibles":       0,
            "valor_por_punto":          0.0,
            "min_puntos_canje":         0,
            "max_pct_canje":            0.5,
            "puntos_maximos_canjeables": 0,
            "descuento_maximo":         0.0,
            "puntos_solicitados":       0,
            "descuento":                0.0,
            "total_original":           subtotal,
            "total_con_descuento":      subtotal,
            "nivel":                    "Bronce",
            "mensaje":                  mensaje,
        }

    def get_customer_loyalty_summary(
        self, cliente_id: int, subtotal: float | None = None
    ) -> dict:
        """
        Resumen completo de fidelización para un cliente.

        Incluye saldo, nivel, historial reciente y — si se provee subtotal —
        un preview de canje.  Diseñado para poblar sidebars/cards de la UI
        sin que la UI calcule nada localmente.

        Returns:
            {
              "enabled":       bool,
              "cliente_id":    int,
              "saldo":         int,
              "nivel":         str,
              "ledger":        list[dict],   # últimos 10 movimientos
              "preview":       dict | None,  # preview_redemption si subtotal dado
            }
        """
        if not self.enabled:
            return {"enabled": False, "cliente_id": cliente_id or 0,
                    "saldo": 0, "nivel": "Bronce", "ledger": [], "preview": None}

        saldo = self.saldo(cliente_id)
        nivel = "Bronce"
        try:
            from core.domain.models import LoyaltySnapshot
            nivel = LoyaltySnapshot.calcular_nivel(saldo)
        except Exception:
            pass

        ledger = self.get_ledger_cliente(cliente_id, limit=10)
        preview = self.preview_redemption(cliente_id, subtotal) if subtotal is not None else None

        return {
            "enabled":    True,
            "cliente_id": cliente_id,
            "saldo":      saldo,
            "nivel":      nivel,
            "ledger":     ledger,
            "preview":    preview,
        }

    def get_puntos(self, cliente_id: int) -> dict:
        """
        Alias de conveniencia (compatible con código existente en sales_service.py).
        Retorna puntos_totales y puntos_ganados (siempre 0 — saldo estático).
        """
        saldo = self.saldo(cliente_id)
        return {"puntos_totales": saldo, "puntos_ganados": 0, "nivel": "Bronce"}

    def compute_redemption_discount(self, pts: int, subtotal: float) -> float:
        """
        Calcula el descuento monetario por canje de `pts` puntos/estrellas.
        Cap: máximo 50% del subtotal.
        Puro (sin efectos secundarios) — seguro para llamar pre-pago.
        """
        if pts <= 0 or subtotal <= 0:
            return 0.0
        valor_por_estrella = float(self._cfg("loyalty_valor_estrella", "0.10"))
        max_pct = float(self._cfg("loyalty_max_pct_canje", "0.5") or "0.5")
        descuento = pts * valor_por_estrella
        return round(min(descuento, subtotal * max_pct), 2)

    def saldo(self, cliente_id: int) -> int:
        try:
            from repositories.loyalty_repository import LoyaltyRepository
            return LoyaltyRepository(self.db).get_balance(cliente_id)
        except Exception:
            return 0

    def pasivo_financiero(self) -> Dict:
        """
        Calcula pasivo financiero desde `loyalty_pasivo_log` (bitácora auxiliar).
        No representa el saldo canónico de puntos; ese saldo está en `loyalty_ledger`
        y se consulta vía `saldo()`.
        """
        total = self.db.execute("SELECT COALESCE(SUM(estrellas),0) FROM loyalty_pasivo_log").fetchone()[0]
        valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
        return {"total_estrellas": int(total or 0), "valor_monetario": float((total or 0) * valor)}

    def pasivo_operativo_desde_ledger(self) -> Dict:
        """
        Estimación operativa desde el ledger canónico (`loyalty_ledger`).
        Útil para contraste/auditoría con `pasivo_financiero()` sin cambiar la UI actual.
        """
        total = self.db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger").fetchone()[0]
        valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
        return {"total_estrellas": int(total or 0), "valor_monetario": float((total or 0) * valor)}

    def solicitar_otp(self, cliente_id: int, estrellas: int, telefono: str) -> str:
        return ""

    # ── Pasivo financiero (bitácora auxiliar; asientos vía handler de eventos) ─────


    def _publish_loyalty_fin_event(self, event_name: str, cliente_id: int, puntos: int, referencia, usuario: str = "") -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import (
                LOYALTY_POINTS_EARNED, LOYALTY_POINTS_REDEEMED,
                LOYALTY_POINTS_EXPIRED, LOYALTY_POINTS_REVERSED,
            )
            mapping = {
                "LOYALTY_POINTS_EARNED": LOYALTY_POINTS_EARNED,
                "LOYALTY_POINTS_REDEEMED": LOYALTY_POINTS_REDEEMED,
                "LOYALTY_POINTS_EXPIRED": LOYALTY_POINTS_EXPIRED,
                "LOYALTY_POINTS_REVERSED": LOYALTY_POINTS_REVERSED,
            }
            ev = mapping.get(event_name)
            if not ev:
                return
            self._bus.publish(ev, {
                "cliente_id": cliente_id,
                "puntos": int(puntos),
                "referencia": str(referencia),
                "sucursal_id": self.sucursal_id,
                "usuario": str(usuario or ""),
                "source": "loyalty_service",
            }, async_=True)
        except Exception:
            pass

    def _registrar_pasivo(self, estrellas: int, referencia, tipo: str, commit: bool = False):
        # IMPORTANTE: en flujo de venta transaccional usar commit=False.
        # El commit debe hacerlo el orquestador superior para preservar atomicidad.
        try:
            valor = float(self._cfg("loyalty_valor_estrella", "0.10"))
            monto = estrellas * valor
            self.db.execute(
                "INSERT INTO loyalty_pasivo_log "
                "(fecha, tipo, estrellas, valor_unitario, monto_total, referencia, sucursal_id) "
                "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)",
                (tipo, estrellas, valor, monto, str(referencia), self.sucursal_id))
            if commit:
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
                             monto_equiv: float = 0.0,
                             commit: bool = False) -> bool:
        """
        LEGACY/DEPRECATED para flujo normal de venta/canje.
        La escritura canónica de movimientos debe ocurrir vía
        LoyaltyApplicationService -> LoyaltyRepository.
        En flujo transaccional debe usarse commit=False para que la atomicidad
        quede controlada por el orquestador superior.

        Registra un movimiento en loyalty_ledger (tabla unificada Fase 2).
        tipo: 'acumulacion' | 'canje' | 'reversa' | 'ajuste'
        puntos: positivo para acumulacion/ajuste, negativo para canje/reversa.
        """
        try:
            if referencia and self._ledger_exists(cliente_id, tipo, referencia):
                return True
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
            if commit:
                try:
                    self.db.commit()
                except Exception:
                    pass
            return True
        except Exception as exc:
            logger.debug("registrar_en_ledger: %s", exc)
            return False

    def _ledger_exists(self, cliente_id: int, tipo: str, referencia: str) -> bool:
        try:
            row = self.db.execute(
                "SELECT 1 FROM loyalty_ledger WHERE cliente_id=? AND tipo=? AND referencia=? LIMIT 1",
                (cliente_id, tipo, str(referencia)),
            ).fetchone()
            return bool(row)
        except Exception:
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
            ref = str(referencia or "")
            app_res = self._app.reverse_redemption(
                cliente_id=int(cliente_id),
                venta_id=ref,
                puntos=int(puntos_canjeados),
                sucursal_id=self.sucursal_id,
                usuario=str(usuario or ""),
            )
            if not app_res.get("ok", False):
                return {"ok": False, "error": app_res.get("error", "reversa_no_aplicada")}
            is_idempotent = bool(app_res.get("idempotent"))
            if not is_idempotent:
                # Ajustar pasivo financiero como bitácora auxiliar
                self._registrar_pasivo(puntos_canjeados, referencia, "reversa", commit=False)
                self._publish_loyalty_fin_event("LOYALTY_POINTS_REVERSED", cliente_id, puntos_canjeados, referencia, usuario)
            nuevo_saldo = int(app_res.get("saldo", self.saldo(cliente_id)))
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



    # ── API pública para UI (sin acceso a _app.repo) ───────────────────────
    def get_referral_config(self) -> dict:
        return self._app.repo.get_referral_config()

    def save_referral_config(self, referidor: int, referido: int, max_mensual: int) -> None:
        self._app.repo.save_referral_config(referidor, referido, max_mensual)
        try:
            self.db.commit()
        except Exception:
            pass

    def list_referrals(self, limit: int = 50):
        return self._app.repo.list_referrals(limit=limit)

    def get_birthday_config(self) -> dict:
        repo = self._app.repo
        return {
            "cumple_bono_estrellas": repo.get_config_value('cumple_bono_estrellas', '100'),
            "cumple_mensaje_wa": repo.get_config_value('cumple_mensaje_wa', '🎂 ¡Feliz cumpleaños {nombre}! Te regalamos {puntos} estrellas.'),
        }

    def save_birthday_config(self, bono_estrellas: int, mensaje_wa: str) -> None:
        self._app.repo.set_config_values({
            'cumple_bono_estrellas': str(int(bono_estrellas)),
            'cumple_mensaje_wa': str(mensaje_wa or ''),
        })
        try:
            self.db.commit()
        except Exception:
            pass

    def list_upcoming_birthdays(self, days: int = 7):
        return self._app.repo.list_upcoming_birthdays(days)

    def list_at_risk_customers(self, days_without_sale: int = 30, limit: int = 200):
        return self._app.repo.list_at_risk_customers(days_without_sale=days_without_sale, limit=limit)

    def get_dashboard_kpis(self) -> dict:
        raw = self._app.repo.get_dashboard_kpis() or {}
        kpis = {k: raw.get(k, 0) for k in self.DASHBOARD_KPI_KEYS}
        # Normalización de tipos para contrato estable de UI.
        int_keys = (
            "clientes_con_puntos",
            "puntos_activos",
            "puntos_emitidos_mes",
            "puntos_canjeados_mes",
            "cumples_7_dias",
            "clientes_en_riesgo",
            "rifas_activas",
        )
        for key in int_keys:
            try:
                kpis[key] = int(kpis[key] or 0)
            except Exception:
                kpis[key] = 0
        try:
            kpis["pasivo_operativo"] = float(kpis["pasivo_operativo"] or 0.0)
        except Exception:
            kpis["pasivo_operativo"] = 0.0
        return kpis

    def list_raffles(self, limit: int = 50):
        return self._app.repo.list_raffles(limit=limit)

    def get_raffle_summary(self) -> dict:
        summary = self._app.repo.get_raffle_summary()
        return summary

    def list_raffle_tickets(self, raffle_id: int, limit: int = 200) -> list[dict]:
        return self._app.repo.list_tickets_by_raffle(raffle_id, limit=limit)

    def resolve_scan(self, codigo: str) -> dict:
        """Resuelve códigos de tarjeta/cliente sin SQL desde UI."""
        code = str(codigo or "").strip()
        if not code:
            return {"found": False, "type": "empty"}
        try:
            from repositories.loyalty_repository import LoyaltyRepository
            repo = LoyaltyRepository(self.db)
            card = repo.get_card_by_code(code)
            if card and card.get("cliente_id"):
                cid = int(card["cliente_id"])
                row = self.db.execute(
                    "SELECT id, nombre, COALESCE(telefono,'') AS telefono FROM clientes WHERE id=? LIMIT 1",
                    (cid,),
                ).fetchone()
                if row:
                    nombre = row[1] if isinstance(row, tuple) else row["nombre"]
                    tel = row[2] if isinstance(row, tuple) else row["telefono"]
                    return {
                        "found": True,
                        "type": "tarjeta",
                        "cliente_id": cid,
                        "nombre": nombre,
                        "telefono": tel,
                        "nivel": card.get("nivel", "Bronce"),
                        "puntos": self.saldo(cid),
                        "card_code": code,
                    }
            return {"found": False, "type": "tarjeta", "card_code": code}
        except Exception:
            return {"found": False, "type": "tarjeta", "card_code": code}

    def _get_cajero_id(self, nombre: str) -> int:
        try:
            row = self.db.execute(
                "SELECT id FROM usuarios WHERE nombre=? LIMIT 1",
                (nombre,)).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _cfg(self, key: str, default: str = "") -> str:
        """Lee config canónica loyalty_* con fallback temporal a growth_*.

        Orden: loyalty_* -> growth_* -> default.
        """
        aliases = {
            "loyalty_expiry_dias": "growth_expiry_dias",
            "loyalty_otp_umbral": "growth_otp_umbral",
            "loyalty_valor_estrella": "growth_costo_estrella",
            "loyalty_max_pct_canje": "growth_cap_pct",
        }
        keys = [key]
        if key in aliases:
            keys.append(aliases[key])
        try:
            for k in keys:
                row = self.db.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?",
                    (k,),
                ).fetchone()
                val = row[0] if row and row[0] else None
                if val not in (None, ""):
                    return val
            return default
        except Exception:
            return default
    # ── Rifas/Sorteos: validadores financieros (FASE 3) ─────────────────────
    @staticmethod
    def validate_raffle_budget(raffle: Dict[str, Any]) -> None:
        presupuesto = float(raffle.get("presupuesto_maximo") or 0)
        premio_estimado = float(raffle.get("premio_costo_estimado") or 0)
        monto_ticket = float(raffle.get("monto_por_boleto") or 0)
        ventas_objetivo = float(raffle.get("ventas_objetivo") or presupuesto)
        fecha_inicio = str(raffle.get("fecha_inicio") or "").strip()
        fecha_fin = str(raffle.get("fecha_fin") or "").strip()

        if presupuesto <= 0:
            raise ValueError("presupuesto_maximo debe ser > 0")
        if premio_estimado <= 0:
            raise ValueError("premio_costo_estimado debe ser > 0")
        if premio_estimado > presupuesto:
            raise ValueError("premio_costo_estimado excede presupuesto_maximo")
        if monto_ticket <= 0:
            raise ValueError("monto_por_boleto debe ser > 0")
        if ventas_objetivo < presupuesto:
            raise ValueError("ventas_objetivo debe ser >= presupuesto_maximo")
        if fecha_inicio and fecha_fin and not (fecha_inicio < fecha_fin):
            raise ValueError("fecha_inicio debe ser menor que fecha_fin")

    @staticmethod
    def validate_raffle_activation(raffle: Dict[str, Any]) -> None:
        status = str(raffle.get("financial_status") or "")
        if status not in ("presupuestada", "reservada"):
            raise ValueError("financial_status inválido para activar")
        if status != "reservada":
            raise ValueError("No activar rifa sin presupuesto reservado")

    @staticmethod
    def validate_ticket_generation(raffle: Dict[str, Any], sale: Dict[str, Any]) -> None:
        if str(raffle.get("estado") or "") != "activa":
            raise ValueError("no generar boletos si la rifa no está activa")
        if not sale.get("venta_id"):
            raise ValueError("no generar boletos sin venta válida")

    @staticmethod
    def validate_winner_selection(raffle: Dict[str, Any]) -> None:
        if str(raffle.get("estado") or "") != "cerrada":
            raise ValueError("no seleccionar ganador si la rifa no está cerrada")

    @staticmethod
    def validate_prize_delivery(raffle: Dict[str, Any], winner: Dict[str, Any]) -> None:
        if str(raffle.get("financial_status") or "") not in ("reservada", "liquidada"):
            raise ValueError("no entregar premio sin reserva financiera")
        if not winner:
            raise ValueError("ganador inválido")

    def create_raffle(self, data: Dict[str, Any]) -> int:
        self.validate_raffle_budget(data)
        raffle_id = self._app.repo.create_raffle(data)
        if self._bus:
            self._bus.publish(
                "RAFFLE_CREATED",
                {
                    "raffle_id": raffle_id,
                    "referencia": f"raffle:{raffle_id}",
                    "sucursal_id": data.get("sucursal_id", self.sucursal_id),
                },
                async_=True,
            )
        return int(raffle_id)
    def create_raffle_with_rules(self, data: Dict[str, Any], rules: Dict[str, Any], prizes: list[dict], eligibility: Dict[str, Any]) -> int:
        self.validate_raffle_budget(data)
        return int(self._app.repo.create_raffle_with_rules(data, rules, prizes, eligibility))

    def reserve_raffle_budget(self, raffle_id: int, monto: float, usuario: str, referencia: str) -> bool:
        ok = self._app.repo.reserve_raffle_budget(raffle_id, monto, usuario, referencia)
        if ok and self._bus:
            self._bus.publish(
                "RAFFLE_BUDGET_RESERVED",
                {
                    "raffle_id": int(raffle_id),
                    "monto": float(monto),
                    "usuario": str(usuario or ""),
                    "referencia": str(referencia or ""),
                    "sucursal_id": self.sucursal_id,
                },
                async_=True,
            )
        return bool(ok)

    def activate_raffle(self, raffle_id: int, usuario: str) -> bool:
        self.validate_raffle_ready_to_activate(raffle_id)
        ok = bool(self._app.repo.activate_raffle(raffle_id, usuario))
        if ok and self._bus:
            self._bus.publish("RAFFLE_ACTIVATED", {"raffle_id": int(raffle_id), "usuario": str(usuario or ""), "sucursal_id": self.sucursal_id}, async_=True)
        return ok


    def close_raffle(self, raffle_id: int, usuario: str) -> bool:
        ok = bool(self._app.repo.close_raffle(raffle_id, usuario))
        if ok and self._bus:
            self._bus.publish(
                "RAFFLE_CLOSED",
                {"raffle_id": int(raffle_id), "usuario": str(usuario or ""), "sucursal_id": self.sucursal_id},
                async_=True,
            )
        return ok

    def generate_tickets_for_sale(
        self,
        raffle_id: int,
        venta_id: int,
        cliente_id: int,
        folio_venta: str,
        monto_base: float,
        sucursal_id: int,
    ) -> list[str]:
        raffle = self._app.repo.get_raffle_by_id(raffle_id)
        self.validate_ticket_generation(raffle, {"venta_id": venta_id})
        tickets = self._app.repo.generate_tickets_for_sale(
            raffle_id, venta_id, cliente_id, folio_venta, monto_base, sucursal_id
        )
        if tickets and self._bus:
            for ticket in tickets:
                self._bus.publish(
                    "RAFFLE_TICKET_GRANTED",
                    {
                        "raffle_id": int(raffle_id),
                        "venta_id": int(venta_id),
                        "cliente_id": int(cliente_id or 0),
                        "numero_boleto": ticket,
                        "sucursal_id": int(sucursal_id or self.sucursal_id),
                    },
                    async_=True,
                )
        return tickets

    def evaluate_raffle_sale_eligibility(self, raffle_id: int, sale_context: Dict[str, Any]) -> Dict[str, Any]:
        raffle = self._app.repo.get_raffle_by_id(raffle_id)
        rules = self._app.repo.get_raffle_rules(raffle_id)
        dt = str(sale_context.get("sale_datetime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        try:
            dt_obj = datetime.fromisoformat(dt.replace("Z", ""))
        except Exception:
            dt_obj = datetime.now()
        if str(raffle.get("estado") or "") != "activa" or str(raffle.get("financial_status") or "") != "reservada":
            return {"eligible": False, "reason": "raffle_not_active"}
        if (raffle.get("fecha_inicio") and dt < str(raffle.get("fecha_inicio"))) or (raffle.get("fecha_fin") and dt > str(raffle.get("fecha_fin"))):
            return {"eligible": False, "reason": "date_out_of_range"}
        if int(rules.get("requires_registered_customer") or 0) == 1 and not sale_context.get("cliente_id"):
            return {"eligible": False, "reason": "registered_required"}
        if float(sale_context.get("total") or 0) < float(rules.get("min_sale_amount") or 0):
            return {"eligible": False, "reason": "min_sale"}
        if int(sale_context.get("sucursal_id") or 0) != int(raffle.get("sucursal_id") or 0):
            return {"eligible": False, "reason": "branch_not_allowed"}
        allowed_payments = _csv_tokens(rules.get("allowed_payment_methods"))
        if allowed_payments and str(sale_context.get("payment_method") or "").strip().lower() not in allowed_payments:
            return {"eligible": False, "reason": "payment_not_allowed"}
        allowed_weekdays = _csv_tokens(rules.get("allowed_weekdays"))
        if allowed_weekdays and str(dt_obj.weekday()) not in allowed_weekdays and dt_obj.strftime("%A").lower() not in allowed_weekdays:
            return {"eligible": False, "reason": "weekday_not_allowed"}
        start_time = str(rules.get("start_time") or "").strip()
        end_time = str(rules.get("end_time") or "").strip()
        if start_time and end_time:
            now_hm = dt_obj.strftime("%H:%M")
            if not (start_time <= now_hm <= end_time):
                return {"eligible": False, "reason": "time_not_allowed"}
        items = sale_context.get("items") or []
        if items:
            r = self.db.execute("SELECT product_id FROM raffle_eligible_products WHERE raffle_id=?", (int(raffle_id),)).fetchall()
            allowed_products = {int((x[0] if isinstance(x, tuple) else x["product_id"]) or 0) for x in r}
            r = self.db.execute("SELECT category_id FROM raffle_eligible_categories WHERE raffle_id=?", (int(raffle_id),)).fetchall()
            allowed_categories = {int((x[0] if isinstance(x, tuple) else x["category_id"]) or 0) for x in r}
            if allowed_products or allowed_categories:
                ok_item = False
                for it in items:
                    pid = int((it.get("product_id") or it.get("id") or 0) or 0)
                    cid = int((it.get("category_id") or it.get("categoria_id") or 0) or 0)
                    if (allowed_products and pid in allowed_products) or (allowed_categories and cid in allowed_categories):
                        ok_item = True
                        break
                if not ok_item:
                    return {"eligible": False, "reason": "products_not_allowed"}
        return {"eligible": True, "raffle": raffle, "rules": rules}

    def calculate_raffle_tickets_count(self, raffle: Dict[str, Any], rules: Dict[str, Any], sale_context: Dict[str, Any]) -> int:
        strategy = str(rules.get("ticket_strategy") or "per_amount")
        if strategy == "per_sale":
            count = int(rules.get("tickets_per_sale") or 1)
        elif strategy == "fixed":
            count = int(rules.get("tickets_per_sale") or 1)
        else:
            amount_per_ticket = float(rules.get("amount_per_ticket") or raffle.get("monto_por_boleto") or 0)
            count = max(0, int(float(sale_context.get("total") or 0) / amount_per_ticket)) if amount_per_ticket > 0 else 0
        mps = int(rules.get("max_tickets_per_sale") or 0)
        return min(count, mps) if mps > 0 else count

    def validate_raffle_ready_to_activate(self, raffle_id: int) -> None:
        raffle = self._app.repo.get_raffle_by_id(raffle_id)
        rules = self._app.repo.get_raffle_rules(raffle_id)
        prizes = self._app.repo.list_raffle_prizes(raffle_id)
        if not raffle.get("fecha_inicio") or not raffle.get("fecha_fin") or not prizes or not rules:
            raise ValueError("No activar rifa sin fecha válida, premio, presupuesto y reglas")
        self.validate_raffle_activation(raffle)

    def process_raffles_for_sale(self, venta_id: int, cliente_id: int, folio: str, total: float, sucursal_id: int, payment_method=None, items=None, sale_datetime=None) -> list[dict]:
        tickets_snapshot: list[dict] = []
        dt = str(sale_datetime or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for raffle in (self._app.repo.get_active_raffles_for_sale(int(sucursal_id), dt) or []):
            rid = int(raffle.get("id") or 0)
            eval_result = self.evaluate_raffle_sale_eligibility(rid, {"venta_id": venta_id, "cliente_id": cliente_id, "total": total, "sucursal_id": sucursal_id, "payment_method": payment_method, "items": items or [], "sale_datetime": dt})
            if not eval_result.get("eligible"):
                continue
            rules = eval_result.get("rules") or {}
            max_customer = int(rules.get("max_tickets_per_customer") or 0)
            current = self._app.repo.count_customer_tickets(rid, int(cliente_id or 0)) if cliente_id else 0
            count = self.calculate_raffle_tickets_count(raffle, rules, {"total": total})
            if max_customer > 0:
                count = max(0, min(count, max_customer - current))
            if count <= 0:
                continue
            existing_sale_tickets = [
                t for t in self._app.repo.list_raffle_tickets(rid, limit=500)
                if int(t.get("venta_id") or 0) == int(venta_id)
            ]
            if existing_sale_tickets:
                continue
            tickets = self.generate_tickets_for_sale(rid, int(venta_id), int(cliente_id or 0), str(folio or ""), float(total or 0), int(sucursal_id or self.sucursal_id))[:count]
            for t in tickets:
                tickets_snapshot.append({"raffle": str(raffle.get("nombre") or f"Rifa {rid}"), "numero_boleto": t})
        return tickets_snapshot

    def cancel_tickets_for_sale(self, venta_id: int, reason: str) -> int:
        cancelled = int(self._app.repo.cancel_tickets_for_sale(venta_id, reason) or 0)
        if cancelled > 0 and self._bus:
            self._bus.publish(
                "RAFFLE_TICKET_CANCELLED",
                {"venta_id": int(venta_id), "cancelled": cancelled, "reason": str(reason or ""), "sucursal_id": self.sucursal_id},
                async_=True,
            )
        return cancelled

    def select_winner(self, raffle_id: int, usuario: str, random_seed: str | None = None, prize_id: int | None = None) -> dict:
        raffle = self._app.repo.get_raffle_by_id(raffle_id)
        self.validate_winner_selection(raffle)
        winner = self._app.repo.select_winner(raffle_id, usuario, random_seed=random_seed, prize_id=prize_id)
        if winner and self._bus:
            payload = dict(winner)
            payload.update({"usuario": str(usuario or ""), "sucursal_id": self.sucursal_id})
            self._bus.publish("RAFFLE_WINNER_SELECTED", payload, async_=True)
        return winner

    def mark_prize_delivered(self, winner_id: int, usuario: str, costo_real: float, referencia: str = "") -> bool:
        winner = self._app.repo.get_winner_by_id(winner_id)
        if not winner:
            return False
        raffle = self._app.repo.get_raffle_by_id(int(winner.get("raffle_id") or 0))
        self.validate_prize_delivery(raffle, winner)
        if not self._app.repo.has_raffle_budget_reserve(int(winner.get("raffle_id") or 0)):
            raise ValueError("no entregar premio sin reserva financiera")
        ok = bool(self._app.repo.mark_prize_delivered(winner_id, usuario, costo_real, referencia=referencia))
        if ok and self._bus:
            ref = str(referencia or f"winner:{winner_id}:deliver")
            self._bus.publish(
                "RAFFLE_PRIZE_DELIVERED",
                {
                    "raffle_id": int(winner.get("raffle_id") or 0),
                    "winner_id": int(winner_id),
                    "usuario": str(usuario or ""),
                    "monto": float(costo_real or 0),
                    "referencia": ref,
                    "sucursal_id": self.sucursal_id,
                },
                async_=True,
            )
        return ok

    def release_raffle_budget(self, raffle_id: int, monto: float, usuario: str, referencia: str) -> bool:
        if not referencia:
            raise ValueError("referencia requerida")
        ok = bool(self._app.repo.release_raffle_budget(raffle_id, monto, usuario, referencia))
        if ok and self._bus:
            self._bus.publish(
                "RAFFLE_BUDGET_RELEASED",
                {
                    "raffle_id": int(raffle_id),
                    "monto": abs(float(monto or 0)),
                    "usuario": str(usuario or ""),
                    "referencia": str(referencia),
                    "sucursal_id": self.sucursal_id,
                },
                async_=True,
            )
        return ok

    DASHBOARD_KPI_KEYS = (
        "clientes_con_puntos",
        "puntos_activos",
        "pasivo_operativo",
        "puntos_emitidos_mes",
        "puntos_canjeados_mes",
        "cumples_7_dias",
        "clientes_en_riesgo",
        "rifas_activas",
    )
