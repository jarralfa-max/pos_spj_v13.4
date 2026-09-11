"""SalesInventoryClient — el punto por donde Ventas habla con Inventario.

Máster prompt §6/§20: "Ventas no es dueño de inventario". Este adaptador es el
único sitio del stack de `backend/application/sales/` que toca el contexto de
inventario.

QUÉ CAMBIÓ Y POR QUÉ
--------------------
Antes envolvía `core.services.stock_reservation_service.StockReservationService`,
que desapareció con la carpeta `core/`. No se reconstruyó: había DOS modelos de
reserva compitiendo en el mismo sistema (§3), y el que sobrevivió es mejor en
todo lo que importa.

    legacy `stock_reservas`          canónico `inventory_reservation`
    ─────────────────────────────    ─────────────────────────────────────
    idempotencia por `folio` UNIQUE  por `operation_id` UNIQUE
    cantidades REAL (float)          Decimal en TEXT
    no retenía disponibilidad        reduce el disponible de verdad
    sin autorización                 exige INVENTARIO.reserva.*
    sin auditoría                    audita y emite evento

El modelo legacy sólo movía una cadena de estado ('activa' → 'confirmada' →
'cancelada') y NO retenía nada: dos cajas podían vender la misma última pieza.
El canónico sube `reserved_quantity` del saldo, así que el disponible baja de
inmediato.

Además desaparece la conversión Decimal → float que este archivo hacía en su
frontera, y de la que su propia versión anterior se disculpaba: ya no hay
ninguna tabla de tipo float al otro lado.

UNA RESERVA POR PRODUCTO, UN ASA POR VENTA
------------------------------------------
El modelo canónico reserva por producto, pero `Sale.inventory_reservation_id`
es un solo campo. El asa es el `sale.id`, que viaja como `source_document_id`
en cada reserva de esa venta: confirmar o liberar "la reserva de la venta"
resuelve todas sus líneas juntas. Por eso este cliente devuelve `sale.id` y no
el id de una fila concreta.

Las líneas se AGRUPAN por producto antes de reservar. Una venta puede tener el
mismo producto en dos renglones (dos pesadas distintas del mismo corte); dos
reservas separadas para el mismo producto chocarían contra la unicidad de
`operation_id`, que se deriva del par venta+producto para que reservar dos
veces la misma venta sea idempotente de verdad.

HALLAZGO PENDIENTE, NO RESUELTO AQUÍ
------------------------------------
Completar una venta NO descuenta la existencia. No es algo que rompiera esta
migración: no existe un solo uso de `MovementType.SALE` en todo el repositorio,
mientras que las devoluciones sí reponen con `SALE_RETURN` (`restore_for_return`,
más abajo). Es decir, las devoluciones inflan el inventario y las ventas nunca
lo bajan.

Este cliente NO lo arregla por su cuenta: registrar la salida cambiaría la
valuación del inventario y el costo de ventas, que es una decisión del negocio.
Lo que sí hace es no disimularlo — al cumplirse una reserva la retención se
mantiene (ver `FulfillReservationUseCase`), de modo que el número de
"reservado" acumula exactamente lo vendido y no descontado, y el síntoma queda
medible.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases.reservation_use_cases import (
    CreateReservationUseCase,
    ExpireReservationsUseCase,
    FulfillReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.domain.inventory.enums import ReservationSource
from backend.domain.sales.entities import Sale
from backend.domain.sales.exceptions import InventoryReservationFailedError
from backend.infrastructure.db.repositories.inventory.reservation_repository import (
    ReservationRepository,
)


def _reserve_operation_id(sale_id: str, product_id: str) -> str:
    """Identidad idempotente de "reservar este producto para esta venta".

    Determinista a propósito: `inventory_reservation.operation_id` es UNIQUE,
    así que reintentar la reserva de una venta reconoce lo ya reservado en vez
    de duplicarlo. Un UUID nuevo en cada intento crearía una reserva más por
    cada reintento, y el disponible bajaría sin que nadie hubiera vendido nada.
    """
    return f"{sale_id}:reserve:{product_id}"


class SalesInventoryClient:
    def __init__(
        self, connection, *, branch_id: str, actor_user_id: str = "",
        authorization: InventoryAuthorizationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self._branch_id = branch_id
        self._actor_user_id = actor_user_id
        # Sin política explícita se construye una SIN verificador, que no
        # concede nada: al primer `require()` lanza `InventoryConfigurationError`.
        # Es deliberado que reviente en vez de denegar en silencio — un cableado
        # incompleto se nota al instante, en lugar de parecerse a "este usuario
        # no tiene permiso". Lo que NO se hace es usar `permissive_for_tests()`
        # por omisión: eso concedería cualquier permiso de inventario a quien
        # pasara por aquí, que es justo lo que §23 prohíbe en producción.
        self._authorization = authorization or InventoryAuthorizationPolicy()

    # ── reservar ─────────────────────────────────────────────────────────
    def reserve_for_sale(self, sale: Sale) -> str:
        """Reserva TODAS las líneas de la venta. Devuelve el asa (`sale.id`).

        Si alguna línea no tiene disponibilidad, se lanza
        `InventoryReservationFailedError` y se liberan las reservas que sí se
        habían creado en este intento: una venta no puede quedarse reteniendo
        la mitad de su mercancía indefinidamente.
        """
        use_case = CreateReservationUseCase(self._authorization)
        creadas: list[str] = []
        for product_id, cantidad in self._quantities_by_product(sale).items():
            result = use_case.execute(
                self._connection, product_id=product_id, branch_id=self._branch_id,
                # Este repositorio trata la sucursal como su propio almacén; es
                # la simplificación ya establecida aquí, no una decisión nueva.
                warehouse_id=self._branch_id,
                source=ReservationSource.SALE, source_document_id=sale.id,
                quantity=cantidad,
                operation_id=_reserve_operation_id(sale.id, product_id),
                actor_user_id=self._actor_user_id,
            )
            if not result.success:
                self._release_all(sale.id, reason="reserva incompleta")
                raise InventoryReservationFailedError(result.message)
            creadas.append(result.entity_id or "")
        if not creadas:
            raise InventoryReservationFailedError("La venta no tiene líneas que reservar.")
        return sale.id

    @staticmethod
    def _quantities_by_product(sale: Sale) -> dict[str, Decimal]:
        """Cantidad total por producto.

        Se agrupa porque el mismo producto puede aparecer en varias líneas
        (dos pesadas del mismo corte) y la reserva canónica es por producto.
        """
        totales: dict[str, Decimal] = {}
        for line in sale.lines:
            totales[line.product_id] = (
                totales.get(line.product_id, Decimal("0")) + line.quantity.value)
        return totales

    # ── confirmar / liberar ──────────────────────────────────────────────
    def confirm(self, reservation_handle: str, *, sale_id: str, folio: str) -> None:
        """La venta se completó: la mercancía salió.

        `folio` se acepta por compatibilidad con los llamadores actuales pero ya
        no identifica nada: la identidad de la reserva es el documento origen.
        Se conserva en el parámetro en lugar de cambiar cinco llamadores a la
        vez; el día que se limpien, se quita de aquí también.
        """
        del folio
        use_case = FulfillReservationUseCase(self._authorization)
        for reservation in self._active_reservations(reservation_handle or sale_id):
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                operation_id=f"{sale_id}:fulfill:{reservation.product_id}",
                actor_user_id=self._actor_user_id,
            )
            if not result.success:
                raise InventoryReservationFailedError(result.message)

    def release(self, reservation_handle: str, *, reason: str = "cancelada") -> None:
        """La operación se canceló: la mercancía vuelve a estar disponible."""
        self._release_all(reservation_handle, reason=reason)

    def _release_all(self, reservation_handle: str, *, reason: str) -> None:
        use_case = ReleaseReservationUseCase(self._authorization)
        for reservation in self._active_reservations(reservation_handle):
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                operation_id=f"{reservation_handle}:release:{reservation.product_id}",
                actor_user_id=self._actor_user_id, reason=reason,
            )
            if not result.success:
                raise InventoryReservationFailedError(result.message)

    def _active_reservations(self, source_document_id: str):
        return ReservationRepository(self._connection).list_active_for_source_document(
            source_document_id)

    # ── caducidad ────────────────────────────────────────────────────────
    def expire_orphaned(self) -> int:
        """Caduca las reservas vencidas y devuelve cuántas. Cero es lo normal."""
        result = ExpireReservationsUseCase(self._authorization).execute(
            self._connection, operation_id="sales:expire-orphaned",
            actor_user_id=self._actor_user_id,
        )
        if not result.success:
            raise InventoryReservationFailedError(result.message)
        return int(result.data.get("expired", 0))

    # ── devoluciones ─────────────────────────────────────────────────────
    def restore_for_return(
        self, *, product_id: str, quantity: Decimal, sale_id: str, operation_id: str,
        actor_user_id: str, reason_code: str, source_document_type: str,
    ) -> None:
        """POS-16/§42-44: devuelve mercancía devuelta al stock vendible.

        Usa `MovementType.SALE_RETURN`, reutilizando `branch_id` como
        `warehouse_id` (la simplificación ya establecida en este repositorio).

        A diferencia de `SalesCashEffectsClient`, esto SÍ se compone dentro de
        la transacción del llamador: `InventoryUnitOfWork` admite
        `owns_transaction=False`, así que se une al `SalesUnitOfWork` que el
        llamador ya tiene abierto.
        """
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        line = InventoryMovementLine.create(
            product_id=product_id, quantity=quantity, to_location_id=self._branch_id,
            to_status=InventoryStatus.AVAILABLE, reason_code=reason_code)
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_RETURN, branch_id=self._branch_id,
            warehouse_id=self._branch_id, source_module="sales",
            source_document_type=source_document_type, source_document_id=str(sale_id),
            operation_id=str(operation_id), created_by_user_id=str(actor_user_id), lines=[line])
        result = PostInventoryMovementUseCase().execute(
            self._connection, movement, actor_user_id=str(actor_user_id),
            owns_transaction=False)
        if not result.success:
            raise InventoryReservationFailedError(
                result.message or "No se pudo restaurar inventario.")
