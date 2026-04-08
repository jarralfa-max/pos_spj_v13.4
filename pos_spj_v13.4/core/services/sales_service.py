from core.services.auto_audit import audit_write

# core/services/sales_service.py
import uuid
import logging
from datetime import datetime

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
                 growth_engine=None, notification_service=None):
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

    def execute_sale(self, branch_id: int, user: str, items: list, payment_method: str, 
                     amount_paid: float, client_id: int = None, client_phone: str = None, 
                     client_level: str = 'bronce', discount: float = 0.0, notes: str = "") -> tuple:
        """
        Ejecuta la venta completa y devuelve el Folio y el Ticket HTML.
        
        :param items: Lista de diccionarios [{'product_id': 1, 'qty': 1.12, 'unit_price': 100, 'es_compuesto': 0, 'name': 'Pollo'}, ...]
        """
        operation_id = str(uuid.uuid4())
        
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

        # Validamos el pago
        if amount_paid < total_a_pagar and payment_method != 'Credito':
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

            # B. Procesar Carrito e Inventario
            for item in carrito_final:
                # Guardar detalle de la venta
                self.sales_repo.save_sale_item(
                    sale_id=sale_id,
                    product_id=item['product_id'],
                    qty=item['qty'],
                    unit_price=item['unit_price'],
                    subtotal=(item['qty'] * item['unit_price'])
                )

                # Descuento Inteligente de Inventario
                if item.get('es_compuesto', 0) == 1:
                    # Composite product: deduct ingredients using recipe
                    recipe_items = self.recipe_repo.get_recipe_items_by_product(item['product_id'])
                    if not recipe_items:
                        raise ValueError(f"El combo ID {item['product_id']} no tiene receta. "
                                         f"Crea la receta en el módulo Recetas.")

                    for sub_item in recipe_items:
                        tipo_receta = sub_item.get('tipo_receta', 'combinacion')
                        rend_pct    = float(sub_item.get('rendimiento_pct') or 0)
                        cantidad    = float(sub_item.get('cantidad') or 0)

                        if rend_pct > 0:
                            # Percentage-based (subproducto type): qty = sale_qty * rendimiento/100
                            qty_to_deduct = float(item['qty']) * rend_pct / 100.0
                        elif cantidad > 0:
                            # Fixed-quantity (combinacion type): qty = cantidad * sale_qty
                            qty_to_deduct = float(item['qty']) * cantidad
                        else:
                            import logging as _lg
                            _lg.getLogger(__name__).warning(
                                "Recipe component pid=%s has no qty/rendimiento — skipped",
                                sub_item['component_product_id'])
                            continue

                        if qty_to_deduct <= 0:
                            continue

                        self.inventory_service.deduct_stock(
                            product_id=sub_item['component_product_id'],
                            branch_id=branch_id,
                            qty=round(qty_to_deduct, 4),
                            operation_id=operation_id,
                            reference_type="VENTA_COMBO",
                            reference_id=str(sale_id),
                            user=user,
                            notes=f"Consumo receta {folio} ({tipo_receta})"
                        )
                else:
                    # Producto Simple / Por Peso: Descuento directo
                    self.inventory_service.deduct_stock(
                        product_id=item['product_id'],
                        branch_id=branch_id,
                        qty=item['qty'],
                        operation_id=operation_id,
                        reference_type="VENTA",
                        reference_id=str(sale_id),
                        user=user,
                        notes=f"Salida por venta {folio}"
                    )
                    # FIFO de lotes/caducidades (falla silenciosamente)
                    if self._lote_svc:
                        try:
                            self._lote_svc.consumir_fifo(
                                producto_id=item['product_id'],
                                cantidad=float(item['qty']),
                                referencia=f"VENTA-{folio}",
                                usuario=user
                            )
                        except Exception as _le:
                            import logging
                            logging.getLogger('spj.sales').debug(
                                "FIFO lotes: %s", _le)

            # C. Automatización Financiera (Ingreso a Caja)
            if payment_method != "Credito" and total_a_pagar > 0:
                self.finance_service.register_income(
                    amount=total_a_pagar,
                    category="VENTAS_MOSTRADOR",
                    description=f"Ingreso por venta {folio}",
                    payment_method=payment_method,
                    branch_id=branch_id,
                    user=user,
                    operation_id=operation_id,
                    reference_id=sale_id
                )

            # D. Sincronización Offline-First (Nube)
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

            # 🛡️ CIERRE EXITOSO DE BD: Si llegamos aquí, todo es consistente
            self.db.execute(f"RELEASE SAVEPOINT {_sp}")
            logger.info(f"Venta {folio} procesada con éxito. Operación: {operation_id}")

            # Notificar al EventBus (async_ para no bloquear al cajero)
            try:
                from core.events.event_bus import get_bus, VENTA_COMPLETADA
                get_bus().publish(VENTA_COMPLETADA, {
                    "venta_id":   sale_id,
                    "folio":      folio,
                    "branch_id":  branch_id,
                    "total":      total_a_pagar,
                    "usuario":    user,
                    "cliente_id": client_id,
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
        # 3. POST-PROCESAMIENTO: Fidelidad, Ticket y Notificaciones
        # (Esto se hace fuera de la transacción para no bloquear la BD)
        # =========================================================
        mensaje_psico = "🐔 ¡Gracias por tu compra!"
        
        if client_id and total_a_pagar > 0:
            try:
                # Use GrowthEngine if available (prevents double-awarding)
                # Legacy LoyaltyService only as fallback when GrowthEngine is not wired
                ge_active = getattr(self, 'growth_engine', None) is not None
                if not ge_active and self.feature_flag_service.is_enabled('loyalty', branch_id):
                    lealtad_resultado = self.loyalty_service.process_loyalty_for_sale(
                        client_id, total_a_pagar, branch_id  # total_a_pagar = net after discounts
                    )
                    mensaje_psico = lealtad_resultado.get('mensaje', mensaje_psico)
            except Exception as e:
                logger.warning("Error procesando lealtad (Venta completada): %s", e)

        # Generar Ticket
        ticket_final_html = ""
        try:
            datos_venta = {
                'folio': folio, 'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero': user, 'total': total_a_pagar, 'pago': amount_paid,
                'cambio': (amount_paid - total_a_pagar) if payment_method == 'Efectivo' else 0,
                'items': carrito_final
            }
            template_html = self.config_service.get('ticket_template_html') 
            ticket_final_html = self.ticket_template_engine.generar_ticket(
                template_html, datos_venta, mensaje_psicologico=mensaje_psico
            )
        except Exception as e:
            logger.warning("No se pudo generar el ticket HTML: %s", e)

        # Notificación completa al cliente (ticket + gamificación + branding)
        if client_phone:
            try:
                # Obtener datos de fidelidad actualizados
                puntos_ganados = 0
                puntos_total   = 0
                nivel_actual   = client_level or "bronce"
                nivel_anterior = client_level or "bronce"
                # Registrar comisión del cajero
                if hasattr(self, '_comisiones_svc') and self._comisiones_svc:
                    try:
                        self._comisiones_svc.registrar_comision(
                            usuario=user,
                            venta_id=sale_id,
                            total_venta=float(total_a_pagar),
                            sucursal_id=branch_id
                        )
                    except Exception as _e:
                        logger.debug("Nombre cliente %s: %s", client_id, _e)

                if hasattr(self, 'loyalty_service') and client_id:
                    try:
                        pts = self.loyalty_service.get_puntos(client_id)
                        puntos_total = pts.get("puntos_totales", 0)
                        puntos_ganados = pts.get("puntos_ganados", 0)
                        nivel_actual   = pts.get("nivel", nivel_actual)
                    except Exception:
                        pass

                # GrowthEngine (estrellas, metas, misiones)
                # Get client name first (needed by GrowthEngine below)
                nombre_cliente = "Cliente"
                if client_id:
                    try:
                        _row_nc = self.db.execute(
                            "SELECT nombre FROM clientes WHERE id=?", (client_id,)
                        ).fetchone()
                        if _row_nc: nombre_cliente = _row_nc[0]
                    except Exception:
                        pass

                ge = getattr(self, 'growth_engine', None)
                if ge and client_id:
                    try:
                        ge_result = ge.procesar_venta(
                            cliente_id = client_id,
                            ticket_id  = sale_id,
                            cajero_id  = 0,
                            subtotal   = total_a_pagar,
                            telefono   = client_phone or "",
                            nombre     = nombre_cliente,
                        )
                        estrellas = ge_result.get("estrellas_ganadas", 0)
                        if estrellas > 0:
                            puntos_ganados = puntos_ganados + estrellas
                            puntos_total   = ge.saldo_cliente(client_id)
                        if ge_result.get("misiones_completadas"):
                            logger.info("Misiones completadas: %s", ge_result["misiones_completadas"])
                    except Exception as ge_err:
                        logger.debug("GrowthEngine post-venta: %s", ge_err)

                # nombre_cliente already fetched above

                # Usar NotificationService si está disponible, WhatsApp directo si no
                if hasattr(self, 'notification_service') and self.notification_service:
                    self.notification_service.notificar_venta_cliente(
                        telefono       = client_phone,
                        nombre         = nombre_cliente,
                        folio          = folio,
                        total          = total_a_pagar,
                        items          = carrito_final,
                        puntos_ganados = puntos_ganados,
                        puntos_total   = puntos_total,
                        nivel_actual   = nivel_actual,
                        nivel_anterior = nivel_anterior,
                        branch_id      = branch_id,
                    )
                elif self.whatsapp_service:
                    self.whatsapp_service.send_message(branch_id, client_phone, mensaje_psico)
            except Exception as e:
                logger.warning("notificacion_cliente: %s", e)

        return folio, ticket_final_html