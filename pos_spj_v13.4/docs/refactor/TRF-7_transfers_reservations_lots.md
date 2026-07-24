# TRF-7 — Reservas y asignación de lotes

## Alcance implementado

- **Reserva:** `ReserveTransferInventoryUseCase` reserva líneas aprobadas y mueve el agregado a `RESERVED`.
- **Ruta canónica:** la reserva consume exclusivamente `InventoryTransferGateway.reserve`; no existe fallback a `InventoryEngine`.
- **FEFO:** `LotAllocationPolicy` asigna lotes disponibles por fecha de caducidad más próxima.
- **Ubicaciones:** cada asignación conserva `location_id` junto con `lot_id`.
- **Peso variable:** la asignación reserva simultáneamente cantidad y peso Decimal-only.
- **Idempotencia:** el use case valida `operation_exists` y registra `TRANSFER_RESERVE`.
- **Eventos:** la reserva emite `TRANSFER_RESERVED` y, si asigna lotes, `TRANSFER_ALLOCATED`.

## Decisiones

- La transferencia no calcula disponibilidad desde tablas; recibe candidatos desde un puerto de lectura.
- La política FEFO ignora candidatos que no están en `AVAILABLE`; Calidad seguirá siendo dueña de bloqueos técnicos.
- TRF-8 usará las asignaciones de lote/ubicación como base para picking, sin volver a leer inventario desde UI.

## Tests TRF-7

- Reserva con gateway canónico de Inventario.
- Asignación FEFO con lotes y ubicaciones.
- Peso variable con Decimal.
- Duplicado por `operation_id`.
- Error explícito si se solicita FEFO sin puerto de disponibilidad.
