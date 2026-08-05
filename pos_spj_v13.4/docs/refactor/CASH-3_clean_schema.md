# CASH-3 — Esquema limpio de Caja

Fecha: 2026-08-03  
Estado: `IMPLEMENTED`.

## Resultado

La migración `175_cash_register_bounded_context_schema.py` crea desde cero:

- `cash_registers`, `cash_drawers`, `pos_terminals`;
- `cash_shifts`, `cash_ledger_entries`;
- `cash_counts`, `cash_count_denominations`;
- `cash_cuts`, `cash_differences`, `cash_handovers`;
- `cash_authorization_grants`, `cash_audit_log`;
- `cash_domain_events`, `cash_outbox`, `cash_processed_operations`.

## Identidad y dinero

- PK/FK funcionales son `TEXT` con check UUIDv7.
- `event_id`, `operation_id`, `entity_id` y outbox `id` son distintos.
- No existen PK enteras, `AUTOINCREMENT`, `lastrowid` o `legacy_id`.
- Todos los montos son `TEXT` decimal con checks numéricos; no hay columnas monetarias `REAL`.

## Constraints e idempotencia

- Estados, tipos de movimiento y direcciones usan catálogos cerrados.
- FKs enlazan turno, ledger, conteo, denominaciones, cortes, diferencias, entregas y outbox.
- Un solo turno activo por caja, cajón, terminal y cajero mediante índices parciales.
- Un solo Corte Z final por turno.
- `operation_id` es único en mutaciones y outbox.
- `event_id` es único y el outbox referencia el evento persistido.
- Conteo confirmado exige timestamp; Corte Z exige conteo y monto contado.
- Reversos deben referenciar un movimiento anterior.

## Bootstrap

- Registrada como migración incremental 175 en `migrations/engine.py`.
- Invocada desde `m000_base_schema.py` para que una instalación nueva nazca con el schema canónico.
- Es idempotente y termina con `PRAGMA foreign_key_check`.

## Sin migrar deuda

La migración no contiene `SELECT`, `INSERT INTO`, `ALTER TABLE`, renombres ni referencias a `turnos_caja`, `movimientos_caja`, `cierres_caja`, `turno_actual` o `caja_operations`. No rescata datos ni crea lectura/escritura dual.

## Validación

- `test_cash_register_schema_born_clean.py`: tablas, UUID, Decimal TEXT, constraints, índices, repetibilidad y FK check.
- `test_cash_register_unit_of_work.py`: CASH-4 opera sobre la migración real, sin DDL duplicado en el fixture.
- `test_cash_register_schema_lives_in_migrations.py`: registro de bootstrap y ausencia de deuda legacy.
