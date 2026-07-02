# CIERRE_GLOBAL — Reporte final del pipeline de refactor UUIDv7

**Módulo #34 · Estado: DONE · Actualizado tras el corte born-clean total (Plan B)**

Este documento refleja el estado REAL del schema activo después de completar el
Plan B: **cero PK enteras funcionales**. La versión anterior de este reporte
describía "dos estrategias coexistentes" (born-clean de esquema + cutover en
runtime); ese estado híbrido fue eliminado — la única estrategia vigente es
**schema UUIDv7 nativo → DB limpia → runtime UUID**.

---

## 1. Estado final (medido por `tools/born_clean_audit.py`)

| Métrica | Antes (FASE 0) | Ahora |
|---|---|---|
| Tablas totales (cadena completa) | 260 | 272 |
| PK entera funcional (`find_integer_pks`) | **139** | **0** |
| `id TEXT PRIMARY KEY` born-clean | 99 | 238 |
| PK natural/compuesta | 22 | 34 |
| AUTOINCREMENT | 126 | 0 |
| Tablas con FK funcional INTEGER | 142 | 0 |
| Tablas con `DEFAULT 1` en FK funcional | 40 | 0 |

`find_integer_pks(conn) == {}` con el bootstrap normal (`m000_base_schema.up` +
`migrations.engine.up`), tanto en base sola como en la cadena completa.
`PRAGMA foreign_key_check` vacío. Detalle inicial y atribución por archivo:
`docs/refactor/born_clean_uuidv7_schema_audit.md`.

## 2. Guardrails — CERO tolerancia (sin techos)

Los techos de deuda (`INTEGER_PK_TABLE_CEILING` / `SERVICES_WITH_DDL_CEILING` /
`LASTROWID_FILE_CEILING`) fueron **reemplazados por criterio cero** en
`tests/architecture/test_clean_birth_guardrails.py` (41/41 verdes):

- `test_fresh_base_schema_has_no_integer_primary_keys`
- `test_full_migration_chain_has_no_integer_primary_keys`
- `test_active_schema_has_no_autoincrement`
- `test_active_schema_has_no_functional_integer_fks`
- `test_active_schema_has_no_default_one_on_functional_fks`
- `test_domain_code_has_no_lastrowid_identity`
- `test_domain_code_has_no_integer_casts_for_entity_ids`
- `test_services_repositories_ui_do_not_create_schema`

## 3. `uuid_cutover` — herramienta excepcional, NO flujo de desarrollo

`backend/infrastructure/db/uuid_cutover.py` y la migración 200 quedan como
herramienta de **rescate para conservación de datos en producción** únicamente.
En desarrollo, una BD contaminada no se repara: se elimina y se recrea
(`docs/runbooks/dev_db_reset.md`). `assert_uuid_identity` sigue bloqueando el
arranque contra BDs no born-clean, con mensaje que dirige al reset (no a la 200);
`SPEC_IS_COMPLETE=False` mantiene la 200 gated.

## 4. Identidad de instalación

Seeds sin `id=1`: la sucursal matriz y la caja principal usan centinelas UUID
constantes documentados (`backend.shared.ids.INSTALL_BRANCH_UUID` /
`INSTALL_CASHBOX_UUID`); el admin acuña `new_uuid()`.

## 5. Trabajo de código completado en el corte

- 16 tablas creadas por servicios en runtime movidas born-clean a `m000`
  (`_create_runtime_service_tables`); 41 archivos de dominio quedaron sin DDL.
- 19 sitios `lastrowid` convertidos a `new_uuid()` explícito (15 archivos).
- 60 casts `int()` sobre identidades eliminados (33 archivos).
- Migración 099 (archivo legacy_*) → no-op documentado; tabla typo
  `configuracioneses` eliminada (defaults redirigidos a `configuraciones`).

## 6. Riesgo residual conocido

INSERTs antiguos que omiten `id` en tablas `TEXT PRIMARY KEY` insertan NULL
silencioso (SQLite no impone NOT NULL en PK TEXT declarada sin NOT NULL).
Mitigación en curso: writers canónicos ya acuñan `new_uuid()`; siguiente paso
sugerido: endurecer `id TEXT PRIMARY KEY NOT NULL` por tabla al tocar cada
módulo, o test de humo que inserte por cada writer y verifique id no-NULL.

*Actualizado como parte del cierre Plan B born-clean.*
