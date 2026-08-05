# LOSS-5 — Registro general

Estado: implementado el 2026-08-03.

El registro general crea un `LossCase` con una o más `LossLine`, selección de
producto/lote, cantidad y peso exactos con `Decimal`, clasificación y causa de
catálogo, y evidencia con checksum SHA-256. El caso puede guardarse como
`DRAFT` o enviarse como `SUBMITTED`.

La escritura de caso, líneas, metadatos de evidencia, outbox y operación
procesada ocurre dentro del mismo savepoint e incluye replay idempotente por
`operation_id`. Esta fase no crea movimientos ni modifica existencias; ese
límite pertenece a LOSS-6.

El formulario canónico usa presenter y componentes desktop compartidos. Se
eliminó `_LegacyLossRegistrationBridge` y el composition root ya no importa
`modulos.merma`.

Verificación ejecutada: compilación de los paquetes Losses, 4 pruebas de
caracterización invocadas directamente y 5 pruebas `unittest` de esquema,
transacción, outbox e idempotencia. `pytest` no está instalado en el entorno.
