# CASH-14 — Corte Z

El Corte Z es el único documento final del turno. Requiere estado `CLOSING`, un conteo ciego confirmado no utilizado y todos los safe drops recibidos por Tesorería. Antes de escribir valida pendientes y reconstruye el esperado exclusivamente desde el ledger físico.

En una sola transacción se crea el snapshot consolidado, el Corte Z final, la diferencia `DETECTED` cuando contado y esperado no coinciden, el cierre del turno, la auditoría, el evento `CASH_Z_CUT_GENERATED` y su outbox. Cualquier fallo revierte el conjunto completo. El índice final por turno impide dos Cortes Z incluso bajo concurrencia.

La impresión y notificación son efectos posteriores al commit, separados e idempotentes mediante sus propios `operation_id`. Usan puertos inyectados y publican confirmaciones auditables; de este modo una impresora o canal caído nunca reabre ni deja parcialmente cerrado el turno.
