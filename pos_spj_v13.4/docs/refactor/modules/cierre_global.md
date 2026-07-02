# CIERRE_GLOBAL — Reporte final del pipeline de refactor UUIDv7

**Módulo #34 · Estado: DONE · Iteración 1**
**Alcance elegido:** cierre de pipeline (barrido global de cumplimiento REGLA CERO,
confirmación de guardrails y reporte final). No es un flip de tablas; la deuda de
`cierre_mensual` / `cierres_caja` se deja a sus módulos dueños (CONFIGURACION / CAJA).

Este documento es el **estado honesto** del pipeline al cerrar la cola operativa
(#1–#34). Refleja el esquema real (`m000_base_schema` + cadena de 113 migraciones),
no una aspiración.

---

## 1. Resumen ejecutivo

El refactor "born-clean UUIDv7" avanzó **por dos estrategias coexistentes**:

1. **Born-clean de esquema (esta tanda, módulos ~#15–#33):** la definición en
   `m000_base_schema` se reescribió a `id TEXT PRIMARY KEY` (UUIDv7) con identidad
   única — sin columna `uuid` dual, sin surrogate entero, sin `DEFAULT 1`. Cada
   módulo dejó un guardrail en `tests/architecture/test_clean_birth_guardrails.py`.

2. **Cutover en runtime (módulos tempranos: ventas, mermas, inventario, etc.):** el
   esquema base conserva `id INTEGER PRIMARY KEY` y se añade columna `uuid` (dual)
   vía migraciones 101/102; la transformación entero→UUIDv7 la ejecuta el mecanismo
   `backend/infrastructure/db/uuid_cutover.py` en runtime, con el gate de arranque
   `assert_uuid_identity` (bloquea el arranque si la BD no fue "cortada", con runbook
   accionable y `SPJ_UUID_CUTOVER_CONFIRMED=1`).

**Conclusión:** el pipeline **no está al 100 %** a nivel de esquema. Una parte del
dominio ya nace limpia; otra parte sigue en entero y depende del cutover en runtime
o queda como deuda documentada asignada a un módulo dueño.

---

## 2. Censo de identidad (medido, no estimado)

### Esquema base (`m000_base_schema.up`)
| Métrica | Valor |
|---|---|
| Tablas totales | 185 |
| PK TEXT identidad única (born-clean) | 73 |
| PK INTEGER funcional (filtro `find_integer_pks`) | **107** (techo 129, holgura 22) |

### Cadena completa (base + 113 migraciones standalone)
| Métrica | Valor |
|---|---|
| Tablas totales | 261 |
| PK TEXT identidad única (born-clean) | 112 |
| PK INTEGER funcional (filtro guard) | **139** |
| — de ellas DUAL (`id` INTEGER + col `uuid`, cutover-ready) | 23 |
| — de ellas INTEGER puro (sin `uuid`) | 116 |

> El filtro `find_integer_pks` es amplio: incluye tablas `legacy_*` (archivo),
> auditoría/log (`audit_log`, `json_audit_log`, `logs`, `login_attempts`,
> `concurrency_events`) y claves naturales compuestas (`sync_version_history` con
> PK `(event_id, version)`), que inflan el conteo de "deuda" real de dominio.

---

## 3. Guardrails de nacimiento limpio — VERDE

`tests/architecture/test_clean_birth_guardrails.py`: **38/38 passing.**

Techos de deuda (sólo pueden bajar hacia 0; subir = regresión que falla el build):

| Techo | Valor actual | Estado |
|---|---|---|
| `INTEGER_PK_TABLE_CEILING` | 129 (medido 107 en base) | ✅ |
| `SERVICES_WITH_DDL_CEILING` | 20 | ✅ |
| `LASTROWID_FILE_CEILING` | 31 | ✅ |

Guardrails por subsistema nacidos en esta tanda (no exhaustivo): alertas, tarjetas
de fidelidad, clientes, proveedores, compras, recepción, pedidos, tickets/print_job,
hardware, notificaciones, WhatsApp, contabilidad core, tesorería, gastos, CxP/CxC,
plan de cuentas, deuda diferida, RRHH, reportes/BI, API REST, **sincronización**,
**instalador**, **actualizador**.

---

## 4. Mecanismo puente: `uuid_cutover` (runtime)

- `find_integer_pks(conn)` — detecta tablas de dominio con PK entero (excluye infra
  de migración como `schema_migrations`).
- `assert_uuid_identity(conn)` — gate de arranque: si hay PKs enteros funcionales y
  no está `SPJ_UUID_CUTOVER_CONFIRMED=1`, levanta `IntegerIdentityError` con runbook.
- `UuidCutover(conn, [TableSpec(...)]).run()` — transforma entero→UUIDv7 respetando
  FKs, de forma directa/atómica (sin escritura dual persistente).

Este es el camino previsto para las 139 tablas enteras/duales que aún no nacen
limpias en el esquema base.

---

## 5. Deuda diferida con dueño asignado (fuera de CIERRE_GLOBAL)

| Deuda | Dueño | Referencia |
|---|---|---|
| Centinela matriz `sucursales`/`cajas`/`usuarios` `id='1'`; `sucursal_id INTEGER DEFAULT 1`; int branch ids | **CONFIGURACION-02-IDENTITY** | `configuracion_scope.json` CFG-SCOPE-002; docstring `_seed_initial_data` |
| `cierre_mensual` (dual `id`+`uuid`+`sucursal_uuid`, `DEFAULT 1`) — writer `config_repository.py`, mig 096, `ClosingPeriodService` | **CONFIGURACION** | census §2; scope doc |
| `cierres_caja` (dual `id`+`uuid`, `DEFAULT 1`) — writers `caja_application_service`, `cierre_caja_service` | **CAJA / CONFIGURACION** | census §2 |
| SQL directo en PyQt de configuración, defaults hardcodeados, matriz de permisos | **CONFIGURACION** (batches 04/02/08) | `test_settings_*`, `test_configuracion_*` |

---

## 6. Estado de la suite (honesto)

- **Born-clean guardrails:** 38/38 verde.
- **`tests/architecture/` completo:** 40 fallos **pre-existentes** (BASE=NOW en
  stash-diff), todos del módulo **CONFIGURACION #0 (PENDING)**: `test_settings_*`,
  `test_configuracion_*`, `test_refactor_orchestrator`, `test_refactor_work_queue`,
  `test_uuid_cutover_migration_gated`, selector de sucursal, widgets estándar.
- **Full suite:** ~628 fallos de baseline, dominados por issues de entorno
  (`ModuleNotFoundError: PIL`, colecciones rotas por `FileNotFoundError`) y ruido de
  logs de `sales_service` (handlers de venta no registrados en entornos aislados).
  Cada módulo de esta tanda se validó con stash-diff full-suite → **cero fallos
  nuevos** vs su baseline.

---

## 7. Cola operativa

Todos los módulos #1–#34 en **DONE**. Único pendiente: **CONFIGURACION #0**, que
absorbe la deuda diferida de §5 (centinela matriz, dual-identity de
`sucursales`/`usuarios`/`cajas`, cierre mensual/caja, y el hardening del módulo de
configuración). Cerrar CONFIGURACION #0 es la condición para intentar bajar
`INTEGER_PK_TABLE_CEILING` hacia 0 y, eventualmente, ejecutar el cutover global.

---

## 8. Definición de "terminado" para el pipeline (pendiente tras CONFIGURACION)

1. `INTEGER_PK_TABLE_CEILING == 0` (todo dominio nace TEXT UUIDv7 en base) **o**
   cutover global confirmado y verificado.
2. `SERVICES_WITH_DDL_CEILING == 0` y `LASTROWID_FILE_CEILING == 0`.
3. Cero `int(..._id)` sobre identidades en código no-test.
4. Suite de arquitectura completa en verde (incluida CONFIGURACION).

*Reporte generado en el cierre de la cola operativa; refleja el esquema real a la
fecha del commit de CIERRE_GLOBAL.*
