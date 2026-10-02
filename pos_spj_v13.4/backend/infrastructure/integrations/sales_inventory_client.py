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

PRODUCTOS COMPUESTOS (decisión del usuario, 2026-09-24). Un producto con
receta de «Explosión de venta» o con combo activo en Productos se surte con sus
COMPONENTES: se reservan, se descuentan y, al devolver, se reponen los
componentes. La composición la resuelve Productos
(`SalesFulfillmentQueryService`, anidados incluidos). `confirm` descuenta lo
reservado, así que sigue a la explosión sin cambios. NO confundir con la
reconstrucción inversa de abajo, que es la dirección OPUESTA (parte → base) y
sale del esquema de corte.

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
    ExpireReservationsUseCase,
    FulfillReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.application.inventory.use_cases.sale_reservation_use_cases import (
    ReserveStockForSaleUseCase,
    plan_sale_issue,
)
from backend.domain.sales.entities import Sale
from backend.domain.sales.exceptions import (
    InventoryReservationFailedError,
    InventoryShortageError,
)
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
        self._warehouse_id: str | None = None

    @property
    def warehouse_id(self) -> str:
        """El almacén del que vende la sucursal (Fase 6, 2026-09-18).

        Antes era SIEMPRE la sucursal (`warehouse_id = branch_id`), un parche
        documentado en `provision_default_warehouse.py` a la espera de que las
        sucursales tuvieran almacenes reales. Ya los tienen, y Compras recibe
        en ellos: la venta buscaba la existencia en una fila que nadie llena y
        nunca la encontraba.

        - un almacén activo de la sucursal marcado para venta → ése;
        - varios → error claro: no se adivina de cuál descontar;
        - ninguno → la convención anterior (la sucursal), para no romper
          sucursales que aún no tienen almacén.
        """
        if self._warehouse_id is None:
            from backend.application.logistics.warehouse_directory import (
                WarehouseDirectoryQueryService,
            )
            almacenes = WarehouseDirectoryQueryService(
                self._connection).sales_warehouses_for_branch(self._branch_id)
            if len(almacenes) > 1:
                raise InventoryReservationFailedError(
                    "La sucursal tiene varios almacenes habilitados para venta; "
                    "deja sólo uno habilitado para venta en Almacenes.")
            self._warehouse_id = almacenes[0] if almacenes else self._branch_id
        return self._warehouse_id

    # ── reservar ─────────────────────────────────────────────────────────
    def reserve_for_sale(self, sale: Sale) -> str:
        """Reserva TODAS las líneas de la venta. Devuelve el asa (`sale.id`).

        Inventario elige de qué saldos sale cada producto
        (`ReserveStockForSaleUseCase`: lote y ubicación incluidos, estrategia
        configurada, FEFO por omisión). Antes se reservaba un único saldo
        buscado SIN lote, y como Compras recibe siempre con lote, nada de lo
        comprado se podía cobrar (re-auditoría POS, 2026-10-01).

        Si algún producto no alcanza, se lanza `InventoryShortageError` (el
        único fallo que admite autorizar la venta sin existencia) y se liberan
        las reservas ya creadas en este intento: una venta no puede quedarse
        reteniendo la mitad de su mercancía indefinidamente.
        """
        use_case = ReserveStockForSaleUseCase(self._authorization)
        reservados = 0
        for product_id, cantidad in self._quantities_by_product(sale).items():
            self._top_up_via_reconstruction_if_short(
                product_id=product_id, needed=cantidad, sale_id=sale.id)
            result = use_case.execute(
                self._connection, product_id=product_id, branch_id=self._branch_id,
                warehouse_id=self.warehouse_id, quantity=cantidad,
                source_document_id=sale.id,
                operation_id=_reserve_operation_id(sale.id, product_id),
                actor_user_id=self._actor_user_id, lot_required=False)
            if not result.success:
                self._release_all(sale.id, reason="reserva incompleta")
                if result.error_code == "INSUFFICIENT_AVAILABILITY":
                    disponible = result.data.get("available", Decimal("0"))
                    raise InventoryShortageError(
                        f"{self._product_name(product_id)}: disponible {disponible}, "
                        f"se venden {cantidad}")
                raise InventoryReservationFailedError(result.message)
            reservados += 1
        if not reservados:
            raise InventoryReservationFailedError("La venta no tiene líneas que reservar.")
        return sale.id

    def _product_name(self, product_id: str) -> str:
        """Para los mensajes al cajero: el nombre, no el identificador."""
        try:
            row = self._connection.execute(
                "SELECT name FROM products WHERE id = ?", (product_id,)).fetchone()
        except Exception:
            logger.exception("nombre de %s no consultable", product_id)
            row = None
        return str(row[0]) if row and row[0] else product_id

    def _available(self, product_id: str) -> Decimal:
        try:
            return InventoryAvailabilityQueryService(self._connection).get_availability(
                product_id=product_id, branch_id=self._branch_id,
                warehouse_id=self.warehouse_id).available
        except Exception:
            logger.exception("disponibilidad de %s no consultable", product_id)
            return Decimal("0")

    def _composition(self):
        from backend.application.products.queries.sales_fulfillment_query_service import (
            SalesFulfillmentQueryService,
        )
        return SalesFulfillmentQueryService(self._connection)

    def _explode(self, product_id: str, quantity: Decimal) -> dict[str, Decimal]:
        from backend.application.products.queries.sales_fulfillment_query_service import (
            CompositeDefinitionError,
        )
        try:
            return self._composition().explode(product_id, quantity)
        except CompositeDefinitionError as exc:
            raise InventoryReservationFailedError(str(exc)) from exc

    def _quantities_by_product(self, sale: Sale) -> dict[str, Decimal]:
        """Lo que SALE del inventario por la venta, por producto: un compuesto
        se reemplaza por sus componentes (Productos define cuáles).

        Se agrupa porque el mismo producto puede aparecer en varias líneas (dos
        pesadas del mismo corte, o el mismo componente en dos combos) y la
        reserva canónica es por producto.
        """
        totales: dict[str, Decimal] = {}
        for line in sale.lines:
            for product_id, cantidad in self._explode(
                    line.product_id, line.quantity.value).items():
                totales[product_id] = totales.get(product_id, Decimal("0")) + cantidad
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
            product_id=product_id, branch_id=self._branch_id, warehouse_id=self.warehouse_id)
        shortfall = needed - availability.available
        if shortfall <= 0:
            return
        try:
            result = ReconstructBaseProductUseCase(self._authorization).execute(
                self._connection, product_id=product_id, quantity=shortfall,
                branch_id=self._branch_id, warehouse_id=self.warehouse_id,
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
    def confirm(self, reservation_handle: str, *, sale_id: str, folio: str,
                unit_costs: dict | None = None) -> None:
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

        self._post_sale_issue(reservations, sale_id=sale_id, unit_costs=unit_costs)

        use_case = FulfillReservationUseCase(self._authorization)
        for reservation in reservations:
            result = use_case.execute(
                self._connection, reservation_id=reservation.id,
                # Por reserva, no por producto: un producto vendido de dos
                # lotes tiene dos reservas, y con la misma identidad la segunda
                # se tomaría por un reintento de la primera.
                operation_id=f"{sale_id}:fulfill:{reservation.id}",
                actor_user_id=self._actor_user_id,
            )
            if not result.success:
                raise InventoryReservationFailedError(result.message)

    def issue_without_stock(self, sale: Sale, *, unit_costs: dict | None = None) -> None:
        """Salida AUTORIZADA sin existencia suficiente (inventario negativo).

        Sólo la llama el cobro después de que otro usuario autorizó en caliente
        vender sin existencia (decisión del usuario, Fase 6). No hay reserva que
        cumplir: no alcanzaba para reservar. `NegativeInventoryPolicy` exige
        `allowed` + `authorized`; ambas cosas las da esa autorización, que el
        caso de uso de Ventas ya validó y deja auditada.
        """
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        costos = unit_costs or {}
        lines = []
        for product_id, cantidad in self._quantities_by_product(sale).items():
            if cantidad <= 0:
                continue
            # Lo que SÍ hay sale de sus lotes (misma estrategia que la reserva);
            # sólo el faltante queda en negativo, en el saldo sin lote. Antes
            # todo salía del saldo sin lote y el lote real quedaba intacto: la
            # mercancía vendida seguía contada.
            rebanadas, faltante = plan_sale_issue(
                self._connection, product_id=product_id, branch_id=self._branch_id,
                warehouse_id=self.warehouse_id, quantity=cantidad)
            for rebanada in rebanadas:
                lines.append(InventoryMovementLine.create(
                    product_id=product_id, quantity=rebanada.quantity,
                    from_location_id=rebanada.location_id, lot_id=rebanada.lot_id,
                    from_status=InventoryStatus.AVAILABLE, reason_code="SALE",
                    unit_cost=costos.get(product_id)))
            if faltante > 0:
                lines.append(InventoryMovementLine.create(
                    product_id=product_id, quantity=faltante,
                    from_location_id=self._branch_id,
                    from_status=InventoryStatus.AVAILABLE,
                    reason_code="SALE_WITHOUT_STOCK", unit_cost=costos.get(product_id)))
        if not lines:
            raise InventoryReservationFailedError("La venta no tiene líneas que descontar.")
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id=self._branch_id,
            warehouse_id=self.warehouse_id, source_module="sales",
            source_document_type="SALE", source_document_id=str(sale.id),
            operation_id=f"{sale.id}:sale-issue",
            created_by_user_id=str(self._actor_user_id), lines=lines)
        result = PostInventoryMovementUseCase().execute(
            self._connection, movement, actor_user_id=str(self._actor_user_id),
            negative_allowed=True, authorized=True, owns_transaction=False)
        if not result.success:
            raise InventoryReservationFailedError(
                result.message or "No se pudo descontar el inventario de la venta.")

    def _post_sale_issue(self, reservations, *, sale_id: str,
                         unit_costs: dict | None = None) -> None:
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
                from_status=InventoryStatus.AVAILABLE, reason_code="SALE",
                # El costo con que sale: el del libro de inventario, y el mismo
                # que Finanzas asienta como costo de venta.
                unit_cost=(unit_costs or {}).get(reservation.product_id))
            for reservation in reservations if reservation.quantity > 0
        ]
        if not lines:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id=self._branch_id,
            warehouse_id=self.warehouse_id, source_module="sales",
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
                operation_id=f"{reservation_handle}:release:{reservation.id}",
                actor_user_id=self._actor_user_id, reason=reason,
            )
            if not result.success:
                raise InventoryReservationFailedError(result.message)

    def _active_reservations(self, source_document_id: str):
        return ReservationRepository(self._connection).list_active_for_source_document(
            source_document_id)

    def _returnable_slices(self, sale_id: str, product_id: str):
        """(lote, ubicación, cantidad aún devolvible) de lo que la venta sacó de
        `product_id`, en el orden en que salió. Lo ya devuelto por devoluciones
        anteriores de la misma venta se descuenta, lote por lote."""
        from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
            InventoryLedgerRepository,
        )
        ledger = InventoryLedgerRepository(self._connection)
        salidas: dict[tuple, Decimal] = {}
        devueltas: dict[tuple, Decimal] = {}
        rows = self._connection.execute(
            "SELECT id, movement_type FROM inventory_ledger WHERE source_document_id = ?"
            " AND source_module = 'sales' ORDER BY occurred_at, id", (str(sale_id),)).fetchall()
        for movement_id, movement_type in rows:
            for line in ledger.get_lines(movement_id):
                if line["product_id"] != product_id:
                    continue
                cantidad = Decimal(str(line["quantity"] or "0"))
                if movement_type == "SALE_ISSUE":
                    clave = (line["lot_id"] or None, line["from_location_id"] or self._branch_id)
                    salidas[clave] = salidas.get(clave, Decimal("0")) + cantidad
                elif movement_type == "SALE_RETURN":
                    clave = (line["lot_id"] or None, line["to_location_id"] or self._branch_id)
                    devueltas[clave] = devueltas.get(clave, Decimal("0")) + cantidad
        return [(lot_id, location_id, libre)
                for (lot_id, location_id), salio in salidas.items()
                if (libre := salio - devueltas.get((lot_id, location_id), Decimal("0"))) > 0]

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

        # Un compuesto devuelto repone sus COMPONENTES: es lo que salió. Y cada
        # componente vuelve al lote y la ubicación de los que SALIÓ: reponer en
        # un saldo sin lote partía la existencia en dos filas y perdía la
        # trazabilidad del lote devuelto.
        lines = []
        for componente, cantidad in self._explode(product_id, quantity).items():
            if cantidad <= 0:
                continue
            pendiente = cantidad
            for lot_id, location_id, libre in self._returnable_slices(sale_id, componente):
                if pendiente <= 0:
                    break
                tomar = min(pendiente, libre)
                lines.append(InventoryMovementLine.create(
                    product_id=componente, quantity=tomar, lot_id=lot_id,
                    to_location_id=location_id,
                    to_status=InventoryStatus.AVAILABLE, reason_code=reason_code))
                pendiente -= tomar
            if pendiente > 0:
                lines.append(InventoryMovementLine.create(
                    product_id=componente, quantity=pendiente, to_location_id=self._branch_id,
                    to_status=InventoryStatus.AVAILABLE, reason_code=reason_code))
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_RETURN, branch_id=self._branch_id,
            warehouse_id=self.warehouse_id, source_module="sales",
            source_document_type=source_document_type, source_document_id=str(sale_id),
            operation_id=str(operation_id), created_by_user_id=str(actor_user_id), lines=lines)
        result = PostInventoryMovementUseCase().execute(
            self._connection, movement, actor_user_id=str(actor_user_id),
            owns_transaction=False)
        if not result.success:
            raise InventoryReservationFailedError(
                result.message or "No se pudo restaurar inventario.")
