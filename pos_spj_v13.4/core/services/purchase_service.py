
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
                          items: list, payment_method: str, amount_paid: float, notes: str = "") -> str:
        """
        Registra la compra, suma inventario y descuenta el dinero automáticamente.
        
        :param items: Lista de diccionarios [{'product_id': 1, 'qty': 100, 'unit_cost': 50.0}, ...]
        """
        # Generamos un ID único para rastrear todo este movimiento en conjunto
        operation_id = str(uuid.uuid4())
        
        # Calculamos el total real de la compra
        total_purchase = sum(item['qty'] * item['unit_cost'] for item in items)
        
        # Determinamos si se pagó completa o quedó a crédito
        status = "completada" if amount_paid >= total_purchase else "credito"

        import uuid as _uuid2
        _sp = f"compra_{_uuid2.uuid4().hex[:8]}"
        try:
            # Use SAVEPOINT (compatible with isolation_level=None / autocommit)
            self.db.execute(f"SAVEPOINT {_sp}")

            # 1. GUARDAR LA COMPRA (Cabecera y detalles en la BD)
            compra_id, folio = self.purchase_repo.create_purchase(
                provider_id=provider_id,
                branch_id=branch_id,
                user=user,
                total=total_purchase,
                status=status,
                operation_id=operation_id,
                notes=notes,
                payment_method=payment_method,
            )
            
            # Guardar los renglones (productos) de la compra
            self.purchase_repo.save_purchase_items(compra_id, items)

            # 2. AUTOMATIZACIÓN DE INVENTARIO
            inv_errors = []
            for item in items:
                try:
                    self.inventory_service.add_stock(
                        product_id=item['product_id'],
                        branch_id=branch_id,
                        qty=item['qty'],
                        unit_cost=item['unit_cost'],
                        operation_id=operation_id,
                        reference_type="COMPRA",
                        reference_id=str(compra_id),
                        user=user,
                        notes=f"Entrada por compra {folio}",
                    )
                except Exception as _inv_e:
                    inv_errors.append(
                        f"{item.get('nombre', item['product_id'])}: {_inv_e}")
                    import logging as _log
                    _log.getLogger(__name__).error(
                        "add_stock FAILED prod=%s compra=%s: %s",
                        item['product_id'], folio, _inv_e)

            if inv_errors:
                # Release savepoint so compra is saved but raise to inform UI
                self.db.execute(f"RELEASE SAVEPOINT {_sp}")
                raise RuntimeError(
                    f"Compra {folio} guardada pero el inventario "
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
                except Exception as _fe:
                    import logging
                    logging.getLogger(__name__).warning("FinanceService compra: %s", _fe)
                    # Non-fatal: inventory already updated, purchase recorded

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

            # Release savepoint — all changes persist
            self.db.execute(f"RELEASE SAVEPOINT {_sp}")

            # Notify EventBus so modules auto-refresh
            try:
                from core.events.event_bus import EventBus, get_bus, COMPRA_REGISTRADA
                get_bus().publish(COMPRA_REGISTRADA, {
                    "event_type": COMPRA_REGISTRADA,
                    "folio": folio,
                    "compra_id": compra_id,
                    "branch_id": branch_id,
                    "user": user,
                    "total": total_purchase,
                })
            except Exception:
                pass

            return folio

        except Exception as e:
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