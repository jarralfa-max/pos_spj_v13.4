
# core/services/inventory_service.py
import uuid
import logging
from core.security.decorators import require_permission

logger = logging.getLogger(__name__)

class InventoryService:
    """
    Servicio Core de Inventario basado en Event Sourcing (Ledger).
    Toda entrada o salida registra un movimiento inmutable y actualiza el caché de stock.
    """

    def __init__(self, db_conn, inventory_repo):
        self.db = db_conn
        self.repo = inventory_repo
        
    # ¡BAM! Un muro de seguridad de una sola línea
    @require_permission('adjust_inventory')
    def execute_manual_adjustment(self, product_id: int, new_qty: float, user_id: int, branch_id: int):
        # Si el usuario no tiene permiso, la ejecución NUNCA llega a esta línea.
        # Lanza PermissionDeniedError automáticamente.
        self.deduct_stock(...)

    def add_stock(self, product_id: int, branch_id: int, qty: float, unit_cost: float, 
                  reference_type: str, reference_id: str, operation_id: str, user: str, notes: str = ""):
        """
        Suma inventario (Compras, Devoluciones, Entrada por Producción, Ajustes positivos).
        """
        if qty <= 0:
            raise ValueError("La cantidad a ingresar debe ser mayor a cero.")

        try:
            # 1. EL LIBRO MAYOR (Append-Only): Registrar el movimiento inmutable
            self.repo.insert_movement(
                product_id=product_id,
                branch_id=branch_id,
                movement_type="IN",
                reference_type=reference_type, # Ej: 'PURCHASE', 'PRODUCTION'
                reference_id=reference_id,
                qty=qty,
                unit_cost=unit_cost,
                operation_id=operation_id,
                user=user,
                notes=notes
            )

            # 2. EL CACHÉ DE LECTURA: Actualizar la tabla rápida y el costo promedio
            current_stock = self.repo.get_current_stock(product_id, branch_id)
            current_avg_cost = self.repo.get_average_cost(product_id, branch_id)
            
            # Matemática para recalcular el costo promedio ponderado
            total_value_before = current_stock * current_avg_cost
            value_added = qty * unit_cost
            new_stock = current_stock + qty
            new_avg_cost = (total_value_before + value_added) / new_stock if new_stock > 0 else 0

            self.repo.update_inventory_cache(
                product_id=product_id,
                branch_id=branch_id,
                new_qty=new_stock,
                new_avg_cost=new_avg_cost
            )
            
            logger.info(f"Inventario sumado: {qty} del prod {product_id}. Ref: {reference_type}-{reference_id}")

        except Exception as e:
            logger.error(f"Error agregando stock al producto {product_id}: {str(e)}")
            raise RuntimeError(f"Fallo al ingresar inventario: {str(e)}")

    def deduct_stock(self, product_id: int, branch_id: int, qty: float, 
                     reference_type: str, reference_id: str, operation_id: str, user: str, notes: str = ""):
        """
        Resta inventario (Ventas, Salida para Producción, Mermas, Ajustes negativos).
        """
        if qty <= 0:
            raise ValueError("La cantidad a descontar debe ser mayor a cero.")

        try:
            # Validar que haya stock suficiente (Regla de negocio crítica)
            current_stock = self.repo.get_current_stock(product_id, branch_id)
            if current_stock < qty:
                raise ValueError(f"Stock insuficiente. Hay {current_stock}, se requieren {qty}.")

            # 1. EL LIBRO MAYOR (Append-Only): Registrar el movimiento como negativo
            current_avg_cost = self.repo.get_average_cost(product_id, branch_id)
            self.repo.insert_movement(
                product_id=product_id,
                branch_id=branch_id,
                movement_type="OUT",
                reference_type=reference_type, # Ej: 'SALE', 'PRODUCTION_CONSUMPTION', 'WASTE'
                reference_id=reference_id,
                qty=-qty,  # Se guarda como negativo para que el SUM() funcione perfecto
                unit_cost=current_avg_cost, # La salida sale al costo promedio actual
                operation_id=operation_id,
                user=user,
                notes=notes
            )

            # 2. EL CACHÉ DE LECTURA: Actualizar la tabla rápida
            new_stock = current_stock - qty
            self.repo.update_inventory_cache(
                product_id=product_id,
                branch_id=branch_id,
                new_qty=new_stock,
                new_avg_cost=current_avg_cost # El costo promedio no cambia en las salidas
            )

            logger.info(f"Inventario descontado: {qty} del prod {product_id}. Ref: {reference_type}-{reference_id}")

        except Exception as e:
            logger.error(f"Error descontando stock al producto {product_id}: {str(e)}")
            raise RuntimeError(f"Fallo al descontar inventario: {str(e)}")

    def get_stock(self, product_id: int, branch_id: int) -> float:
        """
        Lectura ultrarrápida para el POS. Lee del caché, no suma movimientos.
        """
        return self.repo.get_current_stock(product_id, branch_id)

    # ── v13.4: aliases en español para EventBus wiring ────────────────────────

    def descontar_stock(self, producto_id: int, cantidad: float,
                        branch_id: int = 1, referencia_id: str = "EVT",
                        usuario: str = "sistema", **kwargs) -> None:
        """Alias de deduct_stock() para uso desde EventBus."""
        self.deduct_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            reference_type="SALE_EVENT", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(producto_id)),
            user=usuario, notes=kwargs.get("notes", ""),
        )

    def incrementar_stock(self, producto_id: int, cantidad: float,
                          unit_cost: float = 0.0, branch_id: int = 1,
                          referencia_id: str = "EVT",
                          usuario: str = "sistema", **kwargs) -> None:
        """Alias de add_stock() para uso desde EventBus."""
        self.add_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            unit_cost=unit_cost,
            reference_type="PURCHASE_EVENT", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(producto_id)),
            user=usuario, notes=kwargs.get("notes", ""),
        )

    def ajustar_merma(self, producto_id: int, cantidad: float,
                      branch_id: int = 1, referencia_id: str = "MERMA",
                      usuario: str = "sistema", **kwargs) -> None:
        """Descuenta merma del inventario. Alias para EventBus."""
        self.deduct_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            reference_type="WASTE", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(producto_id)),
            user=usuario, notes=kwargs.get("notes", "merma"),
        )

    def conciliate_stock(self, product_id: int, branch_id: int):
        """
        🚨 BOTÓN DE PÁNICO / AUDITORÍA 🚨
        Recalcula el stock exacto sumando la historia inmutable y repara el caché si hay diferencias.
        """
        # 1. Calcular la Verdad Absoluta
        real_stock_from_ledger = self.repo.sum_all_movements(product_id, branch_id)
        
        # 2. Leer la tabla rápida
        cached_stock = self.repo.get_current_stock(product_id, branch_id)
        
        if round(real_stock_from_ledger, 4) != round(cached_stock, 4):
            logger.warning(f"Discrepancia detectada prod {product_id}. Ledger: {real_stock_from_ledger}, Caché: {cached_stock}. Reparando...")
            # Sobrescribir el caché con la verdad
            self.repo.force_update_inventory_cache_qty(product_id, branch_id, real_stock_from_ledger)
            return True, real_stock_from_ledger
        
        return False, cached_stock
    


def execute_manual_adjustment(self, product_id: int, branch_id: int, new_qty: float, user: str, reason: str):
    
    # 1. Leemos cómo estaban las cosas ANTES
    stock_antes = self.get_stock(product_id, branch_id)
    
    # 2. Hacemos el ajuste real (usando el método que ya programamos)
    diferencia = new_qty - stock_antes
    if diferencia < 0:
        self.deduct_stock(product_id, branch_id, abs(diferencia), "ADJUSTMENT", "manual", "op_123", user, reason)
    else:
        self.add_stock(product_id, branch_id, diferencia, 0, "ADJUSTMENT", "manual", "op_123", user, reason)

    # 3. 🚨 EL TESTIGO: Guardamos la auditoría exacta del suceso
    self.audit_service.log_change(
        usuario=user,
        accion="ADJUST",
        modulo="INVENTARIO",
        entidad="PRODUCTO",
        entidad_id=product_id,
        before_state={"stock": stock_antes},         # JSON Antes: {"stock": 100}
        after_state={"stock": new_qty},              # JSON Después: {"stock": 90}
        sucursal_id=branch_id,
        detalles=f"Ajuste manual. Motivo: {reason}"
    )