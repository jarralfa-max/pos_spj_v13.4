# core/events/wiring.py — SPJ POS v13.3
"""
Cableado central de handlers al EventBus.

Extraído de AppContainer._wire_event_bus() para:
  1. Reducir el tamaño del AppContainer
  2. Hacer explícitas las dependencias entre eventos y handlers
  3. Permitir testing independiente de cada handler

Se ejecuta una vez desde AppContainer.__init__() al final:
    from core.events.wiring import wire_all
    wire_all(self)

Convención de prioridades:
  100+  Sync (CRÍTICO — debe ejecutarse primero y de forma síncrona)
   50   Lógica de negocio (fidelidad, comisiones, etc.)
   30   Auditoría
   10   Notificaciones (soft-fail, no crítico)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.app_container import AppContainer

logger = logging.getLogger("spj.events.wiring")




def _wire_loyalty_finance_handlers(bus, container) -> None:
    """Handler financiero único de fidelidad (FASE 5)."""
    fs = getattr(container, "finance_service", None)
    db = getattr(container, "db", None)
    if not fs:
        return
    from core.events.event_bus import (
        LOYALTY_POINTS_EARNED, LOYALTY_POINTS_REDEEMED,
        LOYALTY_POINTS_EXPIRED, LOYALTY_POINTS_REVERSED,
    )

    def _handle(data: dict, kind: str) -> None:
        try:
            puntos = int(data.get("puntos", 0))
            if puntos == 0:
                return
            valor = 0.10
            if db is not None:
                try:
                    r = db.execute("SELECT valor FROM configuraciones WHERE clave='loyalty_valor_estrella'").fetchone()
                    if r:
                        valor = float(r[0] if isinstance(r, tuple) else r["valor"])
                except Exception:
                    pass
            monto = abs(float(puntos)) * float(valor)
            if monto <= 0:
                return
            if kind == "earned":
                debe, haber = "6201-descuentos-fidelizacion", "215.1-pasivo-fidelizacion"
            elif kind in ("redeemed", "expired"):
                debe, haber = "215.1-pasivo-fidelizacion", "401.1-descuento-clientes"
            else:  # reversed
                debe, haber = "401.1-descuento-clientes", "215.1-pasivo-fidelizacion"
            fs.registrar_asiento(
                debe=debe, haber=haber,
                concepto=f"Loyalty {kind} ref={data.get('referencia','')}",
                monto=monto, modulo="loyalty",
                referencia_id=data.get("referencia"),
                sucursal_id=data.get("sucursal_id", 1),
                evento=f"LOYALTY_{kind.upper()}",
                metadata={"cliente_id": data.get("cliente_id"), "puntos": puntos},
            )
        except Exception as e:
            logger.debug("loyalty finance handler %s: %s", kind, e)

    bus.subscribe(LOYALTY_POINTS_EARNED, lambda d: _handle(d, "earned"), priority=60, label="loyalty_fin_earned")
    bus.subscribe(LOYALTY_POINTS_REDEEMED, lambda d: _handle(d, "redeemed"), priority=60, label="loyalty_fin_redeemed")
    bus.subscribe(LOYALTY_POINTS_EXPIRED, lambda d: _handle(d, "expired"), priority=60, label="loyalty_fin_expired")
    bus.subscribe(LOYALTY_POINTS_REVERSED, lambda d: _handle(d, "reversed"), priority=60, label="loyalty_fin_reversed")



def _wire_raffle_finance_handlers(bus, container) -> None:
    """Handler financiero de rifas (FASE 5) con idempotencia por ledger único."""
    fs = getattr(container, "finance_service", None)
    ls = getattr(container, "loyalty_service", None)
    repo = getattr(getattr(ls, "_app", None), "repo", None)
    if not fs or repo is None:
        return

    from core.events.event_bus import (
        RAFFLE_BUDGET_RESERVED,
        RAFFLE_PRIZE_DELIVERED,
        RAFFLE_BUDGET_RELEASED,
    )

    def _post_if_new(data: dict, tipo: str, debe: str, haber: str, concepto: str) -> None:
        try:
            raffle_id = int(data.get("raffle_id") or 0)
            if raffle_id <= 0:
                return
            referencia = str(data.get("referencia") or "").strip()
            if not referencia:
                return
            monto = abs(float(data.get("monto") or 0.0))
            if monto <= 0:
                return
            usuario = str(data.get("usuario") or "sistema")
            sucursal_id = int(data.get("sucursal_id") or 1)

            # Guardia idempotente: UNIQUE(raffle_id, tipo, referencia)
            try:
                repo.db.execute(
                    """
                    INSERT INTO raffle_financial_ledger
                    (raffle_id, tipo, monto, referencia, descripcion, usuario, sucursal_id)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (raffle_id, tipo, monto, referencia, concepto, usuario, sucursal_id),
                )
            except Exception:
                return

            fs.registrar_asiento(
                debe=debe,
                haber=haber,
                concepto=f"{concepto} ref={referencia}",
                monto=monto,
                modulo="raffles",
                referencia_id=referencia,
                sucursal_id=sucursal_id,
                evento=f"RAFFLE_{tipo.upper()}",
                metadata={"raffle_id": raffle_id, "tipo": tipo},
            )
        except Exception as e:
            logger.debug("raffle finance handler %s: %s", tipo, e)

    bus.subscribe(
        RAFFLE_BUDGET_RESERVED,
        lambda d: _post_if_new(
            d,
            "budget_reserved",
            "6201-descuentos-fidelizacion",
            "215.1-pasivo-fidelizacion",
            "Reserva presupuesto rifa",
        ),
        priority=60,
        label="raffle_fin_budget_reserved",
    )
    bus.subscribe(
        RAFFLE_PRIZE_DELIVERED,
        lambda d: _post_if_new(
            d,
            "prize_delivered",
            "215.1-pasivo-fidelizacion",
            "401.1-descuento-clientes",
            "Entrega premio rifa",
        ),
        priority=60,
        label="raffle_fin_prize_delivered",
    )
    bus.subscribe(
        RAFFLE_BUDGET_RELEASED,
        lambda d: _post_if_new(
            d,
            "budget_released",
            "215.1-pasivo-fidelizacion",
            "401.1-descuento-clientes",
            "Liberación reserva rifa",
        ),
        priority=60,
        label="raffle_fin_budget_released",
    )


def _wire_loyalty_domain_handlers(bus, container) -> None:
    """Handlers de dominio de fidelidad (FASE 7) con prioridades explícitas."""
    db = getattr(container, "db", None)
    if db is None:
        return

    from core.events.event_bus import (
        LOYALTY_CARD_ASSIGNED,
        LOYALTY_CARD_BLOCKED,
        LOYALTY_REFERRAL_REWARDED,
        LOYALTY_BIRTHDAY_REWARD_ISSUED,
        LOYALTY_FRAUD_BLOCKED,
    )

    def _audit(evento: str, data: dict) -> None:
        try:
            db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (
                    evento,
                    "FIDELIDAD",
                    "loyalty_event",
                    str(data.get("referencia") or data.get("card_code") or data.get("cliente_id") or ""),
                    str(data.get("usuario", "sistema")),
                    int(data.get("sucursal_id", 1) or 1),
                    str(data),
                ),
            )
            try:
                db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("loyalty audit %s: %s", evento, e)

    bus.subscribe(LOYALTY_CARD_ASSIGNED, lambda d: _audit("LOYALTY_CARD_ASSIGNED", d), priority=40, label="loyalty_audit_card_assigned")
    bus.subscribe(LOYALTY_CARD_BLOCKED, lambda d: _audit("LOYALTY_CARD_BLOCKED", d), priority=40, label="loyalty_audit_card_blocked")
    bus.subscribe(LOYALTY_REFERRAL_REWARDED, lambda d: _audit("LOYALTY_REFERRAL_REWARDED", d), priority=40, label="loyalty_audit_referral_rewarded")
    bus.subscribe(LOYALTY_BIRTHDAY_REWARD_ISSUED, lambda d: _audit("LOYALTY_BIRTHDAY_REWARD_ISSUED", d), priority=40, label="loyalty_audit_birthday_reward")
    bus.subscribe(LOYALTY_FRAUD_BLOCKED, lambda d: _audit("LOYALTY_FRAUD_BLOCKED", d), priority=90, label="loyalty_audit_fraud_blocked")
def wire_all(container: "AppContainer") -> None:
    """Registra todos los handlers del EventBus."""
    from core.events.event_bus import get_bus

    bus = get_bus()

    _wire_venta(bus, container)
    _wire_pedido(bus, container)
    _wire_inventario(bus, container)
    _wire_produccion(bus, container)

    # FASE 12: handlers cruzados para servicios inteligentes
    _wire_alertas(bus, container)
    _wire_finanzas(bus, container)
    _wire_rrhh(bus, container)
    _wire_precio_margen(bus, container)

    # FASE WA: handlers para orquestación WhatsApp ↔ ERP
    _wire_wa_events(bus, container)

    # v13.4: handlers financieros para merma y ajuste stock en merma
    _wire_merma_financiero(bus, container)
    _wire_merma_inventario(bus, container)
    _wire_flujos_criticos(bus, container)

    # Phase 1: SALE_ITEMS_PROCESS — inventory + finance handlers (sync, inside SAVEPOINT)
    _wire_sale_handlers(bus, container)
    _wire_loyalty_finance_handlers(bus, container)
    _wire_loyalty_domain_handlers(bus, container)
    _wire_raffle_finance_handlers(bus, container)

    # Phase 3: PRODUCTION_ITEMS_PROCESS — inventory handler (sync, inside transaction)
    _wire_production_items_handlers(bus, container)

    # Phase 4: PURCHASE_ITEMS_PROCESS + PURCHASE_CREATED — inventory + finance handlers
    _wire_purchase_items_handlers(bus, container)

    # Phase 5: TRANSFER_ITEMS_PROCESS — multi-sucursal OUT/IN inventory handler
    _wire_transfer_items_handlers(bus, container)

    # v13.5: Delivery weight adjustments + inventory reservations
    _wire_delivery_handlers(bus, container)
    _wire_legacy_delivery_event_bridge(bus, container)

    # v13.30: Delivery lifecycle + inventory commit + driver settlement + notifications
    _wire_delivery_lifecycle_handlers(bus, container)
    _wire_inventory_commit_handler(bus, container)
    _wire_driver_settlement_handler(bus, container)
    _wire_notification_handler(bus, container)

    # migración 083: trazabilidad financiera end-to-end (priority=20, post-commit)
    _wire_financial_trace_handlers(bus, container)

    logger.info("EventBus wiring completado — %d eventos activos",
                len(bus.registered_events()))


def _wire_flujos_criticos(bus, container) -> None:
    """
    DEPRECATED HANDLERS REMOVED — 2026-05-08 financial-core audit.

    Previously subscribed:
      - _compra_stock   on COMPRA_REGISTRADA: caused double inventory-IN because
        PurchaseInventoryHandler (Phase 4) already handles stock via PURCHASE_ITEMS_PROCESS.
      - _compra_egreso  on COMPRA_REGISTRADA (= PURCHASE_CREATED alias): caused double
        GL posting because PurchaseFinanceHandler already posts the asiento via PURCHASE_CREATED.
      - _merma_perdida  on MERMA_CREATED: caused double GL posting because
        _wire_merma_financiero already calls registrar_asiento() with explicit debe/haber.

    All three flows are now handled exclusively by their Phase handlers:
      - Purchase inventory : PurchaseInventoryHandler  (PURCHASE_ITEMS_PROCESS, priority=100)
      - Purchase GL        : PurchaseFinanceHandler     (PURCHASE_CREATED,       priority=80)
      - Merma GL           : _wire_merma_financiero     (MERMA_CREATED,          priority=50)
      - Merma stock        : _wire_merma_inventario     (MERMA_CREATED,          priority=80)
    """
    pass  # No active subscriptions — kept as named function for clarity in wire_all()


# ── VENTA_COMPLETADA ──────────────────────────────────────────────────────────

def _wire_venta(bus, container) -> None:
    from core.events.event_bus import VENTA_COMPLETADA, VENTA_CANCELADA

    # Prioridad 100: Sync (CRÍTICO)
    def _sync_venta(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="VENTA_COMPLETADA",
                entidad="ventas",
                entidad_id=data.get("venta_id"),
                payload=data.get("data", data),
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "Sistema"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.error("sync_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _sync_venta,
                  priority=100, label="sync_venta")

    # Prioridad 50: Fidelidad
    def _loyalty_venta(data: dict) -> None:
        if data.get("loyalty_already_processed"):
            return
        cliente_id = data.get("cliente_id")
        if not cliente_id:
            return
        try:
            ls = getattr(container, "loyalty_service", None)
            if ls:
                ls.process_loyalty_for_sale(
                    client_id=cliente_id,
                    total_sale=float(data.get("total", 0)),
                    branch_id=data.get("sucursal_id", 1),
                    venta_id=data.get("venta_id"),
                    usuario=str(data.get("usuario", "Sistema")),
                )
        except Exception as e:
            logger.warning("loyalty_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _loyalty_venta,
                  priority=50, label="loyalty_venta")

    def _raffles_venta(data: dict) -> None:
        if data.get("raffle_already_processed"):
            return
        ls = getattr(container, "loyalty_service", None)
        if not ls:
            return
        try:
            snapshot = ls.process_raffles_for_sale(
                venta_id=int(data.get("venta_id") or 0),
                cliente_id=int(data.get("cliente_id") or 0),
                folio=str(data.get("folio") or ""),
                total=float(data.get("total") or 0),
                sucursal_id=int(data.get("sucursal_id") or 1),
                payment_method=str(data.get("payment_method") or ""),
                items=list(data.get("items") or []),
                sale_datetime=str(data.get("sale_datetime") or ""),
            )
            data["raffle_tickets_snapshot"] = snapshot
        except Exception as e:
            logger.warning("raffles_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _raffles_venta,
                  priority=49, label="raffles_venta")

    # Prioridad 30: Auditoría
    def _audit_venta(data: dict) -> None:
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('COMPLETADA','VENTAS','ventas',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("usuario", "cajero"),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio', '')} Total=${float(data.get('total', 0)):.2f}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_venta handler: %s", e)

    bus.subscribe(VENTA_COMPLETADA, _audit_venta,
                  priority=30, label="audit_venta")

    # Prioridad 20: Treasury management ledger (post-commit, async)
    # Deferred payment methods (credit, MercadoPago) are excluded — income is
    # recorded only after explicit confirmation (webhook / cobro manual).
    def _treasury_venta(data: dict) -> None:
        from core.services.payment_normalization import is_deferred_payment
        forma_pago = str(data.get("payment_method", data.get("forma_pago", "")))
        if is_deferred_payment(forma_pago):
            return
        total = float(data.get("total", 0))
        if total <= 0:
            return
        try:
            ts = getattr(container, "treasury_service", None)
            if ts and getattr(ts, "enabled", False):
                ts.registrar_ingreso(
                    categoria  = "venta",
                    concepto   = f"Venta {data.get('folio', data.get('venta_id', ''))}",
                    monto      = total,
                    sucursal_id= int(data.get("sucursal_id", 1)),
                    referencia = str(data.get("folio", "")),
                    usuario    = str(data.get("usuario", "sistema")),
                )
        except Exception as _te:
            logger.debug("treasury_venta handler: %s", _te)

    bus.subscribe(VENTA_COMPLETADA, _treasury_venta,
                  priority=20, label="treasury_venta")

    # VENTA_CANCELADA → GL reversal (post-commit, async — sale already cancelled)
    fs = getattr(container, "finance_service", None)
    db = getattr(container, "db", None)
    if fs and db:
        from core.events.handlers.finance_handler import SaleCancelledFinanceHandler
        cancel_handler = SaleCancelledFinanceHandler(db_conn=db, finance_service=fs)
        bus.subscribe(VENTA_CANCELADA, cancel_handler.handle,
                      priority=50, label="sale_cancelled_reversal")
        logger.debug("Registered SaleCancelledFinanceHandler on %s", VENTA_CANCELADA)

    def _raffles_cancel(data: dict) -> None:
        ls = getattr(container, "loyalty_service", None)
        if not ls:
            return
        try:
            ls.cancel_tickets_for_sale(int(data.get("venta_id") or 0), str(data.get("motivo") or "cancelación de venta"))
        except Exception as e:
            logger.warning("raffles_cancel handler: %s", e)

    bus.subscribe(VENTA_CANCELADA, _raffles_cancel,
                  priority=49, label="raffles_cancel")


# ── PEDIDO_NUEVO ──────────────────────────────────────────────────────────────

def _wire_pedido(bus, container) -> None:
    from core.events.event_bus import PEDIDO_NUEVO

    def _sync_pedido(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="PEDIDO_NUEVO",
                entidad="pedidos_whatsapp",
                entidad_id=data.get("pedido_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("telefono", "bot"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.error("sync_pedido handler: %s", e)

    bus.subscribe(PEDIDO_NUEVO, _sync_pedido,
                  priority=100, label="sync_pedido")

    def _audit_pedido(data: dict) -> None:
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('NUEVO','PEDIDOS_WA','pedidos_whatsapp',?,?,?,?,datetime('now'))",
                (
                    data.get("pedido_id"),
                    data.get("telefono", "bot"),
                    data.get("sucursal_id", 1),
                    f"Total=${float(data.get('total', 0)):.2f} #{data.get('numero', '')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_pedido handler: %s", e)

    bus.subscribe(PEDIDO_NUEVO, _audit_pedido,
                  priority=30, label="audit_pedido")


# ── INVENTARIO ────────────────────────────────────────────────────────────────

def _wire_inventario(bus, container) -> None:
    from core.events.event_bus import STOCK_BAJO_MINIMO, AJUSTE_INVENTARIO

    def _on_stock_bajo(data: dict) -> None:
        logger.warning(
            "Stock bajo: producto=%s sucursal=%s stock=%.3f minimo=%.3f",
            data.get("product_id"),
            data.get("sucursal_id"),
            data.get("stock_actual", 0),
            data.get("stock_minimo", 0),
        )
        # Notificar si el servicio está disponible
        try:
            ns = getattr(container, "notification_service", None)
            if ns:
                ns.notificar_stock_bajo(
                    [data], sucursal_id=data.get("sucursal_id", 1)
                )
        except Exception:
            pass

    bus.subscribe(STOCK_BAJO_MINIMO, _on_stock_bajo,
                  priority=50, label="log_stock_bajo")

    # Sync para ajustes de inventario
    def _sync_ajuste(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="AJUSTE_INVENTARIO",
                entidad="movimientos_inventario",
                entidad_id=data.get("movimiento_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "Sistema"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.debug("sync_ajuste handler: %s", e)

    bus.subscribe(AJUSTE_INVENTARIO, _sync_ajuste,
                  priority=100, label="sync_ajuste")


# ── PRODUCCIÓN ────────────────────────────────────────────────────────────────

def _wire_produccion(bus, container) -> None:
    from core.events.event_bus import PRODUCCION_COMPLETADA

    def _sync_produccion(data: dict) -> None:
        try:
            el = getattr(container, "event_logger", None)
            if not el:
                return
            el.registrar(
                tipo="PRODUCCION_COMPLETADA",
                entidad="production_batches",
                entidad_id=data.get("batch_id"),
                payload=data,
                sucursal_id=data.get("sucursal_id", 1),
                usuario=data.get("usuario", "produccion"),
                operation_id=data.get("operation_id", ""),
            )
        except Exception as e:
            logger.debug("sync_produccion handler: %s", e)

    bus.subscribe(PRODUCCION_COMPLETADA, _sync_produccion,
                  priority=100, label="sync_produccion")


# ── ALERT_CRITICAL ────────────────────────────────────────────────────────────

def _wire_alertas(bus, container) -> None:
    from core.events.event_bus import ALERT_CRITICAL

    def _notify_alert_critical(data: dict) -> None:
        """Enruta ALERT_CRITICAL al NotificationService (FASE 12)."""
        severity = data.get("severity", "")
        if severity not in ("high", "critical"):
            return
        try:
            ns = getattr(container, "notification_service", None)
            if ns and hasattr(ns, "notificar_alerta_critica"):
                ns.notificar_alerta_critica(
                    titulo=data.get("title", "Alerta crítica"),
                    mensaje=data.get("message", ""),
                    sucursal_id=data.get("sucursal_id", 1),
                )
        except Exception as e:
            logger.warning("notify_alert_critical: %s", e)

    bus.subscribe(ALERT_CRITICAL, _notify_alert_critical,
                  priority=10, label="notify_alert_critical")


# ── MOVIMIENTO_FINANCIERO ─────────────────────────────────────────────────────

def _wire_finanzas(bus, container) -> None:
    from core.events.event_bus import MOVIMIENTO_FINANCIERO

    def _audit_movimiento(data: dict) -> None:
        """Audita cada movimiento financiero para trazabilidad (FASE 12)."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (
                    data.get("tipo", "MOVIMIENTO"),
                    "TESORERIA",
                    "movimientos_caja",
                    None,
                    data.get("referencia", "sistema"),
                    data.get("sucursal_id", 1),
                    f"Concepto={data.get('concepto','')} Monto=${float(data.get('monto',0)):.2f}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("audit_movimiento handler: %s", e)

    bus.subscribe(MOVIMIENTO_FINANCIERO, _audit_movimiento,
                  priority=30, label="audit_movimiento_financiero")

    _wire_payroll_finance_handlers(bus, container)


def _wire_payroll_finance_handlers(bus, container) -> None:
    """Finanzas consume eventos RRHH de nómina; RRHH no registra OPEX directo."""
    from core.rrhh.events import NOMINA_GENERADA, NOMINA_PAGADA
    from core.events.handlers.finance_handler import PayrollFinanceHandler

    fs = getattr(container, "finance_service", None)
    js = getattr(container, "journal_entry_service", None)
    if not fs and not js:
        return

    handler = PayrollFinanceHandler(finance_service=fs, journal_service=js)
    bus.subscribe(NOMINA_GENERADA, handler.handle_generated,
                  priority=60, label="payroll_finance_generated")
    bus.subscribe(NOMINA_PAGADA, handler.handle_paid,
                  priority=60, label="payroll_finance_paid")


# ── RRHH: EMPLOYEE_OVERWORK / PAYROLL_DUE ────────────────────────────────────

def _wire_rrhh(bus, container) -> None:
    from core.events.event_bus import EMPLOYEE_OVERWORK, PAYROLL_DUE

    def _notify_overwork(data: dict) -> None:
        """Notifica por WhatsApp cuando un empleado supera días consecutivos (FASE 12)."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            tel_row = container.db.execute(
                "SELECT telefono FROM configuraciones WHERE clave='tel_gerente_rrhh' LIMIT 1"
            ).fetchone()
            if not tel_row or not tel_row[0]:
                return
            nombre = data.get("nombre", f"Empleado #{data.get('empleado_id')}")
            dias = data.get("dias_consecutivos", "?")
            msg = (f"RRHH: {nombre} lleva {dias} días consecutivos trabajando. "
                   f"Programar descanso obligatorio (NOM-035).")
            ws.send_message(phone_number=tel_row[0], message=msg)
        except Exception as e:
            logger.debug("notify_overwork: %s", e)

    def _notify_payroll_due(data: dict) -> None:
        """Notifica cuando una nómina está por vencer (FASE 12)."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            tel_row = container.db.execute(
                "SELECT telefono FROM configuraciones WHERE clave='tel_gerente_rrhh' LIMIT 1"
            ).fetchone()
            if not tel_row or not tel_row[0]:
                return
            nombre = data.get("nombre", f"Empleado #{data.get('empleado_id')}")
            dias = data.get("dias_vencimiento", "?")
            msg = f"RRHH: Nómina de {nombre} vence en {dias} días. Procesar pago."
            ws.send_message(phone_number=tel_row[0], message=msg)
        except Exception as e:
            logger.debug("notify_payroll_due: %s", e)

    bus.subscribe(EMPLOYEE_OVERWORK, _notify_overwork,
                  priority=10, label="notify_overwork_wa")
    bus.subscribe(PAYROLL_DUE, _notify_payroll_due,
                  priority=10, label="notify_payroll_due_wa")


# ── PRICE_BELOW_MARGIN ────────────────────────────────────────────────────────

def _wire_precio_margen(bus, container) -> None:
    from core.events.event_bus import PRICE_BELOW_MARGIN

    def _on_price_below_margin(data: dict) -> None:
        """Registra en audit_logs cuando se vende por debajo del margen (FASE 12)."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('PRECIO_BAJO_MARGEN','VENTAS','productos',?,?,?,?,datetime('now'))",
                (
                    data.get("product_id"),
                    data.get("usuario", "cajero"),
                    data.get("sucursal_id", 1),
                    (f"Precio=${float(data.get('precio_venta',0)):.2f} "
                     f"Costo=${float(data.get('costo',0)):.2f} "
                     f"Margen={float(data.get('margen_pct',0)):.1f}%"),
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("price_below_margin handler: %s", e)

    bus.subscribe(PRICE_BELOW_MARGIN, _on_price_below_margin,
                  priority=30, label="audit_price_below_margin")


# ── WA Events (FASE WA) ───────────────────────────────────────────────────────

def _wire_wa_events(bus, container) -> None:
    """
    Conecta eventos del microservicio WA al ERP:
      SALE_CREATED      → audit + BI cache invalidation
      PAYMENT_RECEIVED  → audit + treasury
      PURCHASE_ORDER_CREATED → audit + notificación
    """
    # Importar constantes del bus WA (definidas en erp/events.py del microservicio
    # pero también como strings normales — no necesita importar el módulo WA)
    SALE_CREATED_WA        = "SALE_CREATED"
    PAYMENT_RECEIVED_WA    = "PAYMENT_RECEIVED"
    PURCHASE_ORDER_WA      = "PURCHASE_ORDER_CREATED"
    STAFF_NOTIFICATION_WA  = "STAFF_NOTIFICATION"
    FORECAST_DEMAND_WA     = "FORECAST_DEMAND_UPDATED"

    def _on_sale_created(data: dict) -> None:
        """Registra en audit_logs cuando se crea una venta desde WA."""
        if data.get("canal") != "whatsapp":
            return  # Solo procesar ventas WA (evitar loops con VENTA_COMPLETADA)
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('CREADA','VENTAS_WA','ventas',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("cliente_id", 0),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio','')} Total=${float(data.get('total',0)):.2f} origen={data.get('origen','wa')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
            # Invalidar caché BI (motor único: analytics_engine)
            analytics = getattr(container, "analytics_engine", None)
            if analytics:
                getattr(analytics, "invalidar_cache", lambda *a: None)(
                    data.get("sucursal_id", 1))
        except Exception as e:
            logger.debug("on_sale_created: %s", e)

    def _on_payment_received(data: dict) -> None:
        """Registra el pago recibido en audit + tesorería."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('PAGO_RECIBIDO','WA_PAGOS','anticipos',?,?,?,?,datetime('now'))",
                (
                    data.get("venta_id"),
                    data.get("telefono", "cliente_wa"),
                    data.get("sucursal_id", 1),
                    f"Folio={data.get('folio','')} Monto=${float(data.get('monto',0)):.2f} metodo={data.get('metodo','')}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_payment_received: %s", e)

    def _on_purchase_order(data: dict) -> None:
        """Audita generación automática de OC desde WA."""
        try:
            container.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES('OC_AUTOMATICA','COMPRAS','ordenes_compra',?,?,?,?,datetime('now'))",
                (
                    data.get("oc_id"),
                    "wa_orchestrator",
                    data.get("sucursal_id", 1),
                    f"Producto={data.get('nombre','')} Cant={data.get('cantidad',0)} venta={data.get('venta_id',0)}",
                ),
            )
            try:
                container.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_purchase_order: %s", e)

    def _on_staff_notification(data: dict) -> None:
        """Reenvía notificaciones de staff via WhatsAppService del ERP."""
        try:
            ws = getattr(container, "whatsapp_service", None)
            if not ws:
                return
            phones = data.get("phones", [])
            mensaje = data.get("mensaje", "")
            if not mensaje or not phones:
                return
            for phone in phones[:5]:  # Máximo 5 destinatarios por evento
                try:
                    ws.send_message(phone_number=phone, message=mensaje)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("on_staff_notification: %s", e)

    def _on_forecast_demand(data: dict) -> None:
        """Pasa demanda WA al ForecastService del ERP (SOLO LECTURA — no ejecuta)."""
        try:
            fs = getattr(container, "actionable_forecast", None)
            if fs and hasattr(fs, "registrar_demanda_wa"):
                fs.registrar_demanda_wa(
                    producto_id=data.get("product_id"),
                    cantidad=data.get("demanda_est", 0),
                    periodo=data.get("periodo", ""),
                )
        except Exception as e:
            logger.debug("on_forecast_demand: %s", e)

    bus.subscribe(SALE_CREATED_WA,       _on_sale_created,     priority=30, label="wa_sale_audit")
    bus.subscribe(PAYMENT_RECEIVED_WA,   _on_payment_received, priority=30, label="wa_payment_audit")
    bus.subscribe(PURCHASE_ORDER_WA,     _on_purchase_order,   priority=30, label="wa_oc_audit")
    bus.subscribe(STAFF_NOTIFICATION_WA, _on_staff_notification, priority=10, label="wa_staff_notify")
    bus.subscribe(FORECAST_DEMAND_WA,    _on_forecast_demand,  priority=5,  label="wa_forecast_demand")


# ── v13.4 handlers: MERMA_CREATED + PURCHASE_CREATED ─────────────────────────

def _wire_merma_financiero(bus, container) -> None:
    """
    MERMA_CREATED → asiento contable doble entrada.
    Debita cuenta_mermas, acredita cuenta_inventario.
    Solo se activa si finance_service está disponible en el container.
    """
    from core.events.event_bus import MERMA_CREATED

    def _on_merma_financiero(data: dict) -> None:
        try:
            fs = getattr(container, "finance_service", None)
            if not fs or not hasattr(fs, "registrar_asiento"):
                return
            valor = float(data.get("valor", data.get("costo", 0)))
            if valor <= 0:
                return
            fs.registrar_asiento(
                debe="mermas_y_deterioro",
                haber="inventario_almacen",
                concepto=f"Merma: {data.get('motivo', 'N/A')} — producto {data.get('product_id', '')}",
                monto=abs(valor),
                modulo="merma",
                referencia_id=data.get("merma_id") or data.get("product_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=data.get("sucursal_id", 1),
                evento="MERMA_REGISTRADA",
                metadata={
                    "product_id": data.get("product_id"),
                    "cantidad": data.get("cantidad"),
                    "motivo": data.get("motivo"),
                },
            )
        except Exception as e:
            logger.debug("on_merma_financiero: %s", e)

    bus.subscribe(MERMA_CREATED, _on_merma_financiero,
                  priority=50, label="merma_ledger")


# ── v13.4: MERMA_CREATED → ajuste stock físico ───────────────────────────────

def _wire_merma_inventario(bus, container) -> None:
    """
    MERMA_CREATED → descuenta la cantidad merma del stock físico.
    Complementa _wire_merma_financiero (que solo registra el asiento).
    Solo activo si inventory_service.ajustar_merma está disponible.
    """
    from core.events.event_bus import MERMA_CREATED

    def _on_merma_inventario(data: dict) -> None:
        try:
            inv = getattr(container, "inventory_service", None)
            if not inv or not hasattr(inv, "ajustar_merma"):
                return
            cantidad = float(data.get("cantidad", 0))
            if cantidad <= 0:
                return
            inv.ajustar_merma(
                producto_id=data.get("product_id"),
                cantidad=cantidad,
                branch_id=data.get("sucursal_id", 1),
                referencia_id=str(data.get("merma_id", "MERMA")),
                usuario=data.get("usuario", "sistema"),
            )
        except Exception as e:
            logger.debug("on_merma_inventario: %s", e)

    bus.subscribe(MERMA_CREATED, _on_merma_inventario,
                  priority=80, label="merma_stock")


# ── Phase 1: SALE_ITEMS_PROCESS handlers ─────────────────────────────────────

def _wire_sale_handlers(bus, container) -> None:
    """
    Register SaleInventoryHandler and SaleFinanceHandler on SALE_ITEMS_PROCESS.

    Both handlers run synchronously (async_=False) inside the SAVEPOINT opened by
    SalesService.execute_sale(), so their DB writes are atomic with the sale row.

    Priority order:
      100 — SaleInventoryHandler: deduct stock (must run before finance)
       90 — SaleFinanceHandler:   register cash income
    """
    from core.events.domain_events import SALE_ITEMS_PROCESS
    from core.events.handlers.inventory_handler import SaleInventoryHandler
    from core.events.handlers.finance_handler import SaleFinanceHandler

    inv      = getattr(container, "inventory_service", None)
    fs       = getattr(container, "finance_service", None)
    db       = getattr(container, "db", None)

    if inv:
        inv_handler = SaleInventoryHandler(inventory_service=inv, db=db)
        bus.subscribe(
            SALE_ITEMS_PROCESS,
            inv_handler.handle,
            priority=100,
            label="sale_inventory_deduct",
        )
        logger.debug("Registered SaleInventoryHandler on %s", SALE_ITEMS_PROCESS)

    if fs:
        fin_handler = SaleFinanceHandler(finance_service=fs)
        bus.subscribe(
            SALE_ITEMS_PROCESS,
            fin_handler.handle,
            priority=90,
            label="sale_finance_income",
        )
        logger.debug("Registered SaleFinanceHandler on %s", SALE_ITEMS_PROCESS)

    db = getattr(container, "db", None)
    if fs and db:
        from core.events.handlers.finance_handler import CreditSaleFinanceHandler
        credit_handler = CreditSaleFinanceHandler(db_conn=db, finance_service=fs)
        bus.subscribe(
            SALE_ITEMS_PROCESS,
            credit_handler.handle,
            priority=85,
            label="sale_credit_cxc",
        )
        logger.debug("Registered CreditSaleFinanceHandler on %s", SALE_ITEMS_PROCESS)


# ── Phase 3: PRODUCTION_ITEMS_PROCESS handler ────────────────────────────────

def _wire_production_items_handlers(bus, container) -> None:
    """
    Register ProductionInventoryHandler on PRODUCTION_ITEMS_PROCESS (sync, priority=100)
    and ProductionFinanceHandler on PRODUCCION_COMPLETADA (async, priority=45).
    """
    from core.events.domain_events import PRODUCTION_ITEMS_PROCESS
    from core.events.handlers.production_handler import (
        ProductionInventoryHandler,
        ProductionFinanceHandler,
    )
    from core.services.inventory.unified_inventory_service import UnifiedInventoryService

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_production_items_handlers: no container.db — skipping")
        return

    inv_eng = UnifiedInventoryService(conn=db, sucursal_id=1, usuario="produccion")
    handler = ProductionInventoryHandler(inventory_engine=inv_eng)
    bus.subscribe(
        PRODUCTION_ITEMS_PROCESS,
        handler.handle,
        priority=100,
        label="production_inventory_handler",
    )
    logger.debug("Registered ProductionInventoryHandler on %s", PRODUCTION_ITEMS_PROCESS)

    # Production GL: PRODUCCION_COMPLETADA → cost-of-production journal entry
    # FASE 6: pass db= so the handler can query production_cost_ledger for real
    # cost numbers and update costo_promedio for each output product.
    fs = getattr(container, "finance_service", None)
    if fs:
        from core.events.event_bus import PRODUCCION_COMPLETADA
        from core.events.domain_events import PRODUCTION_BATCH_CREATED
        fin_handler = ProductionFinanceHandler(finance_service=fs, db=db)
        bus.subscribe(
            PRODUCCION_COMPLETADA,
            fin_handler.handle,
            priority=45,
            label="production_finance_handler",
        )
        logger.debug("Registered ProductionFinanceHandler on %s", PRODUCCION_COMPLETADA)

        # P0-2: ProductionEngine.close_batch() publishes PRODUCTION_BATCH_CREATED
        # (not PRODUCCION_COMPLETADA).  Register the same finance handler so batches
        # also post GL entries — using the same db= path to read production_cost_ledger.
        batch_fin_handler = ProductionFinanceHandler(finance_service=fs, db=db)
        bus.subscribe(
            PRODUCTION_BATCH_CREATED,
            batch_fin_handler.handle,
            priority=45,
            label="production_batch_finance_handler",
        )
        logger.debug("Registered ProductionFinanceHandler on %s", PRODUCTION_BATCH_CREATED)


# ── Phase 4: PURCHASE_ITEMS_PROCESS + PURCHASE_CREATED handlers ──────────────

def _wire_purchase_items_handlers(bus, container) -> None:
    """
    Register PurchaseInventoryHandler on PURCHASE_ITEMS_PROCESS (sync, inside SAVEPOINT)
    and PurchaseFinanceHandler on PURCHASE_CREATED (async, post-transaction).

    Priority order:
      100 — PurchaseInventoryHandler: add stock IN (must run first)
       80 — PurchaseFinanceHandler:   record cost-of-goods journal entry
    """
    from core.events.domain_events import PURCHASE_ITEMS_PROCESS, PURCHASE_CREATED
    from core.events.handlers.purchase_handler import (
        PurchaseInventoryHandler,
        PurchaseFinanceHandler,
    )

    inv = getattr(container, "inventory_service", None)
    fs  = getattr(container, "finance_service", None)

    if inv:
        inv_handler = PurchaseInventoryHandler(inventory_service=inv)
        bus.subscribe(
            PURCHASE_ITEMS_PROCESS,
            inv_handler.handle,
            priority=100,
            label="purchase_inventory_handler",
        )
        logger.debug("Registered PurchaseInventoryHandler on %s", PURCHASE_ITEMS_PROCESS)

    if fs:
        fin_handler = PurchaseFinanceHandler(finance_service=fs)
        bus.subscribe(
            PURCHASE_CREATED,
            fin_handler.handle,
            priority=80,
            label="purchase_finance_handler",
        )
        logger.debug("Registered PurchaseFinanceHandler on %s", PURCHASE_CREATED)


# ── Phase 5: TRANSFER_ITEMS_PROCESS handler ───────────────────────────────────

def _wire_transfer_items_handlers(bus, container) -> None:
    """
    Register TransferInventoryHandler on TRANSFER_ITEMS_PROCESS.

    Handles multi-sucursal transfers:
      OUT origin branch  (delta < 0, TRANSFER_OUT / TRANSFER_CANCEL)
      IN  dest   branch  (delta > 0, TRANSFER_IN)

    Runs synchronously inside the transfer SAVEPOINT at priority=100.
    """
    from core.events.domain_events import TRANSFER_ITEMS_PROCESS
    from core.events.handlers.transfer_handler import TransferInventoryHandler
    from core.services.inventory.unified_inventory_service import UnifiedInventoryService

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_transfer_items_handlers: no container.db — skipping")
        return

    inv_eng = UnifiedInventoryService(conn=db, sucursal_id=1, usuario="transferencia")
    handler = TransferInventoryHandler(inventory_engine=inv_eng)
    bus.subscribe(
        TRANSFER_ITEMS_PROCESS,
        handler.handle,
        priority=100,
        label="transfer_inventory_handler",
    )
    logger.debug("Registered TransferInventoryHandler on %s", TRANSFER_ITEMS_PROCESS)


def _wire_delivery_handlers(bus, container) -> None:
    """v13.5: Delivery reservation + weight-adjustment handler chain.

    DELIVERY_ORDER_RESERVED     → DeliveryReserveStockHandler     (priority=100)
    stock_liberar_solicitado    → DeliveryReservationReleaseHandler (priority=100)
    INVENTORY_RELEASE_REQUIRED  → DeliveryReservationReleaseHandler (priority=100)
    DELIVERY_ITEM_WEIGHT_ADJUSTED → DeliveryWeightAdjustmentHandler (priority=100)
    DELIVERY_ITEM_WEIGHT_ADJUSTED → DeliveryWhatsAppNotificationHandler (priority=10)
    DELIVERY_TOTAL_UPDATED      → DeliveryPaymentUpdateHandler     (priority=50)
    """
    from core.events.event_bus import (
        DELIVERY_ORDER_RESERVED,
        DELIVERY_RESERVATION_RELEASED,
        DELIVERY_ITEM_WEIGHT_ADJUSTED,
        DELIVERY_TOTAL_UPDATED,
        INVENTORY_RELEASE_REQUIRED,
    )
    from core.events.handlers.delivery_handler import (
        DeliveryReserveStockHandler,
        DeliveryReservationReleaseHandler,
        DeliveryWeightAdjustmentHandler,
        DeliveryPaymentUpdateHandler,
        DeliveryWhatsAppNotificationHandler,
    )

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_delivery_handlers: no container.db — skipping")
        return

    reserve_handler   = DeliveryReserveStockHandler(db)
    release_handler   = DeliveryReservationReleaseHandler(db)
    weight_handler    = DeliveryWeightAdjustmentHandler(db)
    payment_handler   = DeliveryPaymentUpdateHandler(db)
    wa_weight_handler = DeliveryWhatsAppNotificationHandler()

    bus.subscribe(
        DELIVERY_ORDER_RESERVED,
        reserve_handler.handle,
        priority=100,
        label="delivery_reserve_stock",
    )
    # Release reservations when order is cancelled (legacy event name)
    bus.subscribe(
        "stock_liberar_solicitado",
        release_handler.handle,
        priority=100,
        label="delivery_reservation_release_legacy",
    )
    # Release reservations via new canonical event (ChangeDeliveryStatusUseCase)
    bus.subscribe(
        INVENTORY_RELEASE_REQUIRED,
        release_handler.handle,
        priority=100,
        label="delivery_reservation_release",
    )
    bus.subscribe(
        DELIVERY_ITEM_WEIGHT_ADJUSTED,
        weight_handler.handle,
        priority=100,
        label="delivery_weight_adjustment",
    )
    bus.subscribe(
        DELIVERY_ITEM_WEIGHT_ADJUSTED,
        wa_weight_handler.handle,
        priority=10,
        label="delivery_wa_weight_notify",
    )
    bus.subscribe(
        DELIVERY_TOTAL_UPDATED,
        payment_handler.handle,
        priority=50,
        label="delivery_payment_update",
    )
    logger.debug(
        "Registered delivery handlers: reserve, release, weight, WA-notify, payment-update"
        # appended below by _wire_delivery_lifecycle_handlers
    )


def _wire_legacy_delivery_event_bridge(bus, container) -> None:
    """Bridge canonical delivery events to legacy Spanish event names temporarily."""
    from core.delivery.application.legacy_event_bridge import register_legacy_delivery_event_bridge

    register_legacy_delivery_event_bridge(bus)
    logger.debug("Registered LegacyDeliveryEventBridge for canonical delivery events")


# ── v13.30: Delivery lifecycle handlers ──────────────────────────────────────

def _wire_delivery_lifecycle_handlers(bus, container) -> None:
    """Register DeliveryLifecycleAuditHandler on all lifecycle events.

    Priority=30 (audit layer — after business logic at 100/80/50).
    Events: DELIVERY_ORDER_CREATED, DELIVERY_ORDER_CONFIRMED,
            DELIVERY_ORDER_PREPARING, DELIVERY_DRIVER_ASSIGNED,
            DELIVERY_OUT_FOR_DELIVERY, DELIVERY_ORDER_DELIVERED,
            DELIVERY_ORDER_CANCELLED
    """
    from core.events.event_bus import (
        DELIVERY_ORDER_CREATED, DELIVERY_ORDER_CONFIRMED, DELIVERY_ORDER_PREPARING,
        DELIVERY_DRIVER_ASSIGNED, DELIVERY_OUT_FOR_DELIVERY,
        DELIVERY_ORDER_DELIVERED, DELIVERY_ORDER_CANCELLED,
    )
    from core.events.handlers.delivery_handler import DeliveryLifecycleAuditHandler

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_delivery_lifecycle_handlers: no container.db — skipping")
        return

    handler = DeliveryLifecycleAuditHandler(db)

    lifecycle_events = [
        (DELIVERY_ORDER_CREATED,    "delivery_audit_created"),
        (DELIVERY_ORDER_CONFIRMED,  "delivery_audit_confirmed"),
        (DELIVERY_ORDER_PREPARING,  "delivery_audit_preparing"),
        (DELIVERY_DRIVER_ASSIGNED,  "delivery_audit_driver_assigned"),
        (DELIVERY_OUT_FOR_DELIVERY, "delivery_audit_out"),
        (DELIVERY_ORDER_DELIVERED,  "delivery_audit_delivered"),
        (DELIVERY_ORDER_CANCELLED,  "delivery_audit_cancelled"),
    ]
    for event, label in lifecycle_events:
        bus.subscribe(event, handler.handle, priority=30, label=label)

    logger.debug("Registered DeliveryLifecycleAuditHandler on %d events", len(lifecycle_events))


def _wire_inventory_commit_handler(bus, container) -> None:
    """Register InventoryCommitHandler on INVENTORY_COMMIT_REQUIRED.

    Priority=100 — must run before any analytics/notification handlers.
    """
    from core.events.event_bus import INVENTORY_COMMIT_REQUIRED
    from core.events.handlers.delivery_handler import InventoryCommitHandler

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_inventory_commit_handler: no container.db — skipping")
        return

    handler = InventoryCommitHandler(db)
    bus.subscribe(
        INVENTORY_COMMIT_REQUIRED,
        handler.handle,
        priority=100,
        label="inventory_commit_delivery",
    )
    logger.debug("Registered InventoryCommitHandler on %s", INVENTORY_COMMIT_REQUIRED)


def _wire_driver_settlement_handler(bus, container) -> None:
    """Register DriverSettlementFinanceHandler on DRIVER_SETTLEMENT_CREATED."""
    from core.events.event_bus import DRIVER_SETTLEMENT_CREATED
    from core.events.handlers.delivery_handler import DriverSettlementFinanceHandler

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_driver_settlement_handler: no container.db — skipping")
        return

    handler = DriverSettlementFinanceHandler(db)
    bus.subscribe(
        DRIVER_SETTLEMENT_CREATED,
        handler.handle,
        priority=50,
        label="driver_settlement_finance",
    )

    # Revenue recognition when a delivery total is finalized (defect 11/14)
    from core.events.event_bus import DELIVERY_TOTAL_FINALIZED
    from core.events.handlers.delivery_finance_handler import DeliveryRevenueFinanceHandler
    revenue_handler = DeliveryRevenueFinanceHandler(db)
    bus.subscribe(
        DELIVERY_TOTAL_FINALIZED,
        revenue_handler.handle,
        priority=50,
        label="delivery_revenue_finance",
    )

    # Also wire PurchaseSuggestionHandler
    from core.events.event_bus import PURCHASE_SUGGESTION_CREATED
    from core.events.handlers.delivery_handler import PurchaseSuggestionHandler
    ps_handler = PurchaseSuggestionHandler(db)
    bus.subscribe(
        PURCHASE_SUGGESTION_CREATED,
        ps_handler.handle,
        priority=30,
        label="purchase_suggestion_log",
    )
    logger.debug("Registered DriverSettlementFinanceHandler + PurchaseSuggestionHandler")


def _wire_notification_handler(bus, container) -> None:
    """Register DeliveryNotificationDispatchHandler on CUSTOMER_NOTIFICATION_REQUESTED."""
    from core.events.event_bus import CUSTOMER_NOTIFICATION_REQUESTED
    from core.events.handlers.delivery_handler import DeliveryNotificationDispatchHandler

    # Reuse notification_service from container if available
    notif_svc = getattr(container, "delivery_notification_service", None)
    handler = DeliveryNotificationDispatchHandler(notification_service=notif_svc)
    bus.subscribe(
        CUSTOMER_NOTIFICATION_REQUESTED,
        handler.handle,
        priority=10,
        label="customer_notification_dispatch",
    )
    logger.debug("Registered DeliveryNotificationDispatchHandler on %s",
                 CUSTOMER_NOTIFICATION_REQUESTED)


# ── migración 083: trazabilidad financiera end-to-end ────────────────────────

def _wire_financial_trace_handlers(bus, container) -> None:
    """
    Registra los handlers de trazabilidad financiera end-to-end.

    Escuchan eventos post-commit (priority=20) y delegan a FinancialTraceService,
    que escribe en las tablas canónicas de migración 083:
      financial_documents, treasury_movements, journal_entries,
      financial_trace_log, reconciliation_records.

    No interfieren con handlers críticos (p=85-100) porque son post-commit.
    Cada handler captura su propia excepción — un fallo de traza no corta el flujo.
    """
    from core.events.event_bus import (
        VENTA_COMPLETADA,
        COMPRA_REGISTRADA,
        PUNTOS_ACUMULADOS,
    )
    from core.events.domain_events import (
        PAYMENT_CONFIRMED,
        PAYROLL_PAID,
        WASTE_RECORDED,
        DELIVERY_PAYMENT_CONFIRMED,
        DRIVER_SETTLEMENT_CREATED,
        MAINTENANCE_REGISTERED,
        OPERATING_SUPPLY_PURCHASED,
    )
    from core.events.handlers.financial_trace_handler import (
        SaleTraceHandler,
        PurchaseTraceHandler,
        PaymentTraceHandler,
        PayrollTraceHandler,
        WasteTraceHandler,
        LoyaltyTraceHandler,
        DeliveryPaymentHandler,
        DriverSettlementHandler,
        MaintenanceTraceHandler,
        SupplyTraceHandler,
        _build_trace_service,
    )

    db = getattr(container, "db", None)
    if not db:
        logger.debug("_wire_financial_trace_handlers: no container.db — skipping")
        return

    # Construir sub-servicios desde container (todos opcionales)
    finance_services = {
        "journal_service":          getattr(container, "journal_entry_service", None),
        "document_service":         getattr(container, "financial_document_service", None),
        "treasury_movement_service": getattr(container, "treasury_movement_service", None),
        "asset_service":            getattr(container, "fixed_asset_service", None),
        "maintenance_service":      getattr(container, "maintenance_finance_service", None),
        "supply_service":           getattr(container, "operating_supplies_service", None),
        "idempotency_service":      getattr(container, "idempotency_service", None),
    }

    ts = _build_trace_service(db, finance_services)

    _PRIORITY = 20  # post-commit, después de todos los handlers críticos

    bus.subscribe(VENTA_COMPLETADA,           SaleTraceHandler(ts).handle,           priority=_PRIORITY, label="fin_trace_sale")
    bus.subscribe(COMPRA_REGISTRADA,          PurchaseTraceHandler(ts).handle,        priority=_PRIORITY, label="fin_trace_purchase")
    bus.subscribe(PAYMENT_CONFIRMED,          PaymentTraceHandler(ts).handle,         priority=_PRIORITY, label="fin_trace_payment")
    bus.subscribe(PAYROLL_PAID,               PayrollTraceHandler(ts).handle,         priority=_PRIORITY, label="fin_trace_payroll")
    bus.subscribe(WASTE_RECORDED,             WasteTraceHandler(ts).handle,           priority=_PRIORITY, label="fin_trace_waste")
    bus.subscribe(PUNTOS_ACUMULADOS,          LoyaltyTraceHandler(ts).handle,         priority=_PRIORITY, label="fin_trace_loyalty")
    bus.subscribe(DELIVERY_PAYMENT_CONFIRMED, DeliveryPaymentHandler(ts).handle,      priority=_PRIORITY, label="fin_trace_delivery_pay")
    bus.subscribe(DRIVER_SETTLEMENT_CREATED,  DriverSettlementHandler(ts).handle,     priority=_PRIORITY, label="fin_trace_driver_settle")
    bus.subscribe(MAINTENANCE_REGISTERED,     MaintenanceTraceHandler(ts).handle,     priority=_PRIORITY, label="fin_trace_maintenance")
    bus.subscribe(OPERATING_SUPPLY_PURCHASED, SupplyTraceHandler(ts).handle,          priority=_PRIORITY, label="fin_trace_supply")

    logger.debug("Registered 10 FinancialTrace handlers (priority=%d)", _PRIORITY)
