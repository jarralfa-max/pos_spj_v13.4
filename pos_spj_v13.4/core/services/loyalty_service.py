# core/services/loyalty_service.py — SPJ POS v13.30 — FASE 2
"""
LoyaltyService — servicio ÚNICO de fidelización.
Usa LoyaltyApplicationService/Repository, conecta al flujo de cobro y registra pasivo financiero.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("spj.loyalty")


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
