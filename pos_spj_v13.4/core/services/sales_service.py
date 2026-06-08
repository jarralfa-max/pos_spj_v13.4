from core.services.auto_audit import audit_write

# core/services/sales_service.py
import uuid
import os
import logging
from datetime import datetime

from core.events.domain_events import SALE_ITEMS_PROCESS
import json
from core.events.event_factory import make_sale_payload
from core.services.sales_fulfillment_service import SaleFulfillmentService

logger = logging.getLogger(__name__)

ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA = "ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA"
ALLOW_LEGACY_MINIMAL_SALE_WRITE = "ALLOW_LEGACY_MINIMAL_SALE_WRITE"
LEGACY_SALES_REMOVAL_DATE = "2026-06-30"


def _legacy_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "0")).strip().lower() in {"1", "true", "yes", "on"}


class SalesService:
    """
    Orquestador principal del flujo de Ventas (POS, WhatsApp, Delivery).
    Procesa el carrito, descuenta inventario inteligente (simples y combos),
    registra el ingreso en caja, otorga puntos de fidelidad y sincroniza a la nube.
    """
    
    def __init__(self, db_conn, sales_repo, recipe_repo, inventory_service,
                 finance_service, loyalty_service, promotion_engine, sync_service,
                 ticket_template_engine, whatsapp_service, config_service,
                 feature_flag_service, pricing_service=None,
                 growth_engine=None, notification_service=None,
                 customer_service=None, printer_service=None):
        # Inyección de dependencias
        self.db = db_conn
        self.pricing_service = pricing_service
        self.growth_engine = growth_engine
        self.notification_service = notification_service
        self.sales_repo = sales_repo
        self.recipe_repo = recipe_repo
        self.inventory_service = inventory_service
        self._comisiones_svc = None  # Inyectado desde AppContainer
        self._happy_hour_svc = None   # Inyectado desde AppContainer
        # LoteService: FIFO de caducidades (opcional — no bloquea si falla)
        try:
            from core.services.lote_service import LoteService
            self._lote_svc = LoteService(db_conn)
        except Exception as exc:
            logger.warning("LoteService no disponible para venta; FIFO queda desactivado explícitamente: %s", exc)
            self._lote_svc = None
        self.finance_service = finance_service
        self.loyalty_service = loyalty_service
        self.promotion_engine = promotion_engine
        self.sync_service = sync_service
        self.ticket_template_engine = ticket_template_engine
        self.whatsapp_service = whatsapp_service
        self.config_service = config_service
        self.feature_flag_service = feature_flag_service
        self.customer_service = customer_service
        self.printer_service = printer_service
        self._fulfillment = SaleFulfillmentService(db_conn)
        self._sale_loyalty_policy = None

    def _generate_unique_sale_folio(self) -> str:
        """
        Genera folio único auditable para ventas.
        Formato: VYYYYMMDDHHMMSSffffff-XXXX
        """
        base = datetime.now().strftime("%Y%m%d%H%M%S%f")
        for _ in range(5):
            folio = f"V{base}-{uuid.uuid4().hex[:4].upper()}"
            try:
                row = self.db.execute(
                    "SELECT 1 FROM ventas WHERE folio=? LIMIT 1", (folio,)
                ).fetchone()
                if not row:
                    return folio
            except Exception as exc:
                logger.warning("No se pudo validar unicidad de folio; usando folio generado: %s", exc)
                return folio
        return f"V{base}-{uuid.uuid4().hex[:8].upper()}"

    def _validate_stock_pre_sale(self, items: list, branch_id: int) -> None:
        """
        Read-only stock guard executed BEFORE opening the SAVEPOINT.

        Raises RuntimeError with a human-readable message if any simple item
        lacks sufficient stock.  Composite items are skipped here — the
        SaleInventoryHandler validates each component when it processes the recipe.

        Why before the SAVEPOINT: guarantees a clean raise (no partial DB state)
        even when SALE_ITEMS_PROCESS handlers run inside the transaction.
        """
        if not items:
            return
        for item in items:
            if float(item.get("qty", 0)) <= 0:
                continue
            try:
                self._fulfillment.resolve_item(item["product_id"], float(item["qty"]), branch_id)
            except RuntimeError:
                raise
            except ValueError as e:
                raise RuntimeError(str(e))
            except Exception as exc:
                logger.error(
                    "Pre-validación de stock/fulfillment falló para product_id=%s qty=%s branch_id=%s: %s",
                    item.get("product_id"), item.get("qty"), branch_id, exc
                )
                raise RuntimeError(
                    "No se pudo validar inventario antes de la venta. Intenta nuevamente."
                ) from exc

    def _resolve_sale_items(self, items: list, branch_id: int) -> list:
        resolved = []
        for item in items:
            pid = int(item["product_id"])
            qty = float(item["qty"])
            lines = self._fulfillment.resolve_item(pid, qty, branch_id)
            for ln in lines:
                resolved.append({
                    "product_id": ln.product_id,
                    "qty": ln.qty,
                    "cantidad": ln.qty,
                    "unit_price": item.get("unit_price", 0),
                    "precio_unitario": item.get("precio_unitario", item.get("unit_price", 0)),
                    "nombre": item.get("nombre", ln.name),
                    "unidad": item.get("unidad", "kg"),
                    "es_compuesto": 0,
                    "fulfillment_mode": ln.mode,
                    "source_product_id": ln.source_product_id,
                    "sold_product_id": pid,
                })
        # merge duplicates from nested recipes
        merged = {}
        for r in resolved:
            key = r["product_id"]
            if key not in merged:
                merged[key] = dict(r)
            else:
                merged[key]["qty"] += r["qty"]
                merged[key]["cantidad"] += r["cantidad"]
        return list(merged.values())

    def _loyalty_policy(self):
        if self._sale_loyalty_policy is None:
            try:
                from core.services.sales.sale_loyalty_policy import SaleLoyaltyPolicy
                self._sale_loyalty_policy = SaleLoyaltyPolicy(self.db, loyalty_service=self.loyalty_service)
            except Exception as exc:
                logger.warning("SaleLoyaltyPolicy no disponible; usando LoyaltyService directo si existe: %s", exc)
                self._sale_loyalty_policy = None
        return self._sale_loyalty_policy

    def _normalize_payment_method(self, payment_method: str) -> str:
        try:
            from core.services.payment_normalization import normalize_payment_method as _npm
            return _npm(payment_method)
        except Exception as exc:
            logger.warning("No se pudo normalizar método de pago %r; se conserva valor original: %s", payment_method, exc)
            return payment_method

    def _normalize_items_payload(self, items: list) -> list:
        normalized = []
        for _it in items:
            normalized.append({
                'product_id': _it.get('product_id', _it.get('id', 0)),
                'qty': float(_it.get('qty', _it.get('cantidad', 1))),
                'unit_price': float(_it.get('unit_price', _it.get('precio_unitario', 0))),
                'precio_unitario': float(_it.get('unit_price', _it.get('precio_unitario', 0))),
                'cantidad': float(_it.get('qty', _it.get('cantidad', 1))),
                'nombre': _it.get('nombre', _it.get('name', '')),
                'unidad': _it.get('unidad', 'pz'),
                'es_compuesto': _it.get('es_compuesto', 0),
                'promo_nombre': _it.get('promo_nombre', ''),
            })
        return normalized

    def _validate_payment(
        self,
        payment_method: str,
        total_a_pagar: float,
        payment_lines: dict,
        client_id: int = None,
    ):
        from core.services.payment_normalization import is_credit_sale

        method = self._normalize_payment_method(payment_method)
        total_a_pagar = round(float(total_a_pagar or 0.0), 2)
        lines = dict(payment_lines or {})

        if is_credit_sale(method) and client_id and self.customer_service:
            ok, msg = self.customer_service.validate_credit(client_id, total_a_pagar)
            if not ok:
                raise ValueError(msg)

        if method == "Efectivo":
            efectivo = round(float(lines.get("efectivo", 0.0) or 0.0), 2)
            if efectivo < total_a_pagar:
                raise ValueError(
                    f"El efectivo recibido (${efectivo:,.2f}) es menor al total a cobrar (${total_a_pagar:,.2f})"
                )
        elif method in {"Pago Mixto", "Mixto"}:
            pagado = round(
                float(lines.get("efectivo", 0.0) or 0.0)
                + float(lines.get("tarjeta", 0.0) or 0.0)
                + float(lines.get("transferencia", 0.0) or 0.0),
                2,
            )
            if pagado < total_a_pagar:
                raise ValueError(
                    f"Pago mixto insuficiente (${pagado:,.2f}) para total ${total_a_pagar:,.2f}"
                )
        elif method in {"Tarjeta", "Transferencia", "Mercado Pago"}:
            key = {"Tarjeta": "tarjeta", "Transferencia": "transferencia", "Mercado Pago": "mercado_pago"}[method]
            if round(float(lines.get(key, 0.0) or 0.0), 2) < total_a_pagar:
                raise ValueError(f"Pago {method} incompleto para total ${total_a_pagar:,.2f}")
        elif is_credit_sale(method):
            if round(float(lines.get("credito", 0.0) or 0.0), 2) < total_a_pagar:
                raise ValueError(f"Pago a crédito incompleto para total ${total_a_pagar:,.2f}")
        else:
            raise ValueError(f"Método de pago desconocido: {method}")

    def _amount_paid_for_storage(self, payment_method: str, payment_lines: dict, total: float) -> float:
        method = self._normalize_payment_method(payment_method)
        lines = dict(payment_lines or {})
        total = round(float(total or 0.0), 2)
        if method == "Efectivo":
            return round(float(lines.get("efectivo", 0.0) or 0.0), 2)
        if method in {"Crédito", "Credito"}:
            return 0.0
        if method in {"Tarjeta", "Transferencia", "Mercado Pago", "Pago Mixto", "Mixto"}:
            return round(
                float(lines.get("efectivo", 0.0) or 0.0)
                + float(lines.get("tarjeta", 0.0) or 0.0)
                + float(lines.get("transferencia", 0.0) or 0.0)
                + float(lines.get("mercado_pago", 0.0) or 0.0),
                2,
            )
        raise ValueError(f"Método de pago desconocido: {method}")

    def _ensure_pending_sales_intents_table(self) -> None:
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS pending_sales_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente_pago',
                reservation_id INTEGER,
                payment_id TEXT DEFAULT '',
                payment_url TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT DEFAULT (datetime('now', '+30 minutes')),
                confirmed_at TEXT
            )"""
        )
        for stmt in (
            "ALTER TABLE pending_sales_intents ADD COLUMN reservation_id INTEGER",
            "ALTER TABLE pending_sales_intents ADD COLUMN payment_url TEXT DEFAULT ''",
            "ALTER TABLE pending_sales_intents ADD COLUMN expires_at TEXT",
        ):
            try:
                self.db.execute(stmt)
            except Exception as exc:
                logger.debug("pending_sales_intents migration skipped: %s", exc)
        try:
            self.db.execute(
                "UPDATE pending_sales_intents "
                "SET expires_at=datetime('now', '+30 minutes') "
                "WHERE expires_at IS NULL AND estado='pendiente_pago'"
            )
        except Exception as exc:
            logger.debug("pending_sales_intents expires_at backfill skipped: %s", exc)

    def create_pending_payment_sale(self, branch_id: int, user: str, items: list,
                                    client_id: int = None, notes: str = "",
                                    total: float = 0.0) -> dict:
        """Crea intención Mercado Pago pendiente y reserva stock temporalmente."""
        if not items:
            raise ValueError("Mercado Pago pendiente requiere items para reservar stock.")

        self._ensure_pending_sales_intents_table()
        branch_id = int(branch_id or 1)
        folio = f"MP-{uuid.uuid4().hex[:12].upper()}"
        normalized_items = self._normalize_items_payload(items)
        reservation_items = [
            {"id": int(item["product_id"]), "cantidad": float(item["qty"])}
            for item in normalized_items
        ]
        from core.services.stock_reservation_service import StockReservationService
        reservation_id = StockReservationService(self.db, branch_id=branch_id).reservar(
            folio,
            reservation_items,
        )
        payload = {
            "branch_id": branch_id,
            "user": str(user or "sistema"),
            "client_id": client_id,
            "items": normalized_items,
            "total": round(float(total or 0.0), 2),
            "notes": str(notes or ""),
            "reservation_id": int(reservation_id),
            "payment_method": "Mercado Pago",
        }
        try:
            self.db.execute(
                """INSERT INTO pending_sales_intents
                   (folio, payload_json, estado, reservation_id, expires_at)
                   VALUES (?, ?, 'pendiente_pago', ?, datetime('now', '+30 minutes'))""",
                (folio, json.dumps(payload, ensure_ascii=False), int(reservation_id)),
            )
        except Exception as exc:
            logger.warning("No se pudo persistir intención MP; liberando reserva_id=%s: %s", reservation_id, exc)
            try:
                StockReservationService(self.db, branch_id=branch_id).liberar(
                    reservation_id,
                    motivo="cancelada",
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "No se pudo liberar reserva MP tras fallo de intención: reserva_id=%s error=%s",
                    reservation_id,
                    cleanup_exc,
                )
            raise
        try:
            self.db.commit()
        except Exception as exc:
            logger.debug("commit intención MP pendiente omitido: %s", exc)
        return {
            "folio": folio,
            "estado": "pendiente_pago",
            "reservation_id": int(reservation_id),
            "items": normalized_items,
            "total": payload["total"],
        }

    def attach_pending_payment_link(self, folio: str, url: str) -> None:
        self._ensure_pending_sales_intents_table()
        self.db.execute(
            "UPDATE pending_sales_intents SET payment_url=? WHERE folio=? AND estado='pendiente_pago'",
            (str(url or ""), str(folio)),
        )
        try:
            self.db.commit()
        except Exception as exc:
            logger.debug("commit link MP pendiente omitido: %s", exc)

    def cancel_pending_payment_sale(self, folio: str, motivo: str = "cancelada") -> None:
        self._ensure_pending_sales_intents_table()
        row = self.db.execute(
            "SELECT payload_json, reservation_id FROM pending_sales_intents WHERE folio=? LIMIT 1",
            (str(folio),),
        ).fetchone()
        if not row:
            return
        payload_json = row[0] if isinstance(row, tuple) else row["payload_json"]
        reservation_id = row[1] if isinstance(row, tuple) else row["reservation_id"]
        data = json.loads(payload_json or "{}")
        reservation_id = int(reservation_id or data.get("reservation_id") or 0)
        estado = "expirada" if str(motivo).strip().lower() == "expirada" else "cancelada"
        if reservation_id:
            from core.services.stock_reservation_service import StockReservationService
            StockReservationService(self.db, branch_id=int(data.get("branch_id", 1))).liberar(
                reservation_id,
                motivo=estado,
            )
        self.db.execute(
            "UPDATE pending_sales_intents SET estado=? WHERE folio=? AND estado='pendiente_pago'",
            (estado, str(folio)),
        )
        try:
            self.db.commit()
        except Exception as exc:
            logger.debug("commit cancelación MP pendiente omitido: %s", exc)

    def expire_pending_payment_sales(self) -> int:
        self._ensure_pending_sales_intents_table()
        rows = self.db.execute(
            """SELECT folio FROM pending_sales_intents
               WHERE estado='pendiente_pago'
                 AND expires_at IS NOT NULL
                 AND expires_at < datetime('now')"""
        ).fetchall()
        for row in rows:
            folio = row[0] if isinstance(row, tuple) else row["folio"]
            self.cancel_pending_payment_sale(str(folio), motivo="expirada")
        return len(rows)

    def confirm_pending_payment_sale(self, folio: str, payment_id: str = "") -> tuple:
        """
        Convierte una intención pendiente de MercadoPago en venta definitiva.
        """
        row = self.db.execute(
            "SELECT payload_json, estado FROM pending_sales_intents WHERE folio=? LIMIT 1",
            (str(folio),),
        ).fetchone()
        if not row:
            raise RuntimeError(f"Intento pendiente no encontrado: {folio}")
        payload_json = row[0] if isinstance(row, tuple) else row["payload_json"]
        estado = row[1] if isinstance(row, tuple) else row["estado"]
        if estado == "confirmada":
            # idempotencia: no reprocesar
            return str(folio), ""
        if estado != "pendiente_pago":
            raise RuntimeError(f"Intento Mercado Pago no confirmable: {folio} estado={estado}")
        data = json.loads(payload_json or "{}")
        total = float(data.get("total", 0.0))
        items = data.get("items") or []
        branch_id = int(data.get("branch_id", 1))
        user = str(data.get("user", "sistema"))
        client_id = data.get("client_id")
        notes = str(data.get("notes", "")) + f" [MP payment_id={payment_id}]"
        reservation_id = int(data.get("reservation_id") or 0)
        rich = self.execute_sale_result(
            branch_id=branch_id,
            user=user,
            items=items,
            payment_method="Mercado Pago",
            amount_paid=total,
            payment_breakdown={"mercado_pago": total},
            client_id=client_id,
            notes=notes,
            reservation_id=reservation_id,
        )
        folio_sale, ticket = rich.folio, rich.ticket_html
        self.db.execute(
            "UPDATE pending_sales_intents SET estado='confirmada', payment_id=?, confirmed_at=datetime('now') WHERE folio=?",
            (str(payment_id or ""), str(folio)),
        )
        try:
            self.db.commit()
        except Exception as exc:
            logger.warning("No se pudo confirmar commit de intención MP confirmada folio=%s: %s", folio, exc)
        return folio_sale, ticket


    def _sale_handler_labels(self, bus, event_type: str) -> set[str]:
        if hasattr(bus, "handler_labels"):
            return {str(label) for label in (bus.handler_labels(event_type) or [])}
        handlers = getattr(bus, "_handlers", {}).get(event_type, [])
        return {str(label) for _, label, _ in handlers}

    def _validate_critical_sale_handlers(self, bus, event_type: str, payment_method: str) -> None:
        labels = self._sale_handler_labels(bus, event_type)
        missing: list[str] = []

        def _has(fragment: str) -> bool:
            return any(fragment in label for label in labels)

        if not _has("sale_inventory"):
            missing.append("inventario")
        if not _has("sale_finance"):
            missing.append("finanzas/caja")
        from core.services.payment_normalization import is_credit_sale
        if is_credit_sale(payment_method) and not _has("sale_credit"):
            missing.append("crédito")

        if missing:
            registered = ", ".join(sorted(labels)) or "sin handlers etiquetados"
            raise RuntimeError(
                "Handlers críticos de venta no registrados: "
                + ", ".join(missing)
                + f". Registrados: {registered}"
            )


    def _raffle_auto_print_enabled(self) -> bool:
        """Return whether confirmed-sale raffle tickets should be printed automatically."""
        if not self.config_service:
            return True
        disabled_values = {"0", "false", "no", "off", "disabled", "desactivado"}
        try:
            raw = self.config_service.get("raffle_ticket_print_auto", None)
            if raw in (None, ""):
                raw = self.config_service.get("imprimir_automatico_boletos_sorteo", "1")
        except Exception as exc:
            logger.warning("No se pudo leer configuración de impresión automática de rifas: %s", exc)
            return True
        return str(raw).strip().lower() not in disabled_values

    def _raffle_ticket_print_payload(self, snapshot):
        """Normalize raffle snapshots or direct printable payloads into PrinterService input."""
        if not isinstance(snapshot, dict):
            return None
        nested = snapshot.get("raffle_ticket")
        if isinstance(nested, dict):
            return nested
        if str(snapshot.get("ticket_type") or "") == "raffle_ticket":
            return snapshot
        has_raffle_identity = (
            snapshot.get("raffle_id") or snapshot.get("raffle_name") or snapshot.get("raffle")
        )
        if snapshot.get("numero_boleto") and has_raffle_identity:
            payload = dict(snapshot)
            payload.setdefault("ticket_type", "raffle_ticket")
            payload.setdefault("raffle_name", payload.get("raffle") or "")
            payload.setdefault("barcode", payload.get("numero_boleto"))
            payload.setdefault(
                "qr_content",
                "RAFFLE:{raffle_id}|SALE:{venta_id}|TICKET:{numero}".format(
                    raffle_id=payload.get("raffle_id", ""),
                    venta_id=payload.get("venta_id", ""),
                    numero=payload.get("numero_boleto", ""),
                ),
            )
            return payload
        return None

    def _print_raffle_tickets_after_sale(self, raffle_tickets_snapshot, sale_id) -> list[str]:
        """Print issued raffle tickets after the sale is confirmed without cancelling the sale."""
        printed_job_ids: list[str] = []
        if not raffle_tickets_snapshot or not self._raffle_auto_print_enabled():
            return printed_job_ids
        printer = getattr(self, "printer_service", None)
        if not printer or not hasattr(printer, "print_raffle_ticket"):
            return printed_job_ids
        for snapshot in raffle_tickets_snapshot or []:
            payload = self._raffle_ticket_print_payload(snapshot)
            if not payload:
                logger.debug("Snapshot de rifa sin payload imprimible venta=%s: %s", sale_id, snapshot)
                continue
            try:
                job_id = printer.print_raffle_ticket(payload)
                if job_id:
                    printed_job_ids.append(str(job_id))
            except Exception as exc:
                logger.warning(
                    "No se pudo imprimir boleto de rifa venta=%s boleto=%s: %s",
                    sale_id,
                    payload.get("numero_boleto") or payload.get("barcode") or "",
                    exc,
                )
                continue
        return printed_job_ids

    def _execute_sale_core(self, branch_id: int, user: str, items: list, payment_method: str,
                     amount_paid: float, client_id: int = None, client_phone: str = None,
                     client_level: str = 'bronce', discount: float = 0.0, notes: str = "",
                     loyalty_redemption_pts: int = 0, return_details: bool = False,
                     payment_breakdown: dict | None = None, reservation_id: int | None = None,
                     operation_id: str | None = None):
        """
        Ejecuta la venta completa y devuelve el Folio y el Ticket HTML.
        
        :param items: Lista de diccionarios [{'product_id': 1, 'qty': 1.12, 'unit_price': 100, 'es_compuesto': 0, 'name': 'Pollo'}, ...]
        """
        operation_id = str(operation_id or uuid.uuid4())
        reservation_id = int(reservation_id or 0)
        reservation_confirmed = False

        payment_method = self._normalize_payment_method(payment_method)
        items = self._normalize_items_payload(items)

        # =========================================================
        # 1. PRE-PROCESAMIENTO: Matemáticas y Promociones
        # =========================================================
        # Nota: En un caso real aquí buscaríamos las promociones de la BD
        promos_activas = []

        # ── Aplicar precios VIP/lista por cliente ────────────────────────────
        if self.pricing_service and client_id:
            items_con_precio = []
            for item in items:
                try:
                    pi = self.pricing_service.get_precio(
                        producto_id=item['product_id'],
                        cantidad=float(item.get('qty', 1)),
                        cliente_id=client_id,
                        sucursal_id=branch_id
                    )
                    if pi and pi['fuente'] != 'base':
                        item = dict(item)
                        item['unit_price'] = pi['precio']
                except Exception as _e:
                    logger.debug("PricingService item %s: %s", item.get('product_id'), _e)
                items_con_precio.append(item)
            items = items_con_precio

        # ── Aplicar Happy Hour si hay reglas activas ─────────────────────────
        if self._happy_hour_svc:
            items_hh = []
            for item in items:
                try:
                    # Get categoria for category-level rules
                    cat_row = self.db.execute(
                        "SELECT categoria FROM productos WHERE id=?",
                        (item['product_id'],)
                    ).fetchone()
                    categoria = cat_row[0] if cat_row else None
                    nuevo_precio, _, promo = self._happy_hour_svc.aplicar_a_precio(
                        float(item['unit_price']),
                        producto_id=item['product_id'],
                        categoria=categoria
                    )
                    if promo:
                        item = dict(item)
                        item['unit_price'] = nuevo_precio
                        item['promo_nombre'] = promo
                except Exception as _e:
                    logger.debug("HappyHour item %s: %s", item.get('product_id'), _e)
                items_hh.append(item)
            items = items_hh

        context = {
            'hora_actual': datetime.now().time(),
            'nivel_cliente': client_level
        }

        # Aplicamos promociones si el motor está disponible
        if self.promotion_engine:
            resultado_promo = self.promotion_engine.aplicar_promociones(items, promos_activas, context)
            carrito_final   = resultado_promo.get('carrito_descontado', items)
        else:
            carrito_final = items  # sin motor de promociones activo
        
        # Cálculos finales
        subtotal = sum(item['qty'] * item['unit_price'] for item in carrito_final)
        total_a_pagar = subtotal - discount

        # ── Validación de cliente (si se indicó) ─────────────────────────────
        if client_id and self.customer_service:
            customer = self.customer_service.get_customer(client_id)
            if not customer:
                raise ValueError(f"Cliente ID {client_id} no encontrado o inactivo.")
        else:
            customer = None

        # ── Canje de puntos de lealtad (pre-pago, puro) ──────────────────────
        loyalty_discount = 0.0
        if loyalty_redemption_pts > 0 and client_id and self.loyalty_service:
            loyalty_discount = self.loyalty_service.compute_redemption_discount(
                loyalty_redemption_pts, total_a_pagar
            )
            total_a_pagar = round(total_a_pagar - loyalty_discount, 2)
            discount = round(discount + loyalty_discount, 2)

        payment_breakdown = self._build_payment_breakdown(
            payment_method=payment_method,
            total=total_a_pagar,
            amount_paid=amount_paid,
            payment_breakdown=payment_breakdown,
        )
        amount_paid_real = self._amount_paid_for_storage(payment_method, payment_breakdown, total_a_pagar)
        self._validate_payment(payment_method, total_a_pagar, payment_breakdown, client_id=client_id)

        # Guardia de margen v13.4 — no bloquea la venta, solo registra en audit
        if self.finance_service and hasattr(self.finance_service, 'validar_margen'):
            for _item in carrito_final:
                try:
                    if not self.finance_service.validar_margen(
                        _item.get('product_id', 0), _item.get('unit_price', 0)
                    ):
                        logger.warning(
                            "VENTA_BAJO_MARGEN: producto=%s precio=%.2f usuario=%s",
                            _item.get('product_id'), _item.get('unit_price'), user
                        )
                except Exception as exc:
                    logger.error(
                        "Validación de margen/costo falló antes de venta producto=%s usuario=%s: %s",
                        _item.get('product_id'), user, exc
                    )
                    raise RuntimeError("Validación de margen/costo no disponible; venta bloqueada.") from exc

        # =========================================================
        # 2. TRANSACCIÓN CRÍTICA DE BASE DE DATOS
        # =========================================================

        # Pre-SAVEPOINT: read-only stock guard (raises before any DB write)
        self._validate_stock_pre_sale(carrito_final, branch_id)

        _sp = None  # defined before try so except can always reference it
        try:
            import uuid as _uuid_sp
            _sp = f"venta_{_uuid_sp.uuid4().hex[:8]}"
            self.db.execute(f"SAVEPOINT {_sp}")
            cursor = self.db.cursor()

            # A. Guardar Cabecera de la Venta
            sale_id, folio = self.sales_repo.create_sale(
                branch_id=branch_id,
                user=user,
                client_id=client_id,
                subtotal=subtotal,
                discount=discount,
                total=total_a_pagar,
                payment_method=payment_method,
                amount_paid=amount_paid_real,
                operation_id=operation_id,
                notes=notes
            )

            if reservation_id:
                from core.services.stock_reservation_service import StockReservationService
                StockReservationService(self.db, branch_id=branch_id).confirmar(
                    reservation_id,
                    venta_id=sale_id,
                    folio=folio,
                )
                reservation_confirmed = True

            # B. Guardar detalles de línea (sin lógica de inventario)
            for item in carrito_final:
                self.sales_repo.save_sale_item(
                    sale_id=sale_id,
                    product_id=item['product_id'],
                    qty=item['qty'],
                    unit_price=item['unit_price'],
                    subtotal=(item['qty'] * item['unit_price'])
                )

            # C. Inventario + Finanzas vía evento SALE_ITEMS_PROCESS (sync, dentro del SAVEPOINT).
            #    SaleInventoryHandler y SaleFinanceHandler deben estar registrados;
            #    vender sin handlers críticos queda bloqueado.
            resolved_items = self._resolve_sale_items(carrito_final, branch_id)
            _sale_evt_payload = make_sale_payload(
                sale_id=sale_id,
                folio=folio,
                branch_id=branch_id,
                total=total_a_pagar,
                user=user,
                client_id=client_id,
                items=resolved_items,
                payment_method=payment_method,
                amount_paid=amount_paid_real,
                payment_breakdown=payment_breakdown,
                operation_id=operation_id,
            )
            try:
                from core.events.event_bus import get_bus
                _bus = get_bus()
                self._validate_critical_sale_handlers(_bus, SALE_ITEMS_PROCESS, payment_method)
                _bus.publish(SALE_ITEMS_PROCESS, _sale_evt_payload, strict=True)
            except Exception as _evt_err:
                logger.error("SALE_ITEMS_PROCESS dispatch failed (venta %s): %s", operation_id, _evt_err)
                raise  # propagate so SAVEPOINT rolls back

            # D. LOTE FIFO — batch/expiry tracking (optional, non-critical)
            if self._lote_svc:
                for item in carrito_final:
                    if item.get('es_compuesto', 0):
                        continue
                    try:
                        self._lote_svc.consumir_fifo(
                            producto_id=item['product_id'],
                            cantidad=float(item['qty']),
                            referencia=f"VENTA-{folio}",
                            usuario=user
                        )
                    except Exception as _le:
                        logger.debug("FIFO lotes pid=%s: %s", item['product_id'], _le)

            # E. Sincronización Offline-First (Nube)
            if self.sync_service:
                payload_venta = {
                    "folio": folio, "total": total_a_pagar, 
                    "metodo_pago": payment_method, "items": carrito_final
                }
                # Le pasamos el cursor para asegurar que se guarde en la misma transacción
                self.sync_service.registrar_evento(
                    cursor=cursor,
                    tabla="ventas",
                    operacion="INSERT",
                    registro_id=sale_id,
                    payload=payload_venta,
                    sucursal_id=branch_id
                )

            # ── Canje real dentro de transacción crítica (atómico con venta) ──
            if loyalty_redemption_pts > 0 and client_id and self.loyalty_service:
                _lp = self._loyalty_policy()
                _op = f"{operation_id}:redeem"
                red = (
                    _lp.apply_redemption(client_id, sale_id, loyalty_redemption_pts, _op)
                    if _lp else
                    self.loyalty_service.apply_redemption(
                        cliente_id=client_id,
                        venta_id=sale_id,
                        cajero_id=user,
                        subtotal=total_a_pagar,
                        puntos=loyalty_redemption_pts,
                    )
                )
                if not red.get("ok", False):
                    raise RuntimeError(f"Canje de lealtad no aplicado: {red.get('error', 'desconocido')}")

            # 🛡️ CIERRE EXITOSO DE BD: Si llegamos aquí, todo es consistente
            self.db.execute(f"RELEASE SAVEPOINT {_sp}")
            logger.info(f"Venta {folio} procesada con éxito. Operación: {operation_id}")

            # CxC for credit sales is handled atomically inside the SAVEPOINT by
            # CreditSaleFinanceHandler (priority=85 on SALE_ITEMS_PROCESS). Calling
            # register_credit_sale() here would create a duplicate CxC row.

            # ── Acreditación postventa idempotente antes del ticket ───────────
            loyalty_result = {"puntos_ganados": None, "puntos_totales": None, "nivel": None, "mensaje": "", "available": False}
            if client_id and self.loyalty_service:
                try:
                    _lp = self._loyalty_policy()
                    _op = f"{operation_id}:earn"
                    loyalty_result = (
                        _lp.earn_points(
                            cliente_id=client_id,
                            venta_id=sale_id,
                            total=float(total_a_pagar),
                            operation_id=_op,
                            branch_id=branch_id,
                            usuario=str(user),
                        ) if _lp else
                        self.loyalty_service.process_loyalty_for_sale(
                            client_id=client_id,
                            total_sale=float(total_a_pagar),
                            branch_id=branch_id,
                            venta_id=sale_id,
                            usuario=str(user),
                        )
                    ) or loyalty_result
                    loyalty_result = dict(loyalty_result or {})
                    loyalty_result["available"] = loyalty_result.get("puntos_totales") not in (None, "")
                except Exception as _lyl_aw_err:
                    logger.warning("loyalty accrual venta=%s: %s", sale_id, _lyl_aw_err)

            raffle_tickets_snapshot = []
            if self.loyalty_service:
                try:
                    raffle_tickets_snapshot = self.loyalty_service.process_raffles_for_sale(
                        venta_id=int(sale_id),
                        cliente_id=int(client_id or 0),
                        folio=str(folio),
                        total=float(total_a_pagar),
                        sucursal_id=int(branch_id),
                        payment_method=str(payment_method or ""),
                        items=carrito_final,
                        sale_datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        discount=discount,
                    ) or []
                except Exception as _raffle_err:
                    logger.warning("raffles process venta=%s: %s", sale_id, _raffle_err)

            # Notificar al EventBus (async_ para no bloquear al cajero)
            try:
                from core.events.event_bus import get_bus, VENTA_COMPLETADA
                from core.events.outbox import enqueue_event
                # Enrich payload with items so downstream handlers (analytics, WA) can use them
                event_payload = _sale_evt_payload
                # Fase 2: persistir evento en outbox antes del dispatch in-memory
                try:
                    enqueue_event(
                        self.db,
                        event_type=VENTA_COMPLETADA,
                        payload=event_payload,
                        aggregate_type="venta",
                        aggregate_id=sale_id,
                    )
                except Exception as _outbox_err:
                    logger.warning("Outbox persist failed (venta %s): %s", sale_id, _outbox_err)
                get_bus().publish(VENTA_COMPLETADA, {
                    "venta_id":      sale_id,
                    "folio":         folio,
                    "operation_id":  operation_id,
                    "branch_id":     branch_id,
                    "sucursal_id":   branch_id,
                    "total":         total_a_pagar,
                    "usuario":       user,
                    "cliente_id":    client_id,
                    "payment_method": payment_method,
                    "amount_paid": amount_paid_real,
                    "payment_breakdown": payment_breakdown,
                    "items": carrito_final,
                    "sale_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "loyalty_already_processed": True,
                    "loyalty_snapshot": loyalty_result,
                    "raffle_already_processed": True,
                    "raffle_tickets_snapshot": raffle_tickets_snapshot,
                }, async_=True)
            except Exception as _eb_err:
                logger.debug("EventBus publish: %s", _eb_err)  # nunca cancela la venta

        except Exception as e:
            # Rollback to savepoint if still active
            if _sp:
                try:
                    self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
                except Exception as _rollback_err:
                    logger.warning("Rollback de venta falló savepoint=%s: %s", _sp, _rollback_err)
            logger.error("Fallo en venta %s: %s", operation_id, e)
            raise RuntimeError(
                f"Operación cancelada. El inventario y caja están intactos: {e}"
            ) from e

        # =========================================================
        # 3. POST-PROCESAMIENTO (mínimo): Ticket de compatibilidad
        # Fase 5: notificaciones/comisiones/growth/fidelidad viven en handlers.
        # =========================================================

        # Generar Ticket
        ticket_final_html = ""
        try:
            datos_venta = {
                'venta_id': sale_id,
                'sale_id': sale_id,
                'folio': folio,
                'operation_id': operation_id,
                'reservation_id': reservation_id or None,
                'reservation_confirmed': reservation_confirmed,
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero': user,
                'subtotal': round(float(subtotal), 2),
                'descuento': round(float(discount), 2),
                'total': round(float(total_a_pagar), 2),
                'total_final': round(float(total_a_pagar), 2),
                'totales': {
                    'subtotal': round(float(subtotal), 2),
                    'descuento': round(float(discount), 2),
                    'total_final': round(float(total_a_pagar), 2),
                },
                'pago': amount_paid_real,
                'cambio': self._calculate_change(payment_method, payment_breakdown, total_a_pagar),
                'items': carrito_final,
                'puntos_ganados': (loyalty_result or {}).get('puntos_ganados'),
                'puntos_totales': (loyalty_result or {}).get('puntos_totales'),
                'raffle_tickets_snapshot': raffle_tickets_snapshot,
                'raffle_tickets_lines': [f"🎟️ Rifas/Sorteos\nRifa: {t.get('raffle','')}\nBoletos: {t.get('numero_boleto','')}" for t in (raffle_tickets_snapshot or [])],
            }
            template_html = self.config_service.get('ticket_template_html')
            if not template_html:
                raise ValueError("ticket_template_html not configured")
            ticket_final_html = self.ticket_template_engine.generar_ticket(
                template_html, datos_venta, mensaje_psicologico="🐔 ¡Gracias por tu compra!"
            )
        except Exception as e:
            logger.warning("No se pudo generar el ticket HTML: %s", e)

        _pm = self._normalize_payment_method(payment_method)
        ticket_payload = dict(datos_venta)
        ticket_payload["venta_id"] = sale_id
        ticket_payload["sale_id"] = sale_id
        ticket_payload["operation_id"] = operation_id
        ticket_payload["reservation_id"] = reservation_id or None
        ticket_payload["reservation_confirmed"] = reservation_confirmed
        ticket_payload["folio"] = str(folio)
        ticket_payload["items"] = list(carrito_final)
        ticket_payload["total"] = round(float(total_a_pagar), 2)
        ticket_payload["total_final"] = round(float(total_a_pagar), 2)
        ticket_payload["totales"] = {
            "subtotal": round(float(subtotal), 2),
            "descuento": round(float(discount), 2),
            "total_final": round(float(total_a_pagar), 2),
        }
        ticket_payload["pago"] = {
            "forma_pago": _pm,
            "total_pagado": round(sum(float(v or 0.0) for v in payment_breakdown.values()), 2),
            "efectivo_recibido": payment_breakdown["efectivo"],
            "tarjeta": payment_breakdown["tarjeta"],
            "transferencia": payment_breakdown["transferencia"],
            "credito": payment_breakdown["credito"],
            "mercado_pago": payment_breakdown["mercado_pago"],
            "cambio": self._calculate_change(_pm, payment_breakdown, total_a_pagar),
            "saldo_credito": round(float(total_a_pagar), 2) if _pm in {"Credito", "Crédito"} else 0.0,
            "amount_paid": amount_paid_real,
            "amount_paid_real": amount_paid_real,
            "lineas": payment_breakdown,
            "breakdown": payment_breakdown,
        }
        ticket_payload["loyalty"] = {
            "cliente_id": client_id,
            "puntos_canjeados": int(loyalty_redemption_pts or 0),
            "descuento_puntos": float(loyalty_discount or 0.0),
            "puntos_ganados": (loyalty_result or {}).get("puntos_ganados"),
            "puntos_totales": (loyalty_result or {}).get("puntos_totales"),
            "nivel": (loyalty_result or {}).get("nivel"),
            "available": bool((loyalty_result or {}).get("available", False)),
            "mensaje": str((loyalty_result or {}).get("mensaje", "") or ""),
            "operation_id": operation_id,
        }
        raffle_ticket_print_jobs = self._print_raffle_tickets_after_sale(raffle_tickets_snapshot, sale_id)
        ticket_payload["raffle_ticket_print_jobs"] = raffle_ticket_print_jobs
        if return_details:
            return {
                "ok": True,
                "venta_id": int(sale_id or 0),
                "folio": str(folio),
                "operation_id": str(operation_id),
                "subtotal": round(float(subtotal), 2),
                "descuento_total": round(float(discount), 2),
                "total": round(float(total_a_pagar), 2),
                "items": carrito_final,
                "payment": ticket_payload["pago"],
                "loyalty": ticket_payload["loyalty"],
                "ticket_payload": ticket_payload,
                "ticket_html": ticket_final_html or "",
                "raffle_tickets_snapshot": raffle_tickets_snapshot,
                "raffle_ticket_print_jobs": raffle_ticket_print_jobs,
                "warnings": [],
                "error": "",
            }
        return folio, ticket_final_html



    def _calculate_change(self, payment_method: str, payment_lines: dict, total: float) -> float:
        method = self._normalize_payment_method(payment_method)
        total = round(float(total or 0.0), 2)
        lines = dict(payment_lines or {})
        if method == "Efectivo":
            return round(max(float(lines.get("efectivo", 0.0) or 0.0) - total, 0.0), 2)
        if method in {"Pago Mixto", "Mixto"}:
            paid = (
                float(lines.get("efectivo", 0.0) or 0.0)
                + float(lines.get("tarjeta", 0.0) or 0.0)
                + float(lines.get("transferencia", 0.0) or 0.0)
            )
            return round(max(paid - total, 0.0), 2)
        return 0.0



    def _build_payment_breakdown(self, payment_method: str, total: float, amount_paid: float, payment_breakdown: dict | None = None) -> dict:
        method = self._normalize_payment_method(payment_method)
        total = round(float(total or 0.0), 2)
        amount_paid = round(float(amount_paid or 0.0), 2)
        lineas = {
            "efectivo": 0.0,
            "tarjeta": 0.0,
            "transferencia": 0.0,
            "credito": 0.0,
            "mercado_pago": 0.0,
        }
        allowed_methods = {"Efectivo", "Tarjeta", "Transferencia", "Credito", "Crédito", "Mercado Pago", "Pago Mixto", "Mixto"}
        if method not in allowed_methods:
            raise ValueError(f"Método de pago desconocido: {method}")
        aliases = {
            "efectivo": "efectivo",
            "cash": "efectivo",
            "tarjeta": "tarjeta",
            "card": "tarjeta",
            "monto_tarjeta_mixto": "tarjeta",
            "transferencia": "transferencia",
            "transfer": "transferencia",
            "credito": "credito",
            "crédito": "credito",
            "saldo_credito": "credito",
            "mercado_pago": "mercado_pago",
            "mercado pago": "mercado_pago",
        }
        if payment_breakdown:
            for raw_key, raw_value in payment_breakdown.items():
                key = aliases.get(str(raw_key).strip().lower())
                if key is None:
                    raise ValueError(f"Método de pago desconocido en desglose: {raw_key}")
                lineas[key] += round(float(raw_value or 0.0), 2)
            return lineas
        if method == "Efectivo":
            lineas["efectivo"] = amount_paid
        elif method == "Tarjeta":
            lineas["tarjeta"] = total
        elif method == "Transferencia":
            lineas["transferencia"] = total
        elif method in {"Crédito", "Credito"}:
            lineas["credito"] = total
        elif method == "Mercado Pago":
            lineas["mercado_pago"] = total
        elif method in {"Mixto", "Pago Mixto"}:
            raise ValueError("Pago mixto requiere payment_breakdown explícito.")
        return lineas

    def execute_sale_result(self, branch_id: int, user: str, items: list, payment_method: str,
                            amount_paid: float, client_id: int = None, client_phone: str = None,
                            client_level: str = 'bronce', discount: float = 0.0, notes: str = "",
                            loyalty_redemption_pts: int = 0, payment_breakdown: dict | None = None,
                            reservation_id: int | None = None, operation_id: str | None = None):
        from core.services.sales.sale_execution_result import (
            SaleExecutionItem, SaleExecutionResult, SaleLoyaltyResult, SalePaymentResult,
        )

        warnings = []
        details = self._execute_sale_core(
            branch_id=branch_id, user=user, items=items, payment_method=payment_method,
            amount_paid=amount_paid, client_id=client_id, client_phone=client_phone,
            client_level=client_level, discount=discount, notes=notes,
            loyalty_redemption_pts=loyalty_redemption_pts,
            return_details=True,
            payment_breakdown=payment_breakdown,
            reservation_id=reservation_id,
            operation_id=operation_id,
        )
        if not details.get("operation_id"):
            warnings.append("operation_id no disponible en el resultado interno de venta")
        execution_items = [
            SaleExecutionItem(
                product_id=int(d.get("product_id", 0)),
                nombre=str(d.get("nombre", d.get("name", "")) or ""),
                cantidad=float(d.get("qty", d.get("cantidad", 0.0)) or 0.0),
                precio_unitario=float(d.get("unit_price", d.get("precio_unitario", 0.0)) or 0.0),
                subtotal=round(float(d.get("qty", d.get("cantidad", 0.0)) or 0.0) * float(d.get("unit_price", d.get("precio_unitario", 0.0)) or 0.0), 2),
                descuento=0.0,
                total=round(float(d.get("qty", d.get("cantidad", 0.0)) or 0.0) * float(d.get("unit_price", d.get("precio_unitario", 0.0)) or 0.0), 2),
                es_compuesto=int(d.get("es_compuesto", 0) or 0),
            ) for d in (details.get("items") or [])
        ]
        payment = SalePaymentResult(
            forma_pago=str((details.get("payment") or {}).get("forma_pago", "")),
            total_pagado=float((details.get("payment") or {}).get("total_pagado", 0.0) or 0.0),
            efectivo_recibido=float((details.get("payment") or {}).get("efectivo_recibido", 0.0) or 0.0),
            tarjeta=float((details.get("payment") or {}).get("tarjeta", 0.0) or 0.0),
            transferencia=float((details.get("payment") or {}).get("transferencia", 0.0) or 0.0),
            credito=float((details.get("payment") or {}).get("credito", 0.0) or 0.0),
            mercado_pago=float((details.get("payment") or {}).get("mercado_pago", 0.0) or 0.0),
            cambio=float((details.get("payment") or {}).get("cambio", 0.0) or 0.0),
            saldo_credito=float((details.get("payment") or {}).get("saldo_credito", 0.0) or 0.0),
            lineas=dict((details.get("payment") or {}).get("lineas", {}) or {}),
            amount_paid_real=float((details.get("payment") or {}).get("amount_paid_real", (details.get("payment") or {}).get("amount_paid", 0.0)) or 0.0),
        )
        loy_raw = details.get("loyalty") or {}
        loyalty = SaleLoyaltyResult(
            cliente_id=loy_raw.get("cliente_id", client_id),
            puntos_canjeados=int(loy_raw.get("puntos_canjeados", 0) or 0),
            descuento_puntos=float(loy_raw.get("descuento_puntos", 0.0) or 0.0),
            puntos_ganados=loy_raw.get("puntos_ganados"),
            puntos_totales=loy_raw.get("puntos_totales"),
            nivel=loy_raw.get("nivel"),
            mensaje=str(loy_raw.get("mensaje", "") or ""),
            operation_id=str(loy_raw.get("operation_id", details.get("operation_id", "")) or ""),
            available=bool(loy_raw.get("available", False)),
        )
        return SaleExecutionResult(
            ok=bool(details.get("ok", True)),
            venta_id=int(details.get("venta_id", 0) or 0),
            folio=str(details.get("folio", "")),
            operation_id=str(details.get("operation_id", "") or ""),
            subtotal=float(details.get("subtotal", 0.0) or 0.0),
            descuento_total=float(details.get("descuento_total", 0.0) or 0.0),
            total=float(details.get("total", 0.0) or 0.0),
            items=execution_items,
            payment=payment,
            loyalty=loyalty,
            ticket_payload=dict(details.get("ticket_payload", {}) or {}),
            ticket_html=str(details.get("ticket_html", "") or ""),
            warnings=list(details.get("warnings", []) or []) + warnings,
            error=str(details.get("error", "") or ""),
        )

    def execute_sale(self, branch_id: int, user: str, items: list, payment_method: str,
                     amount_paid: float, client_id: int = None, client_phone: str = None,
                     client_level: str = 'bronce', discount: float = 0.0, notes: str = "",
                     loyalty_redemption_pts: int = 0, reservation_id: int | None = None) -> tuple:
        """
        Adapter legacy: mantiene contrato histórico (folio, ticket_html).
        La fuente real es execute_sale_result().
        """
        result = self.execute_sale_result(
            branch_id=branch_id,
            user=user,
            items=items,
            payment_method=payment_method,
            amount_paid=amount_paid,
            client_id=client_id,
            client_phone=client_phone,
            client_level=client_level,
            discount=discount,
            notes=notes,
            loyalty_redemption_pts=loyalty_redemption_pts,
            reservation_id=reservation_id,
        )
        return result.folio, result.ticket_html

    # ── Compatibilidad legacy (tests v9 + módulos antiguos) ─────────────────
    def procesar_venta(self, items, datos_pago, usuario=None, **_kw):
        """
        API legacy bloqueada por defecto.

        Fecha de eliminación planificada: 2026-06-30.
        Ruta oficial: ProcesarVentaUC.ejecutar() -> SalesService.execute_sale_result().
        """
        if not _legacy_flag_enabled(ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA):
            logger.error(
                "SalesService.procesar_venta legacy bloqueado; usa ProcesarVentaUC -> "
                "execute_sale_result. Eliminación planificada: %s. Para tests legacy aislados: %s=1",
                LEGACY_SALES_REMOVAL_DATE,
                ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA,
            )
            raise RuntimeError(
                "SalesService.procesar_venta() legacy está bloqueado por seguridad. "
                "Ruta oficial: ProcesarVentaUC.ejecutar() -> SalesService.execute_sale_result(). "
                f"Eliminación planificada: {LEGACY_SALES_REMOVAL_DATE}. "
                f"Para pruebas legacy aisladas use {ALLOW_LEGACY_SALES_SERVICE_PROCESAR_VENTA}=1."
            )
        from core.services.sales.unified_sales_service import (
            ResultadoVenta, CarritoVacioError, PagoInsuficienteError, StockError, VentaError
        )

        if not items:
            raise CarritoVacioError("El carrito está vacío.")

        usr = usuario or "cajero"
        payment_method = getattr(datos_pago, "forma_pago", "Efectivo")
        payment_breakdown = dict(
            getattr(datos_pago, "payment_breakdown", None)
            or getattr(datos_pago, "pago_mixto", None)
            or getattr(datos_pago, "lineas", None)
            or {}
        )
        if getattr(datos_pago, "amount_paid_real", None) is not None:
            amount_paid = float(getattr(datos_pago, "amount_paid_real") or 0.0)
        elif payment_breakdown:
            amount_paid = float(sum(float(v or 0.0) for v in payment_breakdown.values()))
        else:
            amount_paid = float(getattr(datos_pago, "efectivo_recibido", 0.0) or 0.0)
        client_id = getattr(datos_pago, "cliente_id", None)
        discount = float(getattr(datos_pago, "descuento_global", 0.0) or 0.0)

        items_payload = []
        total_estimado = 0.0
        for it in items:
            qty = float(getattr(it, "cantidad", 0.0) or 0.0)
            pu = float(getattr(it, "precio_unitario", getattr(it, "precio_unit", 0.0)) or 0.0)
            pid = int(getattr(it, "producto_id", 0) or 0)
            nm = getattr(it, "nombre", "")
            total_estimado += qty * pu
            items_payload.append({
                "product_id": pid,
                "qty": qty,
                "unit_price": pu,
                "name": nm,
                "es_compuesto": 0,
            })

        try:
            ventas_cols = {r[1] for r in self.db.execute("PRAGMA table_info(ventas)").fetchall()}
        except Exception as exc:
            logger.warning("No se pudo inspeccionar esquema de ventas; ruta legacy mínima bloqueada: %s", exc)
            raise VentaError("No se pudo validar esquema de ventas para procesar venta.") from exc
        if "operation_id" not in ventas_cols or "observations" not in ventas_cols:
            return self._procesar_venta_legacy_minimal(
                items_payload=items_payload,
                payment_method=payment_method,
                amount_paid=amount_paid,
                client_id=client_id,
                discount=discount,
                usuario=usr,
            )

        try:
            rich = self.execute_sale_result(
                branch_id=1,
                user=usr,
                items=items_payload,
                payment_method=payment_method,
                amount_paid=amount_paid,
                payment_breakdown=payment_breakdown,
                client_id=client_id,
                discount=discount,
            )
            folio, ticket_html = rich.folio, rich.ticket_html
            row = self.db.execute(
                "SELECT id,total,cambio FROM ventas WHERE folio=? ORDER BY id DESC LIMIT 1",
                (folio,)
            ).fetchone()
            venta_id = int(row["id"]) if row else 0
            total_real = float(row["total"]) if row else round(max(total_estimado - discount, 0.0), 2)
            cambio = float(row["cambio"]) if row else max(amount_paid - total_real, 0.0)
            return ResultadoVenta(
                venta_id=venta_id,
                folio=folio,
                total=total_real,
                cambio=cambio,
                ticket_data={
                    "folio": folio,
                    "total": total_real,
                    "items": items_payload,
                    "ticket_html": ticket_html or "",
                },
            )
        except Exception as exc:
            # Fallback legacy (SQLite mínimo de tests/instalaciones antiguas)
            if "operation_id" in str(exc).lower() or "observations" in str(exc).lower():
                return self._procesar_venta_legacy_minimal(
                    items_payload=items_payload,
                    payment_method=payment_method,
                    amount_paid=amount_paid,
                    client_id=client_id,
                    discount=discount,
                    usuario=usr,
                )
            msg = str(exc).lower()
            if "carrito" in msg and ("vacío" in msg or "vacio" in msg):
                raise CarritoVacioError(str(exc)) from exc
            if "monto pagado" in msg or "menor al total" in msg:
                raise PagoInsuficienteError(str(exc)) from exc
            if "stock" in msg or "insuficiente" in msg:
                raise StockError(str(exc)) from exc
            raise VentaError(str(exc)) from exc

    def anular_venta(self, venta_id, motivo="", usuario_id=None):
        """Cancela una venta: revierte stock via apply_movement y genera asiento contable."""
        from core.services.sales.unified_sales_service import VentaError
        from core.db.connection import transaction as _txn
        from core.services.inventory.unified_inventory_service import UnifiedInventoryService as _UIS
        try:
            row = self.db.execute(
                "SELECT id, folio, total, sucursal_id, estado FROM ventas WHERE id=?",
                (int(venta_id),)
            ).fetchone()
            if not row:
                raise VentaError(f"VENTA_NO_ENCONTRADA: id={venta_id}")
            if str(row["estado"]).lower() in ("cancelada", "anulada"):
                raise VentaError(f"VENTA_YA_CANCELADA: id={venta_id}")

            folio = row["folio"] or str(venta_id)
            total = float(row["total"] or 0)
            sucursal_id = int(row["sucursal_id"] or 1)
            usuario = str(usuario_id or "sistema")

            detalles = self.db.execute(
                "SELECT producto_id, cantidad FROM detalles_venta WHERE venta_id=?",
                (int(venta_id),)
            ).fetchall()

            with _txn(self.db):
                for d in detalles:
                    pid = int(d["producto_id"])
                    qty = float(d["cantidad"] or 0)
                    if qty <= 0:
                        continue
                    _UIS(self.db, sucursal_id=sucursal_id, usuario=usuario).process_movement(
                        product_id=pid,
                        quantity=qty,
                        movement_type="DEVOLUCION_ANULACION",
                        reference=folio,
                        metadata={"notas": f"Anulación venta {folio}: {motivo}"},
                    )

                # Marcar venta como cancelada
                try:
                    self.db.execute(
                        "UPDATE ventas SET estado='cancelada', notas=? WHERE id=?",
                        (motivo, int(venta_id))
                    )
                except Exception as exc:
                    logger.warning("Cancelación de venta sin columna notas; usando fallback estado-only venta_id=%s: %s", venta_id, exc)
                    self.db.execute(
                        "UPDATE ventas SET estado='cancelada' WHERE id=?",
                        (int(venta_id),)
                    )

                # Asiento contable (debe=ventas ↔ haber=inventario)
                if self.finance_service and total > 0:
                    try:
                        self.finance_service.registrar_asiento(
                            debe="ventas",
                            haber="inventario",
                            concepto=f"Anulación venta {folio}: {motivo}",
                            monto=total,
                            modulo="VENTAS",
                            referencia_id=int(venta_id),
                            usuario_id=usuario_id,
                            sucursal_id=sucursal_id,
                            evento="VENTA_ANULADA",
                        )
                    except Exception as _fe:
                        import logging as _log
                        _log.getLogger(__name__).error(
                            "anular_venta asiento falló venta_id=%s: %s", venta_id, _fe)

        except VentaError:
            raise
        except Exception as exc:
            raise VentaError(str(exc)) from exc

    def _procesar_venta_legacy_minimal(
        self, *, items_payload, payment_method, amount_paid, client_id, discount, usuario
    ):
        if not _legacy_flag_enabled(ALLOW_LEGACY_MINIMAL_SALE_WRITE):
            logger.error(
                "_procesar_venta_legacy_minimal bloqueado; escribe ventas fuera de "
                "execute_sale_result. Eliminación planificada: %s. Para tests legacy aislados: %s=1",
                LEGACY_SALES_REMOVAL_DATE,
                ALLOW_LEGACY_MINIMAL_SALE_WRITE,
            )
            raise RuntimeError(
                "_procesar_venta_legacy_minimal() está bloqueado por seguridad: "
                "escribe ventas/caja/inventario fuera de SalesService.execute_sale_result(). "
                f"Eliminación planificada: {LEGACY_SALES_REMOVAL_DATE}. "
                f"Para pruebas legacy aisladas use {ALLOW_LEGACY_MINIMAL_SALE_WRITE}=1."
            )
        from datetime import datetime
        from core.services.sales.unified_sales_service import (
            ResultadoVenta, PagoInsuficienteError, StockError, VentaError
        )
        subtotal = round(sum(float(i["qty"]) * float(i["unit_price"]) for i in items_payload), 2)
        total = round(max(subtotal - float(discount or 0), 0.0), 2)
        try:
            payment_lines = self._build_payment_breakdown(payment_method, total, amount_paid, None)
            amount_paid_real = self._amount_paid_for_storage(payment_method, payment_lines, total)
            self._validate_payment(payment_method, total, payment_lines, client_id=client_id)
        except ValueError as exc:
            raise PagoInsuficienteError(str(exc)) from exc

        try:
            for i in items_payload:
                row = self.db.execute("SELECT existencia FROM productos WHERE id=?", (i["product_id"],)).fetchone()
                existencia = float((row["existencia"] if row else 0) or 0)
                if existencia < float(i["qty"]):
                    raise StockError(f"Stock insuficiente para producto {i['product_id']}")

            folio = self._generate_unique_sale_folio()
            cambio = self._calculate_change(payment_method, payment_lines, total)
            cur = self.db.execute(
                """
                INSERT INTO ventas(
                    folio, sucursal_id, usuario, cliente_id, subtotal, descuento, total,
                    forma_pago, efectivo_recibido, cambio, estado, fecha
                ) VALUES (?,1,?,?,?,?,?,?,?,?, 'completada', datetime('now'))
                """,
                (folio, usuario, client_id, subtotal, float(discount or 0), total,
                 payment_method, amount_paid_real, cambio)
            )
            venta_id = int(cur.lastrowid)

            for i in items_payload:
                qty = float(i["qty"])
                pu = float(i["unit_price"])
                self.db.execute(
                    """
                    INSERT INTO detalles_venta(venta_id, producto_id, cantidad, precio_unitario, descuento, subtotal)
                    VALUES (?,?,?,?,0,?)
                    """,
                    (venta_id, i["product_id"], qty, pu, round(qty * pu, 2))
                )
                self.db.execute(
                    "UPDATE productos SET existencia = COALESCE(existencia,0) - ? WHERE id=?",
                    (qty, i["product_id"])
                )

            self.db.execute(
                "INSERT INTO movimientos_caja(tipo, monto, descripcion, usuario, venta_id, forma_pago) VALUES ('INGRESO',?,?,?,?,?)",
                (total, f"Ingreso por venta {folio}", usuario, venta_id, payment_method)
            )
            if client_id:
                puntos = int(total // 10)
                self.db.execute("UPDATE clientes SET puntos = COALESCE(puntos,0) + ? WHERE id=?", (puntos, client_id))

            self.db.commit()
            return ResultadoVenta(
                venta_id=venta_id,
                folio=folio,
                total=total,
                cambio=cambio,
                ticket_data={"folio": folio, "total": total, "items": items_payload},
            )
        except (PagoInsuficienteError, StockError):
            try:
                self.db.rollback()
            except Exception as rb_exc:
                logger.warning("Rollback legacy de venta falló tras error controlado: %s", rb_exc)
            raise
        except Exception as exc:
            try:
                self.db.rollback()
            except Exception as rb_exc:
                logger.warning("Rollback legacy de venta falló: %s", rb_exc)
            raise VentaError(str(exc)) from exc
