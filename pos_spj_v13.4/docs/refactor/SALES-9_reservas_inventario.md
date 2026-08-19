# SALES-9 — Inventory reservations (POS-9 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-8_carrito.md`.

## Alcance ejecutado

Master prompt §67, fase POS-9: "Reserve. Confirm. Release. Expire. Tests." Sección 20
(RESERVA DE INVENTARIO) exige un `ReserveInventoryForSaleUseCase` que valide stock, cree
reserva, sea idempotente y se libere en cancelación — pero "Ventas no modifica inventario
directamente" (§6), así que esta fase es sobre **integrar**, no reconstruir. SALES-0 ya había
clasificado `core/services/stock_reservation_service.py::StockReservationService` como REUSE.

## Hallazgo crítico: `StockReservationService.reservar()` estaba roto en producción, no solo para UUIDv7

Antes de escribir el cliente de integración, ejecuté `reservar()` directamente contra un
esquema real (no solo lo leí) para verificar compatibilidad con ids UUIDv7. Encontré **tres
bugs reales, dos de ellos catastróficos y previos a cualquier trabajo de esta fase**:

1. `payload = [{"producto_id": int(i["id"]), ...} for i in items]` — fuerza `int()` sobre el id
   de producto. Con un `product_id` UUIDv7 (el estándar canónico desde hace varias fases),
   esto lanza `ValueError: invalid literal for int()` inmediatamente.
2. **`stock_reservas.id` (`TEXT NOT NULL PRIMARY KEY`, sin `DEFAULT`) nunca se incluía en su
   propio `INSERT`** — el código generaba `reserva_id = new_uuid()` DESPUÉS del `INSERT`, y
   nunca lo usaba en él. Verificado ejecutando el método: `NOT NULL constraint failed:
   stock_reservas.id`.
3. **`stock_reserva_detalles.id`** (misma forma de columna) tampoco se incluía en su propio
   `INSERT`.

Los bugs 2 y 3 significan que **`reservar()` fallaba para CUALQUIER llamador, con cualquier
tipo de id, contra el esquema real** — no un problema exclusivo de UUIDv7. La razón por la que
nadie lo había detectado: el único archivo de test que ejercía este método
(`tests/test_fase5_stock_reservations.py`) tenía su propio fixture roto (nunca creaba
`stock_reservas`/`stock_reserva_detalles`, y consultaba una tabla `branch_inventory` que
`stock_disponible()` ni siquiera lee — lee `inventory_stock`), así que **8 de sus 14 tests ya
fallaban antes de esta fase**, ocultando el bug real detrás de un error de fixture distinto
("no such table"). En producción, cualquier cajero que presionara "Suspender" en
`modulos/ventas.py` vería el diálogo **"Stock insuficiente"** — un mensaje totalmente engañoso;
el error real era una violación de constraint no relacionada con disponibilidad de stock.

**Los tres bugs se corrigieron** en `core/services/stock_reservation_service.py` (mínimo,
quirúrgico: quitar el `int()`, generar `reserva_id` antes del `INSERT` e incluirlo en ambas
tablas). Verificado end-to-end con un script manual antes y después del fix, y con el propio
`tests/test_fase5_stock_reservations.py` (su fixture también se corrigió — creaba
`branch_inventory` en vez de `inventory_stock`, y nunca creaba las tablas de reserva — pasó de
6/14 a 13/14; el único test restante que falla es una aserción de código-fuente sobre
`modulos/ventas.py::finalizar_venta` que ya estaba desactualizada respecto al archivo real,
confirmado no relacionado a esta fase — ver "Hallazgos no corregidos" abajo).

## Entregables

**Dominio**: `InventoryReservationFailedError` (nueva excepción, exacta del listado §64) en
`backend/domain/sales/exceptions.py`. Campo `inventory_reservation_id: str | None` agregado a
`Sale` (`backend/domain/sales/entities.py`) — referencia cruzada de solo lectura hacia el
sistema de reservas de Inventario (Sales no interpreta ni valida este valor, solo lo porta,
consistente con §6).

**Esquema**: columna `sales.inventory_reservation_id` — agregada al DDL de
`sales_schema.py` (creaciones nuevas) + migración `199_sales_inventory_reservation_column.py`
(vía el helper `ensure_column` ya existente en `m000_base_schema.py`, para bases ya
bootstrapeadas con la migración 198).

**Infraestructura**: `backend/infrastructure/integrations/sales_inventory_client.py::
SalesInventoryClient` — el único punto de esta pipeline donde Decimal se convierte a `float`,
exactamente en el borde donde el mundo Decimal-only de Sales toca una tabla legacy que no le
pertenece y no se está reconstruyendo aquí. `reserve_for_sale(sale)` usa `sale.id` (siempre
UUIDv7) como `folio` — la columna `stock_reservas.folio` es `UNIQUE`, así que reservar dos
veces para la misma venta con el mismo id viola la constraint, dando idempotencia real a nivel
de base de datos además de la que se implementa en el caso de uso.

**Aplicación** (`backend/application/sales/use_cases/inventory_use_cases.py`):
`ReserveInventoryForSaleUseCase` (idempotente: si `sale.inventory_reservation_id` ya existe,
retorna la reserva existente sin crear una segunda), `ConfirmInventoryReservationUseCase`,
`ReleaseInventoryReservationUseCase`, `ExpireOrphanedInventoryReservationsUseCase` (sweep de
sistema, sin gate de permiso de usuario — mismo criterio que otros ganchos de barrido ya
documentados en este repositorio).

**Integración real, no solo paralela**: en vez de solo dejar los 4 casos de uso construidos y
sin conectar (el patrón "not done" que cada fase anterior tuvo que declarar), esta fase
**conecta de verdad** `SuspendSaleUseCase`/`CancelSaleUseCase` (SALES-6) a
`SalesInventoryClient`: suspender ahora reserva inventario antes de transicionar a `SUSPENDED`
(atómico — si la reserva falla, la venta NO se suspende, nada se persiste); cancelar libera la
reserva si existe. Esto refleja el comportamiento **real** ya existente en
`modulos/ventas.py::suspender_venta` (confirmado en la auditoría de SALES-0: ya llama
`StockReservationService.reservar()` al suspender) — no la secuencia más abstracta "reservar en
cada línea agregada" que sugiere el diagrama de flujo de la sección 20. Documentado como la
misma reconciliación "el comportamiento real gana sobre la lista abstracta" de cada fase
anterior (SALES-1, SALES-3, SALES-5).

**Tests** (14 nuevos en `tests/unit/test_sales_inventory_reservation.py`, todos verdes en la
primera corrida; 209 en total en la suite SALES-0..9 combinada, cero regresiones tras corregir
2 fixtures de fases anteriores — ver abajo): cliente de reservas con id UUIDv7 real (regresión
directa del bug 1), stock insuficiente traducido a excepción de dominio, confirmar/liberar,
expirar huérfanas, idempotencia del caso de uso, y — el par más importante — verificación de
que `SuspendSaleUseCase` reserva de verdad (incluyendo que un fallo de stock NO deja la venta a
medio suspender) y que `CancelSaleUseCase` libera de verdad la reserva.

**Regresión en 2 fixtures de fases anteriores, corregida**: cambiar `SuspendSaleUseCase` para
que dependa de verdad de las tablas de reserva rompió 3 tests que ya pasaban en
`test_sales_use_cases.py`/`test_sales_query_service.py` (sus fixtures solo llamaban
`create_sales_schema`, sin sembrar inventario) — se agregaron las mismas tablas mínimas +
siembra de stock abundante a esos dos fixtures. Comportamiento correcto y esperado: antes de
esta fase, suspender no dependía de inventario real; ahora sí, como debe ser.

## Hallazgos no corregidos, confirmados no relacionados

- `tests/test_fase5_stock_reservations.py::test_ui_pasa_reserva_id_al_uc_antes_de_aplicar_resultado`
  — verifica que el código fuente de `modulos/ventas.py::finalizar_venta` contenga el literal
  `"reserva_id=self._reserva_activa_id"`. El método real ya no lo contiene (llama
  `self._procesar_venta_via_uc(carrito_limpio, datos_pago, usuario, cliente_id)` sin ese
  argumento) — desactualización de la propia UI legacy, no causada ni relacionada con esta
  fase. No se tocó `modulos/ventas.py`.
- `tests/integration/test_inventory_availability_uses_reservations.py`,
  `tests/integration/test_sales_inventory_stock_consistency.py`,
  `tests/test_fase_g_concurrency.py` (varios) — fallan con `no such table: stock_reservas`/
  `stock_reserva_detalles`. Confirmado (grep de sus propios fixtures) que **ninguno de estos
  archivos crea esas tablas nunca** — el mismo tipo de bit-rot de fixture que
  `test_fase5_stock_reservations.py` tenía antes de esta fase, en archivos distintos, fuera de
  alcance de POS-9 corregir todos.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se tocó `modulos/ventas.py`.** El bug de `reservar()` corregido aquí beneficia
  inmediatamente al flujo legacy real (`suspender_venta` ya lo llama), pero esta fase no probó
  ni modificó ese archivo — el arreglo se verificó contra el nuevo stack y contra el propio
  test suite legacy de `StockReservationService`.
- **`AddSaleLineUseCase` no reserva por línea.** Como se documentó arriba, la reserva ocurre al
  suspender (comportamiento real), no en cada línea — una decisión consciente, no un olvido.
- **Sin re-reserva al reanudar.** `ResumeSaleUseCase` no vuelve a calcular/ajustar la reserva
  si el carrito cambió mientras estaba suspendida — la reserva original simplemente sigue
  asociada. Ampliar esto (diff de reserva) queda fuera de alcance de esta fase.
- **`ConfirmInventoryReservationUseCase` no está conectado a ningún flujo de checkout real** —
  como con `CompleteSaleUseCase` (nunca construido, SALES-6), confirmar depende de pago
  confirmado (POS-13/14), que no existe todavía. El caso de uso está listo y probado.

## Siguiente fase

El master prompt continúa con POS-10 (Cliente: Search, Assign, Quick create, Loyalty card
scan, Tests). Confirmar alcance con el usuario antes de asumir — dado el patrón de esta
pipeline, es probable que "Assign" ya esté cubierto (`AssignCustomerToSaleUseCase`, SALES-6) y
el resto requiera integración con el bounded context de Clientes/CRM (ya extensamente
construido en este repositorio, ver memoria `crm_enterprise_transformation`).
