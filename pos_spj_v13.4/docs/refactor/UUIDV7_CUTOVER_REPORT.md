# Reporte de corte global UUIDv7

## Estado

```text
IMPLEMENTATION
```

## Alcance

* Tablas.
* PK.
* FK.
* Commands.
* DTO.
* Use Cases.
* Application Services.
* Query Services.
* Repositories.
* Eventos.
* Outbox.
* API.
* PyQt.
* Tests.
* Fixtures.
* Seeds.
* Scripts.
* Sincronización.

## Iteración 1 — Auditoría inicial

### Tests y checks ejecutados

```text
python -m compileall pos_spj_v13.4
python -m pytest pos_spj_v13.4/tests/architecture -q
rg -n --pcre2 -i <patrón> pos_spj_v13.4
```

### Resultado

* `compileall`: PASS.
* `tests/architecture`: PASS, 91 passed / 4 skipped.
* Búsqueda negativa UUIDv7: FAIL, existen violaciones abiertas.

## Inventario inicial

| Patrón | Coincidencias | Estado |
| ------ | ------------: | ------ |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | 803 | OPEN |
| `lastrowid` | 147 | OPEN |
| `legacy_id` | 14 | OPEN |
| `int(product_id)` | 33 | OPEN |
| `int(branch_id)` | 28 | OPEN |
| `int(sale_id)` | 5 | OPEN |
| `int(customer_id)` | 2 | OPEN |
| `int(reservation_id)` | 4 | OPEN |
| `CREATE TABLE` | 1212 | NEEDS_CLASSIFICATION |
| `ALTER TABLE` | 132 | NEEDS_CLASSIFICATION |
| `productos.existencia` | 31 | OPEN |
| `branch_inventory` | 229 | OPEN |

## Iteración 2 — Protección inicial e implementación mínima

### Archivos creados

* `backend/shared/ids.py` — generador canónico `new_uuid()` con UUIDv7 lowercase.
* `tests/architecture/test_uuidv7_cutover_protection.py` — pruebas de protección inicial.

### Tests agregados

* `test_new_uuid_returns_canonical_lowercase_uuidv7_string`.
* `test_new_uuid_generates_unique_values_offline`.
* `test_uuidv7_cutover_forbidden_identity_patterns_do_not_increase`.
* `test_new_uuid_fallback_returns_uuidv7_when_runtime_lacks_uuid7`.

### Resultado

* Protección UUIDv7 inicial: PASS.
* Arquitectura acumulada: PASS, 91 passed / 4 skipped.
* Violaciones restantes: 4197.

## Iteración 3 — Robustez del generador UUIDv7

### Archivos modificados

* `backend/shared/ids.py` — agrega fallback UUIDv7 local cuando el runtime no expone `uuid.uuid7`.
* `tests/architecture/test_uuidv7_cutover_protection.py` — agrega prueba del fallback.

### Resultado

* Protección UUIDv7: PASS.
* Arquitectura acumulada: PASS, 91 passed / 4 skipped.
* Violaciones restantes: 4197.

## Iteración 4 — Work queue y grafo schema inicial

### Archivos creados

* `docs/refactor/work_queue.json` — lotes ejecutables UUID-00 a UUID-19.
* `docs/refactor/UUIDV7_SCHEMA_GRAPH.json` — inventario generado por archivo de tablas, PK, FK y columnas `id`/`*_id`.
* `docs/refactor/UUIDV7_SCHEMA_GRAPH.md` — resumen legible del grafo.
* `tests/architecture/test_refactor_work_queue.py` — validación de cola ejecutable.

### Estado de lotes

* `UUID-00-INVENTORY`: DONE.
* `UUID-01-GENERATOR`: DONE.
* `UUID-02-SCHEMA_GRAPH`: IN_PROGRESS.

### Resultado

* Work queue: PASS.
* Arquitectura acumulada: PASS, 91 passed / 4 skipped.
* Violaciones restantes: 4197.

## Iteración 5 — Cierre de UUID-02-SCHEMA_GRAPH

### Archivos creados

* `docs/refactor/UUIDV7_SCHEMA_CLASSIFICATION.json`.
* `docs/refactor/UUIDV7_SCHEMA_CLASSIFICATION.md`.
* `docs/refactor/UUIDV7_MIGRATION_DESIGN.md`.

### Resultado

* `UUID-02-SCHEMA_GRAPH`: DONE.
* `UUID-03-MIGRATION_DESIGN`: IN_PROGRESS.
* Tablas clasificadas: 269.
* Arquitectura acumulada: PASS, 91 passed / 4 skipped.

## Grafo PK/FK

DONE para inventario inicial. La clasificación está en `UUIDV7_SCHEMA_CLASSIFICATION.json`; el siguiente lote debe convertirla en diseño de migración atómica.

## Tablas migradas

Pendiente. No se declara ninguna tabla como migrada hasta completar corte atómico y pruebas de integridad.

## Contratos migrados

Pendiente. No se declara ningún contrato como migrado hasta cubrir Commands, DTO, UseCases, QueryServices, Repositories, eventos, API, UI, fixtures y scripts.

## Violaciones eliminadas

0. La iteración 2 creó protección y generador canónico, pero no eliminó aún las violaciones funcionales detectadas.

## Próxima fase obligatoria

`IMPLEMENTATION`: construir migración atómica global y reemplazar usos funcionales de identidad dispersa por `backend/shared/ids.py`.

## Validaciones

```text
[ ] Backup verificado.
[ ] Migración atómica ejecutada.
[ ] Conteos pre/post coinciden.
[ ] PRAGMA foreign_key_check sin errores.
[ ] PRAGMA integrity_check = ok.
[ ] Cero PK funcionales enteras.
[ ] Cero FK funcionales enteras.
[ ] Cero AUTOINCREMENT funcional.
[ ] Cero lastrowid funcional.
[ ] Cero casts int(..._id).
[ ] Cero legacy_id.
[ ] Cero escritura dual.
[ ] Cero fallback.
[ ] Tests UUIDv7 aprobados.
```

## Resultado

```text
NOT DONE
```
