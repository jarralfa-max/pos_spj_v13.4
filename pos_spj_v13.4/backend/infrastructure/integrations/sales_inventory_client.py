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

EL CICLO COMPLETO, Y POR QUÉ ESTABA ROTO
---------------------------------------
    reservar   retiene         disponible baja, existencia intacta
    confirmar  SALE_ISSUE      existencia baja y se suelta la retención
    liberar    deshace         la mercancía vuelve a estar disponible
    devolver   SALE_RETURN     la mercancía devuelta vuelve al stock

Hasta ahora faltaba el segundo paso: completar una venta no descontaba nada,
mientras que las devoluciones sí reponían. Las devoluciones inflaban el
inventario y las ventas nunca lo bajaban.

Existía un `CanonicalSaleInventoryHandler` que sí registraba `SALE_ISSUE`, pero
quedó huérfano al desaparecer `core/`: nadie emite ya su evento
(`SALE_ITEMS_PROCESS`), su suscripción vivía en `core/events/wiring.py` y su
explosión de recetas depende de un `RecipeResolver` borrado. Por eso el
descuento se hace aquí, de forma síncrona y atómica con la venta, en lugar de
resucitar una ruta por eventos que ya no tiene ni emisor ni cableado.

PRODUCTOS COMPUESTOS — LIMITACIÓN CONOCIDA, DISTINTA DE LA RECONSTRUCCIÓN DE
ABAJO. Ni reservar ni confirmar explotan recetas de tipo PRODUCTION_BOM/FORMULA/
etc.: se retiene y se descuenta el producto vendido, no sus componentes (vender
un kit no consume hoy sus ingredientes). La simetría es deliberada —descontar
componentes de algo que se retuvo como compuesto dejaría la retención puesta
para siempre. Cerrar esto es trabajo del contexto de Productos, que ya tiene
`RecipeExplosionService` canónico para esa dirección; cuando `reserve_for_sale`
lo use, `confirm` lo seguirá solo, porque descuenta lo que haya reservado.
NO confundir con la reconstrucción inversa de abajo, que es la dirección
OPUESTA (parte → base) y una receta distinta (DISASSEMBLY/CUTTING_YIELD).

RECONSTRUCCIÓN INVERSA (§15-19, Fase 7) — `_top_up_via_reconstruction_if_short`.
Cuando el stock directo de un producto no alcanza para la línea pero tiene una
receta DISASSEMBLY/CUTTING_YIELD marcada `reverse_reconstruction_allowed`
(§16), se reconstruye el faltante desde sus partes (`ReconstructBaseProductUseCase`)
ANTES del intento de reserva normal de abajo — que queda sin cambios, porque ya
hay stock físico real cuando corre. Best-effort silencioso: si no aplica o las
partes tampoco alcanzan, la reserva normal falla sola con su propio mensaje
claro de "sin disponibilidad", nunca una segunda forma de bloquear o arreglar
una venta en silencio.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.inventory.use_cases.reconstruction_use_cases import (
    ReconstructBaseProductUseCase,
)
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

logger = logging.getLogger("spj.sales.inventory_client")


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
            self._top_up_via_reconstruction_if_short(
                product_id=product_id, needed=cantidad, sale_id=sale.id)
            result = use_case.execute(
                self._connection, product_id=product_id, branch_id=self._branch_id,
                # Este repositorio trata la sucursal como su propio almacén; es
                # la simplificación ya establecida aquí, no una decisión nueva.
                warehouse_id=self._branch_id,
                # La sucursal hace también de ubicación. Es la misma clave que
                # ya usa `restore_for_return` al reponer, y tiene que serlo:
                # reservar, descontar y devolver deben caer en LA MISMA fila de
                # saldo, que se identifica por (producto, sucursal, almacén,
                # estado, ubicación, lote). Con ubicaciones distintas no salta
                # ningún error — el stock se parte en dos filas y una de ellas
                # se queda retenida para siempre.
                location_id=self._branch_id,
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

    def _top_up_via_reconstruction_if_short(
        self, *, product_id: str, needed: Decimal, sale_id: str,
    ) -> None:
        """§15-19: when direct stock can't cover this line, try reconstructing
        the shortfall from a reversible recipe's parts BEFORE the normal
        reservation attempt below — real physical stock exists by the time
        it runs, so that reservation logic is completely unchanged either
        way. Best-effort only: if the product isn't reconstructible, or the
        parts themselves are short, this quietly does nothing and the normal
        reservation attempt fails on its own with its own clear
        "insufficient availability" message — reconstruction is a top-up,
        never a new way to block or silently fix a sale.
        """
        availability = InventoryAvailabilityQueryService(self._connection).get_availability(
            product_id=product_id, branch_id=self._branch_id, warehouse_id=self._branch_id)
        shortfall = needed - availability.available
        if shortfall <= 0:
            return
        try:
            result = ReconstructBaseProductUseCase(self._authorization).execute(
                self._connection, product_id=product_id, quantity=shortfall,
                branch_id=self._branch_id, warehouse_id=self._branch_id,
                actor_user_id=self._actor_user_id,
                operation_id=f"{sale_id}:reconstruct:{product_id}")
        except Exception:
            # Reconstruction reaches into Products' recipe tables — optional
            # infrastructure a connection may legitimately not have (a
            # narrower fixture, an environment where that migration hasn't
            # landed yet). This integration point must never turn "recipes
            # aren't set up" into "sales are broken": log it and let the
            # normal reservation attempt below fail on its own, same as any
            # other declined top-up.
            logger.exception(
                "sale %s: reconstruction top-up for %s raised; skipping",
                sale_id, product_id)
            return
        if not result.success:
            logger.info(
                "sale %s: %s short by %s, reconstruction not applied (%s: %s)",
                sale_id, product_id, shortfall, result.error_code, result.message)

    # ── confirmar / liberar ──────────────────────────────────────────────
    def confirm(self, reservation_handle: str, *, sale_id: str, folio: str) -> None:
        """La venta se completó: la mercancía SALE del inventario.

        Dos pasos, en este orden y dentro de la transacción de la venta:

          1. se registra UN movimiento `SALE_ISSUE` con una línea por producto,
             que baja la existencia real;
          2. se cumplen las reservas, lo que suelta su retención.

        El orden no es indiferente. Soltar primero dejaría un instante en el que
        la mercancía ya cobrada figura como disponible; y si el movimiento
        fallara, se habría liberado stock que en realidad salió.

        SE DESCUENTA EXACTAMENTE LO QUE SE RESERVÓ. Las líneas salen de las
        reservas activas de la venta, no de `sale.lines`. Así lo retenido y lo
        descontado no pueden divergir: si mañana `reserve_for_sale` explota
        recetas de productos compuestos, el descuento las seguirá sin tocar este
        método. Al revés —reservar el compuesto y descontar sus componentes—
        dejaría la retención del compuesto puesta para siempre.

        `folio` se acepta por compatibilidad con los llamadores actuales pero ya
        no identifica nada: la identidad de la reserva es el documento origen.
        """
        del folio
        handle = reservation_handle or sale_id
        reservations = self._active_reservations(handle)
        if not reservations:
            return

        self._post_sale_issue(reservations, sale_id=sale_id)

        use_case = FulfillReservationUseCase(self._authorization)
        for reservation in reservations:
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                operation_id=f"{sale_id}:fulfill:{reservation.product_id}",
                actor_user_id=self._actor_user_id,
            )
            if not result.success:
                raise InventoryReservationFailedError(result.message)

    def _post_sale_issue(self, reservations, *, sale_id: str) -> None:
        """Registra la salida de mercancía por venta.

        Un solo movimiento con todas las líneas, no uno por producto: la venta
        es UN documento, y el libro de inventario debe poder reconstruirla como
        tal. Es idempotente por `operation_id`, así que reintentar el cobro no
        descuenta dos veces.

        Se une a la transacción abierta por la venta (`owns_transaction=False`)
        en lugar de abrir la suya: el descuento y el cobro tienen que caer o
        confirmarse juntos.
        """
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        # La ubicación y el lote salen de la RESERVA, no de la sucursal. El
        # saldo se identifica por (producto, sucursal, almacén, estado,
        # ubicación, lote): si el movimiento descontara de una ubicación
        # distinta de la que retuvo la reserva, estaría tocando OTRA fila de
        # saldo — la retenida se quedaría retenida para siempre y la otra se
        # iría a negativo. No da error: parte el stock en dos filas.
        lines = [
            InventoryMovementLine.create(
                product_id=reservation.product_id, quantity=reservation.quantity,
                from_location_id=reservation.location_id, lot_id=reservation.lot_id,
                from_status=InventoryStatus.AVAILABLE, reason_code="SALE")
            for reservation in reservations if reservation.quantity > 0
        ]
        if not lines:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id=self._branch_id,
            warehouse_id=self._branch_id, source_module="sales",
            source_document_type="SALE", source_document_id=str(sale_id),
            operation_id=f"{sale_id}:sale-issue",
            created_by_user_id=str(self._actor_user_id), lines=lines)
        result = PostInventoryMovementUseCase().execute(
            self._connection, movement, actor_user_id=str(self._actor_user_id),
            owns_transaction=False)
        if not result.success:
            # Nunca se sigue adelante con un descuento fallido: cumplir las
            # reservas soltaría la retención de mercancía que sigue contada.
            raise InventoryReservationFailedError(
                result.message or "No se pudo descontar el inventario de la venta.")

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
