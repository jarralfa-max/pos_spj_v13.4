# LOYALTY_LEDGER_SOURCE_OF_TRUTH

Fuente canónica: `loyalty_ledger`.

- `clientes.puntos` y `tarjetas_fidelidad.puntos_actuales` se consideran snapshots recalculables.
- Saldo real = `SUM(loyalty_ledger.puntos)` por cliente.
- Idempotencia de movimientos protegida por `UNIQUE(cliente_id,tipo,referencia)`.
- Migración de datos legacy desde `growth_ledger` a `loyalty_ledger` en `092_loyalty_ledger_canonicalization.py`.
