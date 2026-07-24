# TRF-8 — Picking

## Alcance implementado

- **Listas:** `BuildTransferPickingListUseCase` expone líneas reservadas para picking sin SQL ni repositorios en UI.
- **Barcode:** `ConfirmTransferPickingUseCase` acepta un puerto `TransferBarcodeValidator` para validar escaneos.
- **Lotes:** si una línea requiere lote, confirmar picking exige `lot_id`.
- **Ubicaciones:** cada escaneo requiere `location_id`.
- **Parcial:** `StockTransfer.record_pick` conserva `PARTIALLY_PICKED` cuando quedan líneas/cantidades pendientes.
- **Seguridad:** listas y arranque validan `TRANSFERS_PICK`; confirmación valida `TRANSFERS_PICK_CONFIRM`.
- **Eventos:** arranque y confirmación emiten `TRANSFER_PICKING_STARTED` y `TRANSFER_PICKED`.

## Decisiones

- Picking no mueve inventario; consume la reserva ya creada por TRF-7.
- La validación de barcode/lote/ubicación se delega a un puerto para integrarse después con hardware y catálogos.
- La UI solo captura escaneos y consume DTOs; no calcula cantidades pickeadas ni consulta inventario.

## Tests TRF-8

- Construcción de lista de picking desde líneas reservadas.
- Inicio de picking con evento canónico.
- Confirmación parcial con lote, ubicación, barcode y peso variable.
- Validación de lote requerido y operación duplicada.
