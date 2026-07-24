# TRF-14 — Cárnicos y cadena de frío

## Modelo entregado

- Las líneas recibidas conservan simultáneamente cantidad, piezas enteras Decimal y peso real Decimal.
- Lote, temperatura de recepción y caducidad forman parte de la observación logística, incluida la captura ciega.
- `ProductTransferProfileQueryService` aporta las reglas de peso variable, lote, calidad y temperatura; Transferencias no lee Product Master directamente.
- `ColdChainTransferPolicy` evalúa límites de temperatura configurados y caducidad contra una fecha inyectada.
- Picking exige temperatura para líneas controladas, despacho la exige para una transferencia fría y custodia conserva la lectura del relevo.
- Los estados de cadena de frío y disposición de calidad usan catálogos cerrados.

## Calidad e inventario

- Mercancía vencida o fuera de rango queda en cuarentena y solicita inspección mediante `TransferQualityGateway`.
- Productos con inspección obligatoria quedan `PENDING_INSPECTION` aunque la temperatura sea conforme.
- Transferencias no libera mercancía: el recibo completo se entrega a `InventoryTransferGateway` para respetar su disposición de calidad.
- La solicitud de calidad conserva transferencia, embarque, recibo, producto, línea, lote, motivo y `operation_id`.

## Protecciones

- Un producto catch-weight exige piezas y peso positivos.
- Las piezas deben ser un Decimal entero; se rechazan fracciones y `float`.
- Un producto controlado por lote no puede recibirse sin `lot_id`.
- Un producto con temperatura obligatoria requiere límites configurados y observación Decimal.
- Las columnas críticas continúan almacenándose como texto decimal, nunca SQLite `REAL`.
