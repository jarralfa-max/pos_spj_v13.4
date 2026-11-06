# SDLC-ORD-004 — Pedido cobrado y completado nunca descuenta inventario; su reverso suma existencia que nunca salió

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** auditoría `docs/audits/DELIVERY_REFACTOR_AUDIT.md` (Riesgos detectados §1: "Pedido entregado puede quedar sin commit de inventario") y `docs/refactor/ORD-30_validacion_final.md`, re-verificados en el estrato canónico `backend/*/orders_delivery` (`/sdlc-plan` Modo B, 2026-10-31)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** —

## Problema
En el legacy, el riesgo era que el descuento de inventario de un pedido entregado se perdiera si fallaba el EventBus. En el código canónico de hoy el descuento **no existe**. Al confirmar un pedido se reserva la existencia. Al cobrarlo y completarlo, la venta se cierra con `settle_inventory=False` porque se supone que Pedidos descuenta por su cuenta, pero Pedidos no tiene ninguna operación de descuento. Resultado: la existencia nunca baja y la reserva queda retenida para siempre. Si después se reversa el pedido, Ventas registra una devolución (+1) de mercancía que nunca salió del inventario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `backend/infrastructure/integrations/orders_delivery_sales_client.py:133-138` — comentario "Pedidos descuenta inventario por su propio cliente (ORD-8)" y `CheckoutSaleUseCase(..., settle_inventory=False, ...)`.
- `backend/application/orders_delivery/use_cases/inventory_use_cases.py:11-18` — su docstring dice que el *Commit* (convertir la reserva en descuento real) "deliberately NOT built here".
- `backend/infrastructure/integrations/orders_delivery_inventory_client.py:39,43,63` — el cliente solo tiene `is_available`, `reserve_line` y `release`. No existe ningún método de descuento.
- Grep de `DeliveryEvents.`/`OrderEvents.`/`DELIVERY_COMPLETED` fuera de `backend/*/orders_delivery`: cero consumidores. Ningún handler de Inventario descuenta al completar.
- **Reproducción** con una sonda en el directorio temporal (no versionada) que reutiliza los fixtures de `tests/integration/test_orders_delivery_sales_finance_use_cases.py` (esquema en memoria, no la BD real): capturar → confirmar → reservar → preparar → listo → proyectar venta → cobrar en efectivo → `CompletePickupUseCase` (pedido `COMPLETED`):
  - `inventory_balances` = `[('100', '1')]`: cantidad intacta y 1 reservado.
  - `inventory_reservation.status` = `CONFIRMED`, `expires_at` = `NULL`.
  - Ninguna fila en `inventory_ledger`.
  - Después de `ReverseCustomerOrderUseCase` (éxito, "Pedido reembolsado"), `inventory_balances` = `[('100','1'), ('1','0')]`. La única entrada del ledger es `SALE_RETURN`/`SALE_REVERSAL` +1, y la reserva sigue `CONFIRMED`. La existencia total pasa de 100 a 101 sin que haya salido nada. La fila nueva cae en otra `location_id` (`''` contra la sucursal), igual que en SDLC-INV-003.
- No se probó la entrega a domicilio (`DeliveryJob` → intento exitoso → cobro del repartidor). Por el grep de arriba no hay descuento en ninguna ruta, pero esa ruta no se reprodujo: **no verificado por ejecución**.
- Ninguna prueba de `tests/*/test_orders_delivery_*` revisa `inventory_balances` ni el ledger después de completar (grep). La suite curada pasa completa: `405 passed` (unit + integration `test_orders_delivery_*` y `tests/architecture/test_orders_delivery_permissions_are_granular.py`).

## Impacto
Cada pedido de mostrador o a domicilio que se cobra deja existencia fantasma. El reservado crece con cada pedido y reduce lo disponible para el POS, y cada reverso infla la existencia. Afecta inventario, costo de ventas y reabasto. Es inventario duplicado (P0).

## Objetivo
- Al completar un pedido cobrado, la existencia baja una sola vez por línea, con la cantidad final (`final_quantity`/`final_weight` si hubo ajuste de peso, si no la preparada). La reserva pasa a consumida en la misma transacción. Una prueba verifica el balance y el ledger.
- El reverso de un pedido completado devuelve exactamente lo que salió. Un pedido que nunca descontó no suma existencia. Hay prueba.
- Ningún doble descuento entre Pedidos y Ventas (prueba con `settle_inventory` en ambos valores).
- Las reservas `CONFIRMED` de pedidos ya completados o reversados en bases existentes tienen un plan de saneamiento, probado sobre una copia de la BD.

## Alcance
- **Incluye:** Descuento de inventario de Pedidos al completar (mostrador y domicilio), reverso coherente, saneamiento de reservas huérfanas y pruebas de regresión antes del cambio.
- **No incluye:** Unificar ubicaciones de stock (SDLC-INV-003), dinero de Pedidos (SDLC-ORD-001) ni drenado de outbox (SDLC-ORD-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; Pedidos nunca escribe tablas de Inventario directamente (usa los casos de uso de Inventario por su cliente); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`docs/refactor/ORD-8_inventario.md` (Commit pospuesto hasta ORD-10), `docs/refactor/ORD-22*` (Ventas/Finanzas); Fase 6 del pipeline de integración ERP (memoria: "el cobro no debe volver a descontar"); SDLC-INV-003 (ubicaciones distintas por flujo); SDLC-ORD-001.

## Preguntas abiertas
- ¿El descuento debe ocurrir al **entregar/recoger** (`COMPLETED`) o al **despachar** (sale de la sucursal)? Hoy no ocurre en ninguno de los dos. al despachar 
- ¿Cuántas reservas `CONFIRMED` de pedidos completados hay en la base real? Hay que medirlo sobre una copia antes de diseñar el saneamiento. ni uno, estamos en desarrollo
