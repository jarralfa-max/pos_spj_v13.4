# CASH-8 — Ledger

El ledger canónico registra entradas y salidas como asientos inmutables ligados a un turno y una sucursal. Los movimientos manuales admitidos son ingreso, retiro y retiro a bóveda; cada uno exige concepto, permiso granular, límites monetarios y un `operation_id` UUIDv7 único.

Un reverso nunca modifica ni elimina el asiento original: crea un asiento `REVERSAL` por el mismo importe, en dirección opuesta y con `reversal_of_id`. Exige motivo, autorizador distinto y autorización en la misma sucursal. Sólo puede existir un reverso por asiento.

La proyección recorre los asientos ordenados y reconstruye entradas, salidas y saldo exclusivamente con `Decimal`. La escritura atómica incluye movimiento, auditoría, evento de dominio y outbox mediante `CashRegisterUnitOfWork`. La UI sólo presenta el read model y emite solicitudes de comando.
