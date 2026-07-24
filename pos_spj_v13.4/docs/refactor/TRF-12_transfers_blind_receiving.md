# TRF-12 — Recepción ciega

## Flujo canónico

1. `StartBlindReceiptUseCase` valida que el documento exija recepción ciega y asigna un receptor.
2. `CaptureBlindReceiptUseCase` almacena únicamente los valores observados; sus DTO no contienen cantidades ni pesos esperados.
3. Mientras el conteo está en `CAPTURING`, el receptor puede reemplazar su captura.
4. `ConfirmBlindReceiptUseCase` confirma mediante la misma ruta canónica de recepción de TRF-11.
5. Después de confirmar, el conteo queda inmutable y recién entonces se devuelve la comparación esperado contra observado.

## Protecciones

- Todas las etapas revalidan `TRANSFERS_BLIND_RECEIVE` y el alcance del nodo destino.
- Solo el receptor asignado puede capturar o confirmar el conteo.
- La confirmación también exige el permiso granular total o parcial aplicable.
- El esperado se calcula en aplicación desde el saldo del embarque y nunca se incluye en DTO de inicio o captura.
- `operation_id` protege inicio, captura y confirmación contra repetición.
- Cantidades y pesos son `Decimal`; se rechazan valores `float`.
- Las tablas canónicas separan cabecera y líneas observadas con UUID y estados cerrados.
