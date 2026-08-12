# LOSS-23 — Eliminación de legacy

Fecha de corte: 2026-08-08.

## Inventario

Las pérdidas físicas se postean únicamente desde `LossInventoryIntegrationService`
al ledger canónico. El tipo de movimiento se deriva de la clasificación del caso:
`WASTE`, `SHRINKAGE` o `EXPIRY_DISPOSAL`. Se retiraron los productores paralelos
de `inventory_waste_event` y su repositorio dentro del UoW de Inventario.

Los ajustes legítimos de conteo continúan en `inventory_adjustment`; ya no existe
la tabla genérica `ajustes_inventario` ni se usa `ADJUSTMENT_IN/OUT` para simular
una merma.

## Clasificación

`LossClassificationCode`, `loss_classifications` y `loss_reasons` son la única
fuente de clasificación. Se eliminó `WasteType` y su segunda matriz de mapeo.

## Migración funcional

El proyecto está en desarrollo y sigue la política born-clean: no se conserva ni
se copia información de `mermas`, `ajustes_inventario` o
`inventory_waste_event`. Una base contaminada debe respaldarse si se requiere y
recrearse desde el esquema fuente. No existe lectura dual ni fallback.

## Módulos e imports eliminados

- UI `modulos/merma.py`.
- Command, application service y use case `waste` anteriores.
- Repositorio `mermas` y adaptador `CanonicalWasteInventoryService`.
- Use case y repositorio `inventory_waste_event`.
- Migraciones 097 y 129 que recreaban esquemas retirados.
- Exports e imports transitivos de los paquetes de aplicación e inventario.

## Tablas consolidadas

| Retirada | Fuente canónica |
|---|---|
| `mermas` | `loss_cases` + `loss_lines` |
| `inventory_waste_event` | caso de pérdida + `inventory_ledger` |
| `ajustes_inventario` | `inventory_adjustment` para ajustes reales |

BI, gráficos y reportes leen valores persistidos en `loss_cases`/`loss_lines`;
ya no recalculan la pérdida desde cantidad por costo en una tabla paralela.

## Allowlist

La allowlist de consumidores legacy de Mermas queda vacía. El guardrail
`test_loss_legacy_cutover.py` escanea el runtime y bloquea la reintroducción de
módulos, imports o tablas retiradas.

## Validación

- Arquitectura: ausencia de módulos/imports legacy y allowlist vacía.
- Born-clean: únicamente `loss_cases`, `loss_lines` y tablas relacionadas.
- Integración: registro general e integración con ledger mantienen UUIDv7,
  idempotencia, posteo y reverso.
- Reportes: consumen clasificación y valuación canónicas.

## Riesgo y operación

No ejecutar una migración de rescate. Para desarrollo, respaldar y regenerar la
base local; validar `PRAGMA foreign_key_check` y las suites de Losses/Inventario
antes de distribuir un nuevo ejecutable.
