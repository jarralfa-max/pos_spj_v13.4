"""OrdersDeliveryInventoryClient — Pedidos/Delivery's own integration point
onto Inventory (master prompt §23-24: "Inventario ejecuta la reserva.
Pedidos no escribe tablas de inventario."). Wraps Inventory's own use cases;
`ReservationSource.CUSTOMER_ORDER` exists specifically for this integration.

EL CICLO DE UN PEDIDO (SDLC-ORD-004)
------------------------------------
    reservar     al confirmar: retiene por línea, de los saldos reales
    descontar    SALE_ISSUE al salir de la sucursal (despacho, o entrega en
                 mostrador) y se cumplen las reservas
    devolver     SALE_RETURN si regresa a sucursal o se reversa

Antes el segundo paso no existía: la venta cerraba con `settle_inventory=False`
suponiendo que Pedidos descontaba, y Pedidos no tenía con qué. La existencia no
bajaba, la retención quedaba puesta para siempre y el reverso de Ventas sumaba
mercancía que nunca salió.

Reserva por LÍNEA (`source_document_id = line.id`, que es también el asa en
`inventory_reservation_id`): una línea puede salir de varios lotes y dos líneas
pueden ser del mismo producto.

Los movimientos llevan `source_module="orders_delivery"` y el id del pedido
como documento: el libro es la única memoria de lo que salió, y por eso
descontar dos veces no es posible y devolver repone exactamente eso, en su lote
y ubicación. Los métodos de descuento y devolución se unen a la transacción de
quien llama (`owns_transaction=False`): el pedido y su mercancía caen juntos.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.integration_grants import integration_use_case
from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.reservation_use_cases import (
    FulfillReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.application.inventory.use_cases.sale_reservation_use_cases import (
    ReserveStockForCustomerOrderUseCase,
    plan_sale_issue,
)
from backend.application.logistics.warehouse_directory import WarehouseDirectoryQueryService
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.domain.orders_delivery.exceptions import (
    OrderInventoryCommitFailedError,
    OrderInventoryReservationFailedError,
)
from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from backend.infrastructure.db.repositories.inventory.reservation_repository import (
    ReservationRepository,
)

_SOURCE_MODULE = "orders_delivery"


class OrdersDeliveryInventoryClient:
    def __init__(self, connection, *, branch_id: str) -> None:
        self._connection = connection
        self._branch_id = branch_id
        self._availability = InventoryAvailabilityQueryService(connection)
        self._warehouse_id: str | None = None

    @property
    def warehouse_id(self) -> str:
        """El almacén del que vende la sucursal: la misma regla del mostrador
        (`SalesInventoryClient.warehouse_id`), porque es la misma mercancía."""
        if self._warehouse_id is None:
            almacenes = WarehouseDirectoryQueryService(
                self._connection).sales_warehouses_for_branch(self._branch_id)
            if len(almacenes) > 1:
                raise OrderInventoryReservationFailedError(
                    "La sucursal tiene varios almacenes habilitados para venta; "
                    "deja sólo uno habilitado para venta en Almacenes.")
            self._warehouse_id = almacenes[0] if almacenes else self._branch_id
        return self._warehouse_id

    def is_available(self, *, product_id: str, quantity: Decimal) -> bool:
        return self._availability.is_available(
            product_id=product_id, branch_id=self._branch_id, quantity=quantity)

    def reserve_line(
        self, *, product_id: str, quantity: Decimal, line_id: str, operation_id: str,
        actor_user_id: str,
    ) -> str:
        """§23: reserves ONE order line and returns its handle. The caller
        (`ReserveOrderInventoryUseCase`) is responsible for compensating
        (releasing whatever already succeeded) if a later line fails —
        this client only ever reserves a single line per call."""
        # Concesión de Pedidos a Inventario (auditoría de permisos 968e0bc,
        # PER-02): antes era el default permisivo, que no revisaba nada.
        result = integration_use_case(
            ReserveStockForCustomerOrderUseCase, "orders_delivery", actor_user_id).execute(
            self._connection, product_id=product_id, branch_id=self._branch_id,
            warehouse_id=self.warehouse_id, quantity=quantity, source_document_id=line_id,
            operation_id=operation_id, actor_user_id=actor_user_id, lot_required=False)
        if not result.success:
            raise OrderInventoryReservationFailedError(result.message)
        return line_id

    def release(self, reservation_handle: str, *, operation_id: str, actor_user_id: str,
                reason: str = "", owns_transaction: bool = True) -> None:
        """Suelta TODAS las reservas activas de una línea (una por lote)."""
        use_case = integration_use_case(
            ReleaseReservationUseCase, "orders_delivery", actor_user_id)
        for reservation in self._active_reservations(reservation_handle):
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                operation_id=f"{operation_id}:{reservation.id}",
                actor_user_id=actor_user_id, reason=reason,
                owns_transaction=owns_transaction)
            if not result.success:
                raise OrderInventoryReservationFailedError(result.message)

    # ── descontar ────────────────────────────────────────────────────────
    def commit_order(self, order, *, operation_id: str, actor_user_id: str) -> None:
        """La mercancía del pedido sale de la sucursal, en la transacción de
        quien llama. Un solo movimiento: el pedido es UN documento.

        Sale la cantidad final de cada línea (`issue_quantity`), no la reservada:
        si se preparó de menos, lo demás vuelve a estar disponible al soltar la
        retención; si se preparó de más, lo que falta sale de lo disponible y,
        si no alcanza, el pedido no sale. Una línea rechazada suelta su reserva;
        una sustituida suelta la del original y saca el sustituto.

        Si el libro dice que el pedido ya está fuera, no hace nada: es lo que
        impide descontarlo dos veces.
        """
        if self._outstanding(order.id):
            return
        lineas: list[InventoryMovementLine] = []
        cumplir, soltar = [], []
        adicional: dict[str, Decimal] = {}
        for line in order.lines:
            producto = line.issue_product_id()
            sustituida = producto != line.product_id
            pendiente = line.issue_quantity() if line.ships else Decimal("0")
            for reserva in self._active_reservations(line.id):
                tomar = Decimal("0") if sustituida else min(pendiente, reserva.quantity)
                if tomar <= 0:
                    soltar.append(reserva)
                    continue
                lineas.append(self._issue_line(
                    producto, tomar, location_id=reserva.location_id, lot_id=reserva.lot_id))
                cumplir.append(reserva)
                pendiente -= tomar
            if pendiente > 0:
                adicional[producto] = adicional.get(producto, Decimal("0")) + pendiente
        for producto, cantidad in adicional.items():
            lineas.extend(self._extra_lines(producto, cantidad))

        if lineas:
            self._post(
                MovementType.SALE_ISSUE, lineas, source_document_type="CUSTOMER_ORDER",
                document_id=order.id, warehouse_id=self.warehouse_id,
                operation_id=f"{order.id}:order-issue:{self._issue_count(order.id) + 1}",
                actor_user_id=actor_user_id)
        self._fulfill(cumplir, operation_id=operation_id, actor_user_id=actor_user_id)
        release = integration_use_case(
            ReleaseReservationUseCase, "orders_delivery", actor_user_id)
        for reserva in soltar:
            result = release.execute(
                self._connection, reservation_id=reserva.id,
                operation_id=f"{operation_id}:{reserva.id}", actor_user_id=actor_user_id,
                reason="La línea no salió como se reservó", owns_transaction=False)
            if not result.success:
                raise OrderInventoryCommitFailedError(result.message)

    def _extra_lines(self, product_id: str, quantity: Decimal) -> list[InventoryMovementLine]:
        """Lo que sale sin reserva (preparado de más, sustituto): misma
        estrategia y elegibilidad que la reserva. Sin autorización de vender sin
        existencia, un faltante detiene la salida."""
        rebanadas, faltante = plan_sale_issue(
            self._connection, product_id=product_id, branch_id=self._branch_id,
            warehouse_id=self.warehouse_id, quantity=quantity)
        if faltante > 0:
            raise OrderInventoryCommitFailedError(
                f"Sin existencia para surtir el pedido: faltan {faltante} del producto "
                f"{product_id}.")
        return [self._issue_line(product_id, rebanada.quantity,
                                 location_id=rebanada.location_id, lot_id=rebanada.lot_id)
                for rebanada in rebanadas]

    def _issue_line(self, product_id: str, quantity: Decimal, *, location_id, lot_id
                    ) -> InventoryMovementLine:
        return InventoryMovementLine.create(
            product_id=product_id, quantity=quantity, from_location_id=location_id,
            lot_id=lot_id, from_status=InventoryStatus.AVAILABLE, reason_code="SALE",
            unit_cost=self._unit_cost(product_id))

    def _unit_cost(self, product_id: str):
        """Costo promedio de Precios; sin costo conocido no se inventa."""
        try:
            from backend.application.pricing.queries.pricing_read_facade import (
                PricingReadFacade,
            )
            costo = PricingReadFacade(self._connection).unit_cost(product_id, self._branch_id)
        except Exception:  # noqa: BLE001 - el costo no detiene la salida de mercancía
            return None
        return None if costo is None else Decimal(str(costo))

    def _fulfill(self, reservations, *, operation_id: str, actor_user_id: str) -> None:
        use_case = integration_use_case(
            FulfillReservationUseCase, "orders_delivery", actor_user_id)
        for reservation in reservations:
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                operation_id=f"{operation_id}:{reservation.id}",
                actor_user_id=actor_user_id, owns_transaction=False)
            if not result.success:
                raise OrderInventoryCommitFailedError(result.message)

    # ── devolver ─────────────────────────────────────────────────────────
    def restore_order(self, order, *, operation_id: str, actor_user_id: str,
                      reason_code: str) -> None:
        """Devuelve EXACTAMENTE lo que el pedido tiene fuera, según el libro, a
        los lotes y ubicaciones de los que salió, en la transacción de quien
        llama. Un pedido que nunca descontó no suma nada; si aún retenía
        mercancía, la suelta."""
        for line in order.lines:
            self.release(line.id, operation_id=operation_id, actor_user_id=actor_user_id,
                         reason=reason_code, owns_transaction=False)
        fuera = self._outstanding(order.id)
        if not fuera:
            return
        lineas = [
            InventoryMovementLine.create(
                product_id=producto, quantity=cantidad, lot_id=lot_id,
                to_location_id=location_id, to_status=InventoryStatus.AVAILABLE,
                reason_code=reason_code, unit_cost=costo)
            for (_almacen, producto, lot_id, location_id), (cantidad, costo) in fuera.items()]
        self._post(
            MovementType.SALE_RETURN, lineas, source_document_type="CUSTOMER_ORDER_RETURN",
            document_id=order.id, warehouse_id=next(iter(fuera))[0],
            operation_id=f"{operation_id}:order-return", actor_user_id=actor_user_id)

    # ── libro ────────────────────────────────────────────────────────────
    def _movements(self, order_id: str) -> list[tuple]:
        return self._connection.execute(
            "SELECT id, movement_type, warehouse_id FROM inventory_ledger"
            " WHERE source_document_id=? AND source_module=? ORDER BY occurred_at, id",
            (str(order_id), _SOURCE_MODULE)).fetchall()

    def _issue_count(self, order_id: str) -> int:
        return sum(1 for fila in self._movements(order_id) if fila[1] == "SALE_ISSUE")

    def _outstanding(self, order_id: str) -> dict[tuple, tuple[Decimal, Decimal | None]]:
        """(almacén, producto, lote, ubicación) → (cantidad fuera, costo con que
        salió). Salidas menos devoluciones del pedido; costo promedio de lo que
        salió con costo, None si salió sin costo."""
        ledger = InventoryLedgerRepository(self._connection)
        salio: dict[tuple, Decimal] = {}
        volvio: dict[tuple, Decimal] = {}
        valor: dict[tuple, Decimal] = {}
        con_costo: dict[tuple, Decimal] = {}
        for movement_id, movement_type, warehouse_id in self._movements(order_id):
            for line in ledger.get_lines(movement_id):
                cantidad = Decimal(str(line["quantity"] or "0"))
                if movement_type == "SALE_ISSUE":
                    clave = (warehouse_id, line["product_id"], line["lot_id"] or None,
                             line["from_location_id"])
                    salio[clave] = salio.get(clave, Decimal("0")) + cantidad
                    if line["unit_cost"] not in (None, ""):
                        valor[clave] = valor.get(clave, Decimal("0")) + cantidad * Decimal(
                            str(line["unit_cost"]))
                        con_costo[clave] = con_costo.get(clave, Decimal("0")) + cantidad
                elif movement_type == "SALE_RETURN":
                    clave = (warehouse_id, line["product_id"], line["lot_id"] or None,
                             line["to_location_id"])
                    volvio[clave] = volvio.get(clave, Decimal("0")) + cantidad
        resultado = {}
        for clave, cantidad in salio.items():
            neto = cantidad - volvio.get(clave, Decimal("0"))
            if neto > 0:
                costo = valor[clave] / con_costo[clave] if con_costo.get(clave) else None
                resultado[clave] = (neto, costo)
        return resultado

    def _post(self, movement_type: MovementType, lineas, *, source_document_type: str,
              document_id: str, warehouse_id: str, operation_id: str,
              actor_user_id: str) -> None:
        movement = InventoryMovement.create(
            movement_type=movement_type, branch_id=self._branch_id,
            warehouse_id=warehouse_id, source_module=_SOURCE_MODULE,
            source_document_type=source_document_type, source_document_id=str(document_id),
            operation_id=operation_id, created_by_user_id=str(actor_user_id), lines=lineas)
        result = integration_use_case(
            PostInventoryMovementUseCase, "orders_delivery", actor_user_id).execute(
            self._connection, movement, actor_user_id=str(actor_user_id),
            owns_transaction=False)
        if not result.success:
            raise OrderInventoryCommitFailedError(
                result.message or "No se pudo registrar la mercancía del pedido.")

    def _active_reservations(self, source_document_id: str):
        return ReservationRepository(self._connection).list_active_for_source_document(
            source_document_id)
