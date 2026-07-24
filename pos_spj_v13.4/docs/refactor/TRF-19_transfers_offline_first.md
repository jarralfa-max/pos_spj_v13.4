# TRF-19 — Offline-first

## Operaciones permitidas

`OfflineTransferPolicy` habilita por configuración picking, pesaje, escaneo,
despacho, recepción, evidencias y temperatura. Aprobaciones críticas, cambio de
destino, resolución crítica, reversión y cancelación posterior al despacho no
forman parte del catálogo offline y por tanto no pueden sincronizarse.

## Envelope y secuencia

Cada operación lleva `operation_id`, `device_id`, `local_sequence`,
`transfer_id`, tipo cerrado, versión base y payload. El hash SHA-256 se calcula
sobre JSON canónico y permite distinguir un reintento idempotente de la
reutilización maliciosa o accidental del mismo `operation_id`.

## Sincronización y conflictos

- El servicio ordena por dispositivo y secuencia local.
- Una operación idéntica ya aplicada responde `SYNCED` sin ejecutarse de nuevo.
- Una secuencia no contigua produce `SEQUENCE_GAP`.
- Un mismo operation ID con payload diferente produce `PAYLOAD_MISMATCH`.
- Una versión agregada desactualizada produce `AGGREGATE_VERSION`.
- Solo operaciones sin conflicto llegan al executor canónico; este debe invocar
  los mismos UseCases online, nunca una ruta directa a Inventario.

La persistencia conserva estado, conflicto y unicidad tanto por `operation_id`
como por `(device_id, local_sequence)` para auditoría y reanudación.
