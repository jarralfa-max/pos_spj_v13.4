# SALES-15 — Suspensiones (POS-15 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-14_checkout.md`.

## Alcance ejecutado

Master prompt §67, fase POS-15: "Persist. Resume. Expire. Counter. Tests."

A diferencia de fases anteriores, "Persist" y "Resume" ya estaban construidos —
`SuspendSaleUseCase`/`ResumeSaleUseCase` existen desde SALES-6, con reserva real de inventario al
suspender desde SALES-9. Esta fase confirma esa cobertura con una regresión corta y construye los
dos huecos reales: "Expire" y "Counter".

## El hueco real de "Expire"

SALES-9 ya construyó `ExpireOrphanedInventoryReservationsUseCase` — pero ese sweep solo libera el
lado de INVENTARIO de una reserva vencida (`stock_reservas.expires_at`, TTL de 30 minutos). Nunca
toca la VENTA misma: una venta suspendida cuya reserva ya expiró por ese lado queda exactamente
igual — `status=SUSPENDED`, sosteniendo un `inventory_reservation_id` que Inventario ya liberó en
silencio por debajo. Confirmado leyendo el código, no asumido.

Tampoco existe ningún precedente real de un umbral de expiración para una venta suspendida —
`modulos/ventas.py::ventas_en_espera` (el dict en memoria) nunca expira por tiempo, solo se limpia
al reanudar/cancelar o al reiniciar la app. Por eso `max_age_hours` es un parámetro que el llamador
decide, no una regla de negocio inventada sin precedente (misma disciplina aplicada a
Promociones/Cupones/Vales en SALES-11).

## Entregables

**Aplicación**:
- `backend/application/sales/use_cases/suspension_sweep_use_cases.py::
  ExpireSuspendedSalesUseCase` — sweep de sistema (sin gate de `SalesPermissions`, mismo
  razonamiento que `ExpireOrphanedInventoryReservationsUseCase`): busca ventas SUSPENDED
  anteriores a un corte, las cancela (`Sale.cancel()`, transición SUSPENDED→CANCELLED ya válida
  desde SALES-3), libera su reserva de inventario si tiene una, y encola `SaleEvents.CANCELLED`
  al outbox con `expired=true` en el payload para distinguirlo de una cancelación manual.
- `SaleQueryService.count_suspended()` — el "Counter": un conteo liviano, separado de
  `list_suspended()` (que hidrata cada `Sale`/`SaleLine` completo). Precedente real: el propio
  botón "Reanudar" de `modulos/ventas.py` ya muestra
  `f"▶️ Reanudar ({len(self.ventas_en_espera)})"` — este método es el equivalente real para la
  pila nueva.

**Infraestructura/Repositorio**: `SaleRepository.list_suspended_before(cutoff_iso)` — a
diferencia de `list_suspended()` (por sucursal), este es cross-sucursal por diseño: un sweep de
sistema, no una acción de un cajero.

**Tests** (11 nuevos en `tests/unit/test_sales_suspension.py`, todos verdes tras dos correcciones
de fixture — ver abajo): round-trip de persistencia y reanudación (regresión corta, la cobertura
completa ya vive en la suite de SALES-6/9), expira una venta vieja y la cancela, libera su reserva
de inventario real, no toca ventas suspendidas recientes, emite `SALE_CANCELLED` al outbox con la
marca `expired`, barre múltiples sucursales en una sola llamada; contador en cero sin ventas
suspendidas, cuenta correctamente por sucursal sin filtrar entre sucursales, baja tras reanudar,
exige el permiso `VIEW`.

**Dos correcciones de fixture encontradas en la primera corrida, no del código de producción**:
(1) el fixture asumía que `SuspendSaleUseCase` solo reserva inventario condicionalmente — en
realidad SIEMPRE lo hace (comportamiento real de SALES-9, confirmado leyendo el use case, no
recordado de memoria) — sin stock sembrado, `reserve_for_sale` falla y la suspensión entera falla
silenciosamente si el test no revisa `result.success`; (2) una query de test buscaba por
`entity_id` en el payload sin filtrar por `event_name`, y encontraba el evento `SALE_STARTED`
(que comparte el mismo `entity_id`) en vez de `SALE_CANCELLED`. Ambas corregidas en el propio
archivo de test, no en el código nuevo.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se inventó un umbral de expiración por defecto.** `max_age_hours` es responsabilidad de
  quien invoque el sweep (una tarea programada futura, fuera de alcance — ningún dispatcher de
  este tipo existe en este repositorio, mismo hallazgo repetido desde SALES-4/5/9/14).
- **No se tocó `modulos/ventas.py`.** El diccionario en memoria `ventas_en_espera` sigue siendo
  la fuente real de ventas suspendidas en la UI viva — el propio P0 que SALES-0 marcó sigue sin
  resolver: la UI no persiste sus suspensiones en la pila nueva.
- **No se construyó ningún job/scheduler que invoque `ExpireSuspendedSalesUseCase`
  periódicamente** — es un caso de uso invocable, no un proceso en ejecución.

## Siguiente fase

El master prompt continúa con POS-16 (Cancelaciones y devoluciones) — confirmar alcance con el
usuario antes de asumir.
