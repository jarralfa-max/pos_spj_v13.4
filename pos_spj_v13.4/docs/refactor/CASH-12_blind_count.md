# CASH-12 — Conteo ciego

Cada turno admite una sola sesión `OPEN` de conteo. Puede iniciarse con el turno abierto o en cierre preliminar y transporta UUIDv7 para sesión, operación, denominaciones y eventos.

La captura utiliza exclusivamente denominaciones activas y vigentes. Cada cantidad es un entero no negativo, el subtotal se calcula con `Decimal` y los reintentos se deduplican mediante `cash_processed_operations`. El esperado no se persiste en la sesión, no se incluye en eventos de captura y no aparece en el DTO normal.

Confirmar cambia la sesión a `CONFIRMED` de forma irreversible y bloquea nuevas capturas. Sólo después de confirmar, una consulta explícita con `CASH_BLIND_COUNT_REVEAL_EXPECTED` reconstruye el efectivo desde el ledger y devuelve esperado y diferencia. La UI permanece delgada, muestra “Esperado: oculto” por defecto y emite comandos a su controlador.
