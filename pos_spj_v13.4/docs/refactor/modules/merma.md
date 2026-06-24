# Módulo MERMA (waste)

## Estado

```text
AUDIT — F0 (baseline). Módulo llega mayormente refactorizado.
```

## Alcance canónico

```text
modulos/merma.py                                            # UI PyQt (sin SQL/commit)
backend/application/services/waste_application_service.py   # application service
backend/application/use_cases/register_waste_use_case.py    # use case canónico
backend/application/commands/waste_commands.py              # Command(s)
backend/application/queries/waste_query_service.py          # lecturas
backend/infrastructure/db/repositories/waste_repository.py  # SQL boundary
```

## Hallazgos F0

MERMA llega con la mayor parte del checklist ya cumplido (auditoría previa
`docs/architecture/WASTE_MODULE_PHASE11_AUDIT.md`):

- UI sin SQL/commit/rollback, sin `lastrowid`, sin `int(..._id)`, sin `uuid4`,
  sin integraciones externas crudas (smtplib/serial/urllib/socket/subprocess).
- Identidad UUIDv7 verificada: `product_id`/`branch_id` como `str`, `new_uuid()`,
  repo no usa `lastrowid` como identidad (`test_waste_uuid_identity.py`).
- Servicios/Use Case/Command/Query canónicos presentes; ruta legacy eliminada
  (`test_waste_module_refactor.py`).

### Auditoría por fase (confirmada)

- F1 sin SQL/commit en UI ✅
- F2 identidad UUIDv7 ✅ (`branch_id` ahora `str` en todas las firmas del repo)
- F3 transacción la posee el application service vía `save_changes()/rollback_changes()` ✅
- F4 QueryService retorna DTOs tipados (`SearchResult`, `TableRow`, `KpiMetric`) ✅
- F5 fuente única / ruta legacy eliminada ✅
- F6 UI → `RegisterWasteUseCase.execute(RegisterWasteCommand)` ✅
- F7 idempotencia por `operation_exists(operation_id)` + evento `WASTE_REGISTERED` ✅
- F8 sin integraciones externas crudas en UI ✅

### Violaciones restantes (documentadas, baja prioridad)

- `waste_repository`: expone `save_changes()`/`rollback_changes()` (commit/rollback
  con nombre explícito; el application service orquesta el boundary, pero idealmente
  vía `ConnectionUnitOfWork`) → alinear en fase de transacciones/identidad.
- ~~`branch_id: str | int` en firmas del repo~~ → **RESUELTO**: todas las firmas
  (`search_products`, `list_waste_records`, `get_daily_summary`, `_branch_stock_expression`)
  ahora usan `branch_id: str`. Ratchet en `test_waste_repository_branch_id_signatures_are_str`.
  Verificado: sin casts `int(branch_id)`, el valor se pasa directo como parámetro SQL.
- `waste_query_service.get_daily_summary` usa default arbitrario `branch_id="1"`
  (regla 23) → mover a `SystemSettingsService` (pendiente).
- `save_changes()`/`rollback_changes()` → `ConnectionUnitOfWork` se cierra con el
  corte atómico de identidad global (migración 200).
- `metadata["id"]` (construcción de dict) y `currentText()` (motivo/periodo) en
  `merma.py` son valores libres, no identidad — no son violaciones.

## Tests

```text
tests/architecture/test_merma_guardrails.py          # NEW — baseline ratchet F0
tests/architecture/test_waste_module_refactor.py
tests/architecture/test_waste_uuid_identity.py
tests/architecture/test_merma_no_legacy_permissions.py
tests/integration/test_merma_module_loads.py
tests/unit/test_waste_refactor.py
tests/finance/test_financial_trace_waste_loyalty.py
```

Suite MERMA/waste: 32 passed, 9 skipped.

## Próxima acción

Cerrar residuales (`save_changes` → UnitOfWork; `branch_id: str|int` → `str`) en
el corte atómico de identidad, o avanzar a `PRODUCTOS`.
