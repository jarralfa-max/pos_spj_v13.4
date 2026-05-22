
# core/services/purchase_service.py
import uuid
import logging

logger = logging.getLogger("spj.purchase_service")


class PurchaseService:
    """
    Orquestador principal del flujo de Compras.
    Automatiza la entrada de inventario y el registro financiero (salida de dinero/deuda)
    en una sola transacción segura.
    """
    
    def __init__(self, db_conn, purchase_repo, inventory_service, finance_service):
        # Inyección de dependencias: El orquestador conoce a sus "subordinados"
        self.db = db_conn
        self.purchase_repo = purchase_repo
        self.inventory_service = inventory_service
        self.finance_service = finance_service

    def register_purchase(self, provider_id: int, branch_id: int, user: str,
                          items: list, payment_method: str, amount_paid: float,
                          notes: str = "",
                          condicion_pago: str = "liquidado",
                          plazo_dias: int = 0,
                          moneda: str = "MXN",
                          tax_amount: float = 0.0) -> tuple:
        """
        Registra la compra, suma inventario y descuenta el dinero automáticamente.

        Returns (folio, finance_warnings) where finance_warnings is a list of
        non-fatal strings (empty on clean run).

        :param items: Lista de diccionarios [{'product_id': 1, 'qty': 100, 'unit_cost': 50.0}, ...]
        """
        # Generamos un ID único para rastrear todo este movimiento en conjunto
        operation_id = str(uuid.uuid4())
        finance_warnings: list[str] = []
        
        # Calculamos el subtotal físico y el total fiscal de la compra directa.
        subtotal_purchase = round(
            sum(item['qty'] * item['unit_cost'] for item in items), 2
        )
        tax_amount = round(float(tax_amount or 0), 2)
        total_purchase = round(subtotal_purchase + tax_amount, 2)
        
        # Determinamos si se pagó completa o quedó a crédito
        status = "completada" if amount_paid >= total_purchase else "credito"

        _sp = f"compra_{uuid.uuid4().hex[:8]}"
        _sp_released = False
        try:
            # Use SAVEPOINT (compatible with isolation_level=None / autocommit)
            self.db.execute(f"SAVEPOINT {_sp}")

            # 1. GUARDAR LA COMPRA (Cabecera y detalles en la BD)
            compra_id, folio = self.purchase_repo.create_purchase(
                provider_id=provider_id,
                branch_id=branch_id,
                user=user,
                subtotal=subtotal_purchase,
                tax=tax_amount,
                total=total_purchase,
                status=status,
                operation_id=operation_id,
                notes=notes,
                payment_method=payment_method,
                condicion_pago=condicion_pago,
                plazo_dias=plazo_dias,
                moneda=moneda,
            )
            
            # Guardar los renglones (productos) de la compra
            self.purchase_repo.save_purchase_items(compra_id, items)

            # 2. AUTOMATIZACIÓN DE INVENTARIO (event bus or direct fallback)
            from core.events.event_bus import get_bus
            from core.events.domain_events import PURCHASE_ITEMS_PROCESS
            _bus = get_bus()
            inv_errors = []
            if _bus.handler_count(PURCHASE_ITEMS_PROCESS) > 0:
                _bus.publish(PURCHASE_ITEMS_PROCESS, {
                    "branch_id":    branch_id,
                    "sucursal_id":  branch_id,
                    "operation_id": operation_id,
                    "compra_id":    compra_id,
                    "folio":        folio,
                    "user":         user,
                    "usuario":      user,
                    "items":        items,
                }, strict=True)
            else:
                for item in items:
                    try:
                        self.inventory_service.add_stock(
                            product_id     = item['product_id'],
                            branch_id      = branch_id,
                            qty            = item['qty'],
                            unit_cost      = item['unit_cost'],
                            operation_id   = operation_id,
                            reference_type = "COMPRA",
                            reference_id   = str(compra_id),
                            user           = user,
                            notes          = f"Entrada por compra {folio}",
                        )
                    except Exception as _inv_e:
                        inv_errors.append(
                            f"{item.get('nombre', item['product_id'])}: {_inv_e}")
                        logger.error(
                            "add_stock FAILED prod=%s compra=%s: %s",
                            item['product_id'], folio, _inv_e)

            if inv_errors:
                # Fase 5: inventario es parte del flujo DIRECT; si falla,
                # no debe quedar cabecera/detalle de compra parcialmente
                # comprometido porque eso abriría riesgo de doble inventario,
                # doble CxP/asiento o reintentos ambiguos.
                try:
                    self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
                finally:
                    self.db.execute(f"RELEASE SAVEPOINT {_sp}")
                    _sp_released = True
                raise RuntimeError(
                    f"Compra {folio} cancelada: el inventario "
                    f"NO se actualizó para:\n" +
                    "\n".join(inv_errors))

            # 3. AUTOMATIZACIÓN FINANCIERA (CAJA Y DEUDAS)
            # Registro financiero — adaptado a los métodos reales de FinanceService
            if self.finance_service:
                try:
                    # Si queda deuda, registrar CxP
                    if amount_paid < total_purchase:
                        deuda = total_purchase - amount_paid
                        # crear_cxp(provider_id, amount, due_date, notes, purchase_id)
                        if hasattr(self.finance_service, 'crear_cxp'):
                            self.finance_service.crear_cxp(
                                supplier_id=provider_id,
                                concepto=f"Compra {folio}",
                                amount=deuda,
                                due_date=None,
                                referencia=folio,
                                ref_type="compra",
                                usuario=user,
                            )

                    # Si se pagó al contado, registrar salida de caja si hay turno abierto
                    if amount_paid > 0 and payment_method != 'CREDITO':
                        turno = None
                        try:
                            turno = self.finance_service.get_estado_turno(branch_id, user)
                        except Exception:
                            pass
                        if turno and hasattr(self.finance_service, 'registrar_movimiento_manual'):
                            self.finance_service.registrar_movimiento_manual(
                                turno['id'], branch_id, user,
                                'RETIRO',
                                amount_paid,
                                f"Pago compra {folio} — {notes or 'proveedor'}"
                            )
                        # Double-entry journal — always, regardless of open shift
                        if hasattr(self.finance_service, 'registrar_asiento'):
                            self.finance_service.registrar_asiento(
                                debe="inventario",
                                haber="caja_efectivo",
                                concepto=f"Compra contado {folio}",
                                monto=float(amount_paid),
                                modulo="compras",
                                referencia_id=compra_id,
                                evento="COMPRA_REGISTRADA",
                                metadata={"folio": folio, "provider_id": provider_id,
                                          "payment_method": payment_method},
                            )
                except Exception as _fe:
                    _msg = f"Registro financiero incompleto: {_fe}"
                    logger.warning("FinanceService compra %s: %s", folio, _fe)
                    finance_warnings.append(_msg)

            # MEJORA: Auto-crear lotes para trazabilidad FIFO
            # Cada ítem de compra genera un lote independiente con su costo y caducidad
            self._crear_lotes_compra(
                compra_id=compra_id,
                folio=folio,
                items=items,
                proveedor_id=provider_id,
                sucursal_id=branch_id,
                usuario=user,
            )

            try:
                self.db.execute(f"RELEASE SAVEPOINT {_sp}")
            except Exception as _rel_err:
                if "no such savepoint" in str(_rel_err).lower():
                    # A nested service (e.g. FinanceService) committed the connection,
                    # implicitly releasing all savepoints. The purchase was already
                    # persisted to disk — treat this as success.
                    logger.debug(
                        "register_purchase: savepoint %s released by nested commit; "
                        "data already persisted.", _sp)
                else:
                    raise
            _sp_released = True

            # Notify EventBus — enriched payload includes items for downstream handlers
            try:
                from core.events.event_bus import get_bus, COMPRA_REGISTRADA
                get_bus().publish(COMPRA_REGISTRADA, {
                    "event_type":  COMPRA_REGISTRADA,
                    "folio":       folio,
                    "compra_id":   compra_id,
                    "branch_id":   branch_id,
                    "sucursal_id": branch_id,
                    "user":        user,
                    "usuario":     user,
                    "total":       total_purchase,
                    "proveedor_id":provider_id,
                    "items": [
                        {
                            "product_id":  it["product_id"],
                            "qty":         it["qty"],
                            "unit_cost":   it["unit_cost"],
                            "nombre":      it.get("nombre", ""),
                        }
                        for it in items
                    ],
                })
            except Exception:
                pass

            return folio, finance_warnings

        except Exception as e:
            if not _sp_released:
                try: self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
                except Exception: pass
            raise RuntimeError(f"Error al registrar la compra. Operación cancelada: {str(e)}")

    def _crear_lotes_compra(
        self, compra_id: int, folio: str, items: list,
        proveedor_id: int, sucursal_id: int, usuario: str,
    ) -> None:
        """
        MEJORA TRAZABILIDAD: Crea un lote por cada ítem de compra.

        Esto permite:
        - FIFO real por lote (vender el más antiguo primero)
        - Costeo por lote (cada lote tiene su propio costo_kg)
        - Trazabilidad completa: lote compra → lote producción → venta
        - Alertas de caducidad por lote

        Nota: solo actualiza la tabla `lotes` — NO toca `productos.existencia`
        porque PurchaseService.add_stock() ya lo hizo.
        """
        from datetime import datetime

        for item in items:
            try:
                producto_id = item.get("product_id")
                qty = float(item.get("qty", 0))
                unit_cost = float(item.get("unit_cost", 0))
                if not producto_id or qty <= 0:
                    continue

                numero_lote = f"{folio}-P{producto_id}"
                fecha_caducidad = item.get("fecha_caducidad")  # opcional

                self.db.execute("""
                    INSERT OR IGNORE INTO lotes (
                        uuid, producto_id, numero_lote, proveedor_id,
                        peso_inicial_kg, peso_actual_kg, costo_kg,
                        fecha_caducidad, sucursal_id,
                        temperatura_c, observaciones, estado
                    ) VALUES (
                        lower(hex(randomblob(16))),
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        NULL, ?, 'activo'
                    )
                """, (
                    producto_id, numero_lote, proveedor_id,
                    qty, qty, unit_cost,
                    fecha_caducidad, sucursal_id,
                    f"Compra {folio} - compra_id={compra_id}",
                ))

                lote_id = self.db.execute(
                    "SELECT id FROM lotes WHERE numero_lote=? AND producto_id=?",
                    (numero_lote, producto_id)
                ).fetchone()

                if lote_id:
                    self.db.execute("""
                        INSERT INTO movimientos_lote
                            (lote_id, tipo, cantidad_kg, referencia, usuario)
                        VALUES (?, 'recepcion', ?, ?, ?)
                    """, (lote_id[0], qty, folio, usuario))

            except Exception as _le:
                # No crítico: la compra ya se guardó, el lote es auditoría adicional
                logger.warning("Auto-lote compra item=%s: %s", item.get("product_id"), _le)

    # ── C-1: Cancel with inventory reversal ──────────────────────────────────

    def cancel_purchase_with_reversal(
        self, compra_id: int, user: str, branch_id: int, folio: str,
    ) -> list[str]:
        """
        Cancels a purchase and reverses its inventory movements.

        Returns a list of warning strings (empty on clean run).
        Partial reversal is allowed: if an item's stock has already been
        consumed the reversal for that item is skipped with a WARNING, and the
        purchase is still cancelled so the record stays accurate.
        """
        warnings: list[str] = []
        _sp = f"cancel_{uuid.uuid4().hex[:8]}"
        try:
            self.db.execute(f"SAVEPOINT {_sp}")

            items = self.purchase_repo.get_purchase_items_raw(compra_id)

            for item in items:
                pid = item["product_id"]
                qty = item["qty"]
                if qty <= 0:
                    continue
                try:
                    self.inventory_service.deduct_stock(
                        product_id     = pid,
                        branch_id      = branch_id,
                        qty            = qty,
                        reference_type = "CANCELACION",
                        reference_id   = str(compra_id),
                        operation_id   = _sp,
                        user           = user,
                        notes          = f"Reversión por cancelación {folio}",
                    )
                except ValueError as _ve:
                    # Stock insuficiente — reversal parcial; still cancel the purchase
                    _w = f"Producto {pid}: stock insuficiente para revertir ({_ve})"
                    logger.warning("cancel_reversal %s: %s", folio, _w)
                    warnings.append(_w)
                except Exception as _e:
                    _w = f"Producto {pid}: fallo reversión — {_e}"
                    logger.error("cancel_reversal %s: %s", folio, _w)
                    warnings.append(_w)

            self.purchase_repo.cancel_purchase(compra_id)

            self.db.execute(f"RELEASE SAVEPOINT {_sp}")
        except Exception as e:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
            except Exception:
                pass
            raise RuntimeError(f"Error al cancelar compra {folio}: {e}")

        return warnings