# LOSS-12 — Transferencias y recepciones

## Alcance

- Conversión del hecho `TRANSFER_DIFFERENCE_RESOLVED / CREATE_LOSS_CASE` en un expediente Losses.
- Cálculo `Decimal` de faltante de cantidad y peso, sin convertir sobrantes en pérdidas.
- Conservación de transferencia, diferencia, resolución, recepción y etapa responsable.
- Sugerencia de responsabilidad por tránsito, origen, destino u otra etapa.
- Reclamaciones contra transportista, sucursal, empleado, proveedor u otra parte.
- Idempotencia UUIDv7 y eventos outbox para expediente y reclamación.

## Inventario

La recepción de Transferencias ya postea la cantidad observada mediante
`CanonicalInventoryTransferGateway`. LOSS-12 exige que exista ese movimiento
`TRANSFER_RECEIPT` y almacena `POSTED_BY_TRANSFER_RECEIPT` como efecto físico.
No genera ajustes ni un segundo movimiento, evitando duplicar el faltante.

## Persistencia

- `loss_transfer_links`: trazabilidad, responsabilidad y vínculo con el posteo de recepción.
- `loss_transfer_claims`: parte responsable, valor reclamado, evidencia y estado.
- Se reutilizan `loss_cases`, `loss_lines`, `loss_outbox` y
  `loss_processed_operations`.

## Permisos

- `LOSSES_TRANSFER_LINK`: crear el expediente desde la resolución autorizada.
- `LOSSES_MANAGE_CLAIMS`: abrir y administrar reclamaciones de transferencia.

## Validación manual

1. Despachar y recibir parcialmente una transferencia.
2. Revisar la diferencia y resolverla con `CREATE_LOSS_CASE`.
3. Verificar un único movimiento de recepción en Inventario.
4. Confirmar el expediente con cantidad/peso faltante y etapa responsable.
5. Abrir una reclamación y repetir el mismo `operation_id` para validar replay.
