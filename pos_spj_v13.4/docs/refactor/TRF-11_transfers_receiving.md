# TRF-11 — Recepción canónica

## Alcance entregado

- `ConfirmTransferReceiptUseCase` es la única ruta de aplicación para confirmar recepciones.
- Las recepciones totales y parciales se comparan contra el saldo despachado pendiente.
- El embarque se carga por puerto, debe pertenecer a la transferencia y su saldo limita cada recepción.
- Varias recepciones se acumulan en el agregado sin permitir exceder cantidad o peso en tránsito.
- Un QR opcional se valida mediante `TransferReceiptQrValidator`; la aplicación no interpreta el QR en UI.
- Las capturas offline exigen `operation_id`, `device_id` y `local_sequence` positiva, quedan con `sync_status=PENDING` y conservan idempotencia.
- Inventario recibe el asiento mediante `InventoryTransferGateway.receive`; Transferencias no escribe balances.

## Seguridad y eventos

- La recepción completa requiere `TRANSFERS_RECEIVE`.
- La recepción parcial requiere `TRANSFERS_PARTIAL_RECEIVE`.
- El alcance se revalida contra el nodo destino.
- Segregación impide que el mismo usuario que despachó confirme la recepción destino.
- Se recolecta `TRANSFER_RECEIVED` o `TRANSFER_PARTIALLY_RECEIVED` para publicación post-commit.
- Una línea rechazada produce una diferencia y `TRANSFER_DIFFERENCE_DETECTED`.

## Protecciones

- `operation_id` duplicada se rechaza antes de mutar el agregado.
- Cantidades y pesos aceptan únicamente `Decimal`, texto decimal o entero; `float` se rechaza.
- El esquema impone unicidad por operación y por secuencia local del dispositivo.
