# TRF-13 — Diferencias, tolerancias y resolución

## Modelo canónico

- `TransferDifference` conserva tipo, esperado, observado, deltas Decimal, severidad, etapa responsable, evidencia, detector y estado.
- `TransferDifferencePolicy` clasifica faltantes, sobrantes y variaciones de peso usando tolerancias inyectadas desde configuración.
- Los demás tipos cerrados —producto, lote, daño, temperatura, calidad, paquete, sello, pérdida y documento— se reportan explícitamente sin texto libre.
- `TransferDifferenceResolution` registra una opción cerrada, resolutor, motivo, evidencia, `operation_id` y UUIDv7 independiente.

## Workflow

1. Detección crea una o varias diferencias sin resolverlas automáticamente.
2. Revisión cambia `DETECTED` a `PENDING_REVIEW`.
3. Resolución exige revisión previa y permiso granular de resolución o aceptación.
4. La diferencia queda `RESOLVED`, pero la transferencia no se cierra automáticamente.

## Protecciones

- `float` está prohibido en valores y tolerancias.
- Evidencias se conservan como referencias inmutables.
- Una diferencia crítica no puede ser resuelta por el mismo usuario que la detectó.
- Cada mutación valida `operation_id`, pertenencia a la transferencia y permisos backend.
- Los eventos canónicos son `TRANSFER_DIFFERENCE_DETECTED` y `TRANSFER_DIFFERENCE_RESOLVED`.
