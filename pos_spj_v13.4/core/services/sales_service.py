from core.services.auto_audit import audit_write

# core/services/sales_service.py
import uuid
import logging
from datetime import datetime

from core.events.domain_events import SALE_ITEMS_PROCESS
import json
from core.events.event_factory import make_sale_payload
from core.services.sales_fulfillment_service import SaleFulfillmentService

logger = logging.getLogger(__name__)

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
                 customer_service=None):
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
        except Exception:
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
        self._fulfillment = SaleFulfillmentService(db_conn)

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
            except Exception:
                # Si no se puede validar unicidad por esquema/tabla, retornar igual
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

    def create_pending_payment_sale(self, branch_id: int, user: str, items: list,
                                    client_id: int = None, notes: str = "",
                                    total: float = 0.0) -> dict:
        """
        Fase 7: crea una intención de pago MercadoPago sin ejecutar venta definitiva.
        No descuenta stock, no registra caja, no publica VENTA_COMPLETADA.
        """
        folio = self._generate_unique_sale_folio()
        subtotal = total or sum(float(i.get("qty", 0)) * float(i.get("unit_price", 0)) for i in (items or []))
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS pending_sales_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT UNIQUE NOT NULL,
                payload_json TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente_pago',
                payment_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                confirmed_at TEXT
            )
        """)
        payload = {
            "branch_id": branch_id,
            "user": user,
            "client_id": client_id,
            "items": items or [],
            "total": round(float(subtotal), 2),
            "notes": notes or "",
        }
        self.db.execute(
            "INSERT OR REPLACE INTO pending_sales_intents(folio, payload_json, estado) VALUES (?,?, 'pendiente_pago')",
            (folio, json.dumps(payload)),
        )
        try:
            self.db.commit()
        except Exception:
            pass
        return {
            "ok": True,
            "estado": "pendiente_pago",
            "folio": folio,
            "branch_id": branch_id,
            "usuario": user,
            "client_id": client_id,
            "subtotal": round(float(subtotal), 2),
            "notes": notes or "",
            "items": items or [],
            "todo": "Implementar confirmación por webhook para convertir a venta definitiva.",
        }

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
        data = json.loads(payload_json or "{}")
        total = float(data.get("total", 0.0))
        items = data.get("items") or []
        branch_id = int(data.get("branch_id", 1))
        user = str(data.get("user", "sistema"))
        client_id = data.get("client_id")
        notes = str(data.get("notes", "")) + f" [MP payment_id={payment_id}]"
        folio_sale, ticket = self.execute_sale(
            branch_id=branch_id,
            user=user,
            items=items,
            payment_method="Mercado Pago",
            amount_paid=total,
            client_id=client_id,
            notes=notes,
        )
        self.db.execute(
            "UPDATE pending_sales_intents SET estado='confirmada', payment_id=?, confirmed_at=datetime('now') WHERE folio=?",
            (str(payment_id or ""), str(folio)),
        )
        try:
            self.db.commit()
        except Exception:
            pass
        return folio_sale, ticket

    def execute_sale(self, branch_id: int, user: str, items: list, payment_method: str,
                     amount_paid: float, client_id: int = None, client_phone: str = None,
                     client_level: str = 'bronce', discount: float = 0.0, notes: str = "",
                     loyalty_redemption_pts: int = 0) -> tuple:
        """
        Ejecuta la venta completa y devuelve el Folio y el Ticket HTML.
        
        :param items: Lista de diccionarios [{'product_id': 1, 'qty': 1.12, 'unit_price': 100, 'es_compuesto': 0, 'name': 'Pollo'}, ...]
        """
        operation_id = str(uuid.uuid4())

        # ── Normalizar método de pago (UI envía "Crédito" con acento; backend espera "Credito") ──
        try:
            from core.services.payment_normalization import normalize_payment_method as _npm
            payment_method = _npm(payment_method)
        except Exception:
            pass  # normalization is non-critical; proceed with original value

        # ── Normalizar claves de items (la UI puede usar distintos nombres) ──
        # UI envía: unit_price / qty / id
        # Servicios internos esperan: precio_unitario / cantidad / product_id
        _normalized = []
        for _it in items:
            _normalized.append({
                'product_id':    _it.get('product_id', _it.get('id', 0)),
                'qty':           float(_it.get('qty', _it.get('cantidad', 1))),
                'unit_price':    float(_it.get('unit_price', _it.get('precio_unitario', 0))),
                'precio_unitario': float(_it.get('unit_price', _it.get('precio_unitario', 0))),
                'cantidad':      float(_it.get('qty', _it.get('cantidad', 1))),
                'nombre':        _it.get('nombre', _it.get('name', '')),
                'unidad':        _it.get('unidad', 'pz'),
                'es_compuesto':  _it.get('es_compuesto', 0),
                'promo_nombre':  _it.get('promo_nombre', ''),
            })
        items = _normalized

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

        # ── Validación de crédito (si aplica) ────────────────────────────────
        from core.services.payment_normalization import is_credit_sale
        if is_credit_sale(payment_method) and client_id and self.customer_service:
            ok, msg = self.customer_service.validate_credit(client_id, total_a_pagar)
            if not ok:
                raise ValueError(msg)

        # Validamos el pago
        if amount_paid < total_a_pagar and not is_credit_sale(payment_method):
            raise ValueError(f"El monto pagado (${amount_paid:,.2f}) es menor al total a cobrar (${total_a_pagar:,.2f})")

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
                except Exception:
                    pass  # guardia no crítica

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
                amount_paid=amount_paid,
                operation_id=operation_id,
                notes=notes
            )

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
            #    SaleInventoryHandler y SaleFinanceHandler están registrados en wiring.py.
            #    Si no hay handlers activos (tests sin AppContainer), la emisión es no-op.
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
                operation_id=operation_id,
            )
            try:
                from core.events.event_bus import get_bus
                get_bus().publish(SALE_ITEMS_PROCESS, _sale_evt_payload, strict=True)
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
                red = self.loyalty_service.apply_redemption(
                    cliente_id=client_id,
                    venta_id=sale_id,
                    cajero_id=user,
                    subtotal=total_a_pagar,
                    puntos=loyalty_redemption_pts,
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
            loyalty_result = {"puntos_ganados": 0, "puntos_totales": 0, "nivel": "Bronce", "mensaje": ""}
            if client_id and self.loyalty_service:
                try:
                    loyalty_result = self.loyalty_service.process_loyalty_for_sale(
                        client_id=client_id,
                        total_sale=float(total_a_pagar),
                        branch_id=branch_id,
                        venta_id=sale_id,
                        usuario=str(user),
                    ) or loyalty_result
                except Exception as _lyl_aw_err:
                    logger.warning("loyalty accrual venta=%s: %s", sale_id, _lyl_aw_err)

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
                    "branch_id":     branch_id,
                    "sucursal_id":   branch_id,
                    "total":         total_a_pagar,
                    "usuario":       user,
                    "cliente_id":    client_id,
                    "payment_method": payment_method,
                    "loyalty_already_processed": True,
                    "loyalty_snapshot": loyalty_result,
                }, async_=True)
            except Exception as _eb_err:
                logger.debug("EventBus publish: %s", _eb_err)  # nunca cancela la venta

        except Exception as e:
            # Rollback to savepoint if still active
            if _sp:
                try: self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
                except Exception: pass
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
                'folio': folio, 'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero': user, 'total': total_a_pagar, 'pago': amount_paid,
                'cambio': (amount_paid - total_a_pagar) if payment_method == 'Efectivo' else 0,
                'items': carrito_final,
                'puntos_ganados': (loyalty_result or {}).get('puntos_ganados', 0),
                'puntos_totales': (loyalty_result or {}).get('puntos_totales', 0)
            }
            template_html = self.config_service.get('ticket_template_html')
            if not template_html:
                raise ValueError("ticket_template_html not configured")
            ticket_final_html = self.ticket_template_engine.generar_ticket(
                template_html, datos_venta, mensaje_psicologico="🐔 ¡Gracias por tu compra!"
            )
        except Exception as e:
            logger.warning("No se pudo generar el ticket HTML: %s", e)

        return folio, ticket_final_html

    # ── Compatibilidad legacy (tests v9 + módulos antiguos) ─────────────────
    def procesar_venta(self, items, datos_pago, usuario=None, **_kw):
        """
        API legacy compatible con UnifiedSalesService.
        Mantiene retrocompatibilidad sin romper `execute_sale`.
        """
        from core.services.sales.unified_sales_service import (
            ResultadoVenta, CarritoVacioError, PagoInsuficienteError, StockError, VentaError
        )

        if not items:
            raise CarritoVacioError("El carrito está vacío.")

        usr = usuario or "cajero"
        payment_method = getattr(datos_pago, "forma_pago", "Efectivo")
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
        except Exception:
            ventas_cols = set()
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
            folio, ticket_html = self.execute_sale(
                branch_id=1,
                user=usr,
                items=items_payload,
                payment_method=payment_method,
                amount_paid=amount_paid,
                client_id=client_id,
                discount=discount,
            )
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
                except Exception:
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
        from datetime import datetime
        from core.services.sales.unified_sales_service import (
            ResultadoVenta, PagoInsuficienteError, StockError, VentaError
        )
        subtotal = round(sum(float(i["qty"]) * float(i["unit_price"]) for i in items_payload), 2)
        total = round(max(subtotal - float(discount or 0), 0.0), 2)
        if payment_method.lower() not in {"tarjeta", "credito"}:
            # Hardening Fase 0: efectivo debe cubrir el total neto de la venta.
            if float(amount_paid or 0) < total:
                raise PagoInsuficienteError("El monto pagado es menor al total.")

        try:
            for i in items_payload:
                row = self.db.execute("SELECT existencia FROM productos WHERE id=?", (i["product_id"],)).fetchone()
                existencia = float((row["existencia"] if row else 0) or 0)
                if existencia < float(i["qty"]):
                    raise StockError(f"Stock insuficiente para producto {i['product_id']}")

            folio = self._generate_unique_sale_folio()
            cambio = round(max(float(amount_paid or 0) - total, 0.0), 2)
            cur = self.db.execute(
                """
                INSERT INTO ventas(
                    folio, sucursal_id, usuario, cliente_id, subtotal, descuento, total,
                    forma_pago, efectivo_recibido, cambio, estado, fecha
                ) VALUES (?,1,?,?,?,?,?,?,?,?, 'completada', datetime('now'))
                """,
                (folio, usuario, client_id, subtotal, float(discount or 0), total,
                 payment_method, float(amount_paid or 0), cambio)
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
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                self.db.rollback()
            except Exception:
                pass
            raise VentaError(str(exc)) from exc
