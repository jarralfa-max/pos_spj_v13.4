# LOSS-3 — Esquema limpio de Losses

Estado: `IMPLEMENTED_WITH_PYTEST_ENVIRONMENT_BLOCKER` (2026-08-03).

## Implementado

- Migración versionada `174_losses_bounded_context_schema.py`.
- Registro en `migrations/engine.py`.
- Inclusión en el bootstrap aislado de `m000_base_schema.py`, reutilizando una sola fuente DDL.
- Identidades y FK funcionales `TEXT` con guardas UUIDv7.
- Valores Decimal persistidos como `TEXT`, nunca `REAL`.
- Constraints de clasificación, origen, estado, workflow persistente, valores y segregación.
- Índices por scope/estado, clasificación, causa, fecha, producto/lote, fuentes, auditoría y despacho.
- `loss_outbox` con `event_id` único, IDs independientes, estados, reintentos y despacho.
- `loss_processed_operations` con `operation_id` como PK idempotente.
- Seeds idempotentes de clasificaciones canónicas, con código inglés y nombre visible español.

## Tablas

```text
loss_classifications
loss_reasons
loss_cases
loss_lines
loss_evidence
loss_approvals
loss_dispositions
loss_recoveries
yield_variances
loss_investigations
loss_root_causes
loss_corrective_actions
loss_corrective_action_tasks
loss_audit_log
loss_outbox
loss_processed_operations
```

## Estrategia born-clean

No existe backfill desde `mermas`, lectura dual, escritura dual, `legacy_id` ni tabla de compatibilidad. La migración crea exclusivamente el nuevo bounded context. Las rutas antiguas permanecen sin conexión al schema nuevo hasta que los casos de uso posteriores estén protegidos.

## Tests

- `tests/integration/losses/test_losses_schema_born_clean.py`: cobertura pytest completa de tablas, tipos, seeds, UUIDv7, constraints, FK, outbox e idempotencia.
- `tests/integration/losses/test_losses_schema_smoke_unittest.py`: validación stdlib ejecutable sin pytest.
- `tests/architecture/test_losses_schema_lives_in_migrations.py`: DDL solo en migraciones y registro de versión.

## Resultado

```text
compileall: PASSED
unittest LOSS-3: 4 PASSED
pytest LOSS-1/2/3: BLOCKED (pytest no está instalado)
PRAGMA foreign_key_check: PASSED
migración repetida: PASSED
m000 bootstrap: PASSED
operación duplicada: REJECTED
event_id duplicado: REJECTED
FK huérfana: REJECTED
```

## Siguiente gate

Antes de LOSS-4 deben ejecutarse las suites pytest pendientes. LOSS-4 podrá crear sidebar/rutas y modelos de lectura, pero no debe conectar una escritura operativa al schema nuevo hasta LOSS-5/LOSS-6.
