# TRF-23 — Validación final de Transferencias

## Estado

`MIGRATED`

La ruta canónica cubre dominio, aplicación, infraestructura, escritorio,
integraciones, sincronización offline y bootstrap limpio. No existe allowlist ni
ruta de compatibilidad de Transferencias.

## Matriz ejecutable

| Validación | Evidencia automatizada |
|---|---|
| Dominio | `tests/unit/test_transfers_domain.py` y políticas especializadas |
| Aplicación | `tests/unit/test_transfers_*_use_cases.py` |
| Integración | `tests/integration/test_transfers_schema.py` |
| E2E | `tests/e2e/test_transfers_clean_workspace.py` |
| Seguridad | `tests/unit/test_transfers_security.py` |
| UI | `tests/unit/test_transfers_ui_workspace.py` |
| Arquitectura | `tests/architecture/test_transfers_*.py` |
| Bootstrap limpio | `tests/integration/test_transfers_bootstrap_migration.py` |
| UUIDv7 y Decimal | `tests/architecture/test_transfers_final_audit.py` |
| SQL en UI y tablas duplicadas | `tests/architecture/test_transfers_final_audit.py` |
| Inventario, eventos y permisos | tests de integraciones, eventos y permisos |
| Offline | `tests/unit/test_transfers_offline_sync.py` |
| Legacy | `test_no_legacy_transfer_imports.py` y allowlist vacía |

## Resultado

- Identidades funcionales almacenadas como `TEXT` y generadas con `new_uuid()`.
- Cantidades, pesos, temperatura y métricas variables almacenadas como Decimal
  textual; no se admite `REAL`, `FLOAT` ni `DOUBLE`.
- El frontend no contiene SQL ni control transaccional.
- `stock_transfers` y sus tablas subordinadas son el único modelo persistente.
- Inventario se consume mediante gateway; no existe fallback a `InventoryEngine`.
- Eventos y permisos pertenecen a catálogos canónicos cerrados.
- Operaciones offline conservan secuencia local, política de conflicto e
  idempotencia.
- La allowlist de legacy permanece vacía.
