# TRF-17 — Integraciones canónicas

## Inventario

`CanonicalInventoryTransferGateway` compone una sola ruta por operación:

- reserva y asignación;
- despacho a tránsito;
- recepción y disposición de calidad;
- despacho y recepción de devolución.

No contiene fallback a `InventoryEngine`, SQL ni escritura directa de balances.

## Productos y Calidad

- `CanonicalProductTransferProfileQueryService` compone unidades, peso variable, lote/caducidad y perfil de calidad.
- Transferencias no consulta `productos` directamente.
- `TransferQualityGateway` solicita inspección; Calidad conserva la autoridad para liberar o bloquear.

## Orígenes de necesidad

- Ventas: `CUSTOMER_ORDER_REQUIRES_TRANSFER`.
- POS: `STOCK_REPLENISHMENT_REQUIRED`.
- Producción: `PRODUCTION_MATERIAL_TRANSFER_REQUIRED`.
- Forecast: `TRANSFER_SUGGESTION_REQUESTED`.

Los handlers solo crean solicitudes o propuestas. No aprueban, reservan ni mueven inventario.

## Mermas, Costos y Finanzas

- Una resolución `CREATE_LOSS_CASE` se transforma en `LOSS_CASE_REQUESTED` mediante gateway.
- Costos/Finanzas reciben hechos de despacho, recepción, diferencia confirmada, pérdida confirmada y devolución completada.
- Transferencias no conoce cuentas, pólizas, causas finales de merma ni métodos de costeo.

## Ventas y POS

`OrderTransferStatusQueryService` expone estado, llegada esperada y disponible para prometer sin entregar repositorios ni SQL a consumidores.
