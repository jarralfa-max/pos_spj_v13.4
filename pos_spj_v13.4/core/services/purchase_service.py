
# core/services/purchase_service.py
import uuid

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
            # 🚨 SI ALGO FALLA (Ej. no hay dinero en caja o falla la base de datos):
            # Se deshace la compra, se deshace el inventario, no pasó nada.
            try: self.db.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
            except Exception: pass
            raise RuntimeError(f"Error al registrar la compra. Operación cancelada: {str(e)}")