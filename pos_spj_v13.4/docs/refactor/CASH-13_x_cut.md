# CASH-13 — Corte X

El Corte X es un documento operativo informativo, no final. Al generarse reconstruye el ledger del turno y persiste un snapshot inmutable con entradas, salidas, saldo esperado, cantidad de movimientos y desglose por tipo. Tiene UUIDv7 como identidad y un número documental visible independiente.

`CASH_X_CUT_GENERATE` permite emitirlo y `CASH_X_CUT_VIEW` consultar sus metadatos. Los montos y el snapshot sólo son visibles con `CASH_VIEW_SENSITIVE_AMOUNTS`; sin ese permiso el DTO los devuelve redactados. Generar un Corte X nunca cambia el estado del turno ni sustituye el conteo ciego o el Corte Z.

La impresión usa `XCutPrintGateway`, requiere permiso de impresión —o reimpresión—, permiso de vista y acceso a montos sensibles. Un `operation_id` evita impresiones duplicadas por reintento. Generación e impresión quedan auditadas y emiten evento/outbox; un fallo del gateway no registra falsamente una impresión exitosa.
