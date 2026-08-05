# CASH-4 — Repositorios y UnitOfWork de Caja

Fecha: 2026-08-03  
Estado: `IMPLEMENTED`, condicionado al schema born-clean de CASH-3.

## Frontera transaccional

`CashRegisterUnitOfWork` es el único propietario de `commit()` y `rollback()` para:

1. `cash_shifts` — turno;
2. `cash_ledger_entries` — movimiento;
3. `cash_counts` — conteo ciego;
4. `cash_cuts` — Corte X/Z;
5. `cash_differences` — diferencia;
6. `cash_domain_events` — evento persistido;
7. `cash_outbox` — mensaje pendiente de publicación.

Los repositorios comparten exactamente la misma conexión y no confirman, revierten ni modifican schema. Una excepción en cualquier escritura revierte toda la operación.

## Decisiones

- Los valores Decimal se persisten como texto exacto; nunca se convierten a `float`.
- Denominaciones y payloads se serializan como JSON determinista.
- `operation_id` es la clave de idempotencia funcional; `event_id`, `entity_id` y el ID del outbox son identidades independientes.
- El evento de dominio y su outbox se insertan antes del commit en la misma transacción.
- El envío a EventBus, WhatsApp u otros consumidores ocurre únicamente después del commit y no pertenece al repositorio.
- No se reutilizan `repositories/caja.py`, `movimientos_caja` ni las tablas legacy.

## Validación de atomicidad

`tests/integration/cash_register/test_cash_register_unit_of_work.py` usa SQLite aislado y prueba:

- commit conjunto de las siete áreas;
- rollback conjunto ante una excepción después de insertar evento/outbox;
- rollback conjunto ante duplicación de `operation_id`;
- ausencia de commits dentro de repositorios.

`tests/architecture/test_cash_register_unit_of_work_boundary.py` impide:

- `commit()` o `rollback()` dentro de repositorios;
- `CREATE TABLE`, `ALTER TABLE` o `DROP TABLE` fuera de migraciones;
- omitir una de las siete colecciones del UnitOfWork.

## Dependencia pendiente

CASH-3 no ha sido ejecutado. Por ello, estos repositorios todavía no deben conectarse al bootstrap productivo. CASH-3 debe crear las tablas y constraints exactos usados aquí, incluyendo como mínimo:

```text
UNIQUE(operation_id)
UNIQUE(z_cut_id)
UNIQUE(shift_id) WHERE cut_type = 'Z' AND is_final = 1
FKs de turno, conteo, corte y diferencia
CHECKs de estados, tipos y direcciones
```

Después de CASH-3 deberá repetirse esta suite usando el bootstrap real, eliminando el schema fixture del test de integración.
