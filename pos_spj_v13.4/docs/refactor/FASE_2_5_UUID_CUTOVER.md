# FASE 2.5 — Corte UUID global, total y atómico (Diseño)

> Estado: **DISEÑO / propuesta revisable.** No ejecutar la migración destructiva
> sin aprobación. Este documento define el plan; la ejecución es un PR aparte.

Cumple REGLA CERO del skill `spj-refactor`: UUIDv7 como **única** identidad de
dominio. Cierra `legacy_id`, `INTEGER PRIMARY KEY AUTOINCREMENT`, `lastrowid` y
los casts `int(..._id)`, y alinea los tests de identidad hoy en rojo.

---

## 1. Inventario del estado actual (medido)

| Patrón prohibido | Ocurrencias | Baseline test cutover | Estado |
|---|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | **398** | 392 | 🔴 +6 sobre baseline (tablas nuevas de sesión previa; convertir a `TEXT` en Fase B) |
| `lastrowid` (identidad de inserción) | **122** | 122 | 🟡 en baseline |
| `legacy_id` | **0** | 2 | ✅ cerrado en PR-A0 (eran labels de log + texto de tooling) |
| `int(product_id)` | 27 | 27 | 🟡 |
| `int(branch_id)` | 25 | 25 | 🟡 |
| `int(sale_id)` / `customer_id` / `reservation_id` | 2 / 1 / 3 | igual | 🟡 |

**Esquema:** 191 `CREATE TABLE`; **81 archivos** con PK entera autoincremental
(migrations 55, core 26, repositories 3, modulos 5, integrations 1, sync 2).

**FKs funcionales** (frecuencia en migraciones, define el grafo a reescribir):

| FK | refs | FK | refs |
|---|---|---|---|
| `sucursal_id`/`branch_id` | 424 | `batch_id` | 66 |
| `producto_id`/`product_id` | 236 | `venta_id`/`sale_id` | 46 |
| `cliente_id`/`customer_id` | 72 | `usuario_id` | 23 |
| `proveedor_id` | 18 | `empleado_id` | 11 |
| `receta_id`/`recipe_id` | 13 | `reservation_id` | 5 |

**Ya hecho (runtime UUID-tolerante):** módulos **MERMA** y **PRODUCTOS** tratan
identidad como `str` end-to-end (sin `int(_id)`, sin SQL/commit en UI). El
generador único `backend/shared/ids.py::new_uuid()` (UUIDv7) existe y pasa sus
tests. Esto baja el riesgo: el corte de esquema no parte de cero.

---

## 2. Decisión de estrategia

REGLA CERO prohíbe escritura/lectura dual, `legacy_id`, tablas paralelas y
fallback int→uuid. Por tanto **NO** se permite un strangler con doble id. El
corte es **un solo evento atómico** sobre la base SQLite:

```
App cerrada → backup → transacción exclusiva → reescritura total → validación → commit
```

Pero el riesgo se controla en **dos fases temporales** (no dos esquemas):

- **Fase A — Runtime UUID-tolerante (no destructiva, incremental).**
  Hacer que TODO el runtime acepte `str` como identidad (como ya hicimos en
  MERMA/PRODUCTOS), eliminar `int(_id)`, y que cada repo **genere** el UUID antes
  del INSERT en vez de leer `lastrowid`. Sin tocar el esquema todavía: SQLite con
  columnas `INTEGER` acepta texto por afinidad durante la transición de código,
  pero el objetivo es que el código nunca dependa del tipo entero.
- **Fase B — Corte de esquema atómico (destructiva, único PR/migración).**
  Migración `200_uuid_cutover` que convierte PK/FK a `TEXT` y reescribe todos los
  datos con mapas `old_id → uuid`. Tras el corte, el esquema solo admite UUID.

Fase A se puede mergear por módulos sin downtime. Fase B se ejecuta una vez,
offline, cuando A está completa y verde.

---

## 3. Diseño técnico

### 3.1 Generador (existe)
`backend/shared/ids.py`:
```python
def new_uuid() -> str:  # UUIDv7 canónico lowercase
```
Regla: ningún widget, repo o motor genera identidad por otra vía. Prohibido
`uuid4` para identidad de dominio, `MAX(id)+1`, folio/SKU/código como PK.

### 3.2 Esquema objetivo
- SQLite: `id TEXT PRIMARY KEY`. PostgreSQL futuro: `id UUID PRIMARY KEY`.
- Toda FK funcional: `TEXT NOT NULL` (o `TEXT` si nullable), nunca `INTEGER`.
- Folios, SKU, códigos de barras, tickets: columnas normales, **no** PK.

### 3.3 Migración atómica `200_uuid_cutover` (algoritmo)

Sigue los 14 pasos de REGLA CERO. Pseudocódigo del núcleo:

```text
1.  Verificar app cerrada + lock exclusivo (PRAGMA locking_mode=EXCLUSIVE).
2.  Backup completo del archivo .db (copia + checksum).  -> AppBackupService
3.  BEGIN EXCLUSIVE TRANSACTION.
4.  PRAGMA foreign_keys = OFF.
5.  Construir orden topológico de tablas por dependencia FK (padres primero).
6.  Para cada tabla T:
      - crear T_new con id TEXT PRIMARY KEY y FKs TEXT (mismo resto de columnas).
7.  Para cada tabla T en orden topológico:
      - para cada fila: uuid = new_uuid(); registrar map[T][old_id] = uuid.
      - INSERT en T_new reescribiendo PK (uuid) y cada FK vía map[parent][old_fk].
        (FK sin match -> NULL si nullable, si no -> abortar y reportar huérfano.)
8.  Validar: COUNT(T_new) == COUNT(T) para toda T.
9.  DROP TABLE T;  ALTER TABLE T_new RENAME TO T.
10. Recrear índices/uniques/triggers con definiciones nuevas.
11. PRAGMA foreign_keys = ON;  PRAGMA foreign_key_check  (debe salir vacío).
12. COMMIT.
13. Descartar mapas temporales.
14. Marcar schema_migrations '200' y arrancar solo con esquema UUID.
```

Fallo en cualquier paso → ROLLBACK + restaurar backup + bloquear arranque normal
+ log estructurado. Prohibido dejar migración parcial.

**Mapas `old_id → uuid`:** en memoria (dict por tabla) o tabla temporal
`_uuid_map(tabla, old_id, uuid)` si la base no cabe en RAM. Se eliminan al final.

**Orden topológico:** derivado del grafo FK. Raíces típicas primero
(`sucursales`, `usuarios`, `categorias`, `productos`, `clientes`,
`proveedores`), luego dependientes (`ventas`→`detalles_venta`,
`compras`→`detalles_compra`, `batches`→`batch_movements`, etc.). Ciclos: romper
con segunda pasada que actualiza FKs autorreferenciales tras el INSERT.

### 3.4 `lastrowid` → identidad generada (122 sitios)
Patrón actual (prohibido):
```python
cur = conn.execute("INSERT INTO t(...) VALUES(...)"); new_id = cur.lastrowid
```
Patrón objetivo:
```python
uuid = new_uuid()
conn.execute("INSERT INTO t(id, ...) VALUES(?, ...)", (uuid, ...)); return uuid
```
Hotspots: `enterprise/finance_service.py` (13), `finance/erp_financial_service.py`
(8), `finance/treasury_service.py` (6), `rrhh/.../sqlite_repositories.py` (6),
`integrations/pos_adapter.py` (5), varios `repositories/*` (2 c/u). Cada uno con
test de protección antes de tocar (regla 4).

### 3.5 Casts `int(..._id)` (58 sitios)
Eliminar por módulo igual que en PRODUCTOS/MERMA: pasar `str` directo (el SQL liga
como parámetro; SQLite compara por afinidad durante Fase A y exacto tras Fase B).
Concentrados en módulos aún no auditados (ventas, delivery, caja, finanzas, etc.).

### 3.6 `legacy_id` (4 → 0)
No es identidad dual real:
- `core/session_context.py` (2): labels de log `legacy_id=%s` → renombrar a
  `sucursal_legacy=%s` o quitar (cosmético, cierra el patrón).
- `tools/refactor_control/bootstrap_refactor_state.py` (2): texto de checklist;
  reescribir sin la cadena literal.

### 3.7 Operación, evento y comando
`operation_id`, `event_id`, `entity_id` son UUID **distintos** (no reutilizar
entre sí). Hoy varios `operation_id` van prefijados (`product-<uuid>`); decidir:
mantener prefijo legible (no es PK) o UUID puro. Recomendado: UUID puro en
`entity_id`/`event_id`, prefijo permitido solo en `operation_id` de idempotencia.

---

## 4. Cambios de runtime por capa

| Capa | Cambio | Sitios |
|---|---|---|
| `migrations/` | nuevas tablas con `id TEXT`; migración 200 | 55 archivos |
| `repositories/`, `infrastructure/` | generar uuid antes de INSERT; quitar `lastrowid` | 122 |
| `application/services` | identidad `str`; UoW ya en marcha | — |
| `modulos/` (UI) | quitar `int(_id)`; ids como `str` | 5 módulos restantes |
| `core/` engines (recipe/production/inventory) | firmas `branch_id: int` → `str` | 26 archivos |

Orden recomendado de Fase A por módulo (mismo patrón ya probado): **caja,
transferencias, delivery, ventas, compras, finanzas, rrhh** (los que tienen
`int(_id)` y `lastrowid`), cada uno con guardrail + tests headless.

---

## 5. Validación y criterios de salida

La fase se declara terminada cuando:

- [ ] `PRAGMA foreign_key_check` vacío tras la migración 200.
- [ ] Conteos por tabla idénticos pre/post.
- [ ] `test_uuidv7_cutover_forbidden_identity_patterns_do_not_increase`: todos los
      baselines del test bajan a **0** (AUTOINCREMENT, lastrowid, legacy_id,
      int(*_id)). Actualizar `FORBIDDEN_IDENTITY_BASELINE` a 0 en el mismo PR.
- [ ] Los 10 tests de identidad hoy en rojo pasan:
      `test_production_cost_service` (`'3'==3`), `test_production_query_service`,
      `test_product_catalog_refactor` (`datatype mismatch`), `test_waste_uuid_identity`,
      `test_configuracion_*`, `test_refactor_work_queue`.
- [ ] Suite completa sin regresiones nuevas.
- [ ] Bootstrap desde cero (`scripts/bootstrap_db.py`) produce esquema UUID.

---

## 6. Rollback y backup
- Backup automático del `.db` antes de la 200 (regla 26).
- Fallo → restaurar backup, bloquear arranque normal, log estructurado.
- La 200 es **irreversible una vez confirmada**; el rollback es restaurar backup,
  no una down-migration.

---

## 7. Plan de ejecución por incrementos (PRs)

1. **PR-A0 (este doc).** Diseño + alinear `legacy_id` (4→0) — cambio trivial y seguro.
2. **PR-A1..An (Fase A).** Por módulo: quitar `int(_id)`, `lastrowid`→`new_uuid()`,
   firmas `int`→`str`, guardrail + tests. Mergeables sin downtime.
3. **PR-B (Fase B).** Migración `200_uuid_cutover` + esquemas `TEXT` + runner
   offline + validación. Se mergea cuando Fase A está completa.
4. **PR-B1.** Bajar todos los baselines del cutover test a 0; alinear los 10 rojos.

---

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| FK huérfanas detienen la 200 | Pre-auditoría de integridad antes del corte; reporte de huérfanas |
| Triggers/índices con tipos viejos | Recrear desde definición nueva (paso 10) |
| Bases grandes no caben en RAM para mapas | Tabla temporal `_uuid_map` indexada |
| Código externo asume id entero (`int(...)`) | Fase A elimina la dependencia antes del corte |
| Backups insuficientes | Checksum + verificación de restore en staging |
| `operation_id` prefijado rompe parse | Decidir formato en §3.7 antes de Fase B |

---

## 8.5. Implementación (estado)

- ✅ **Motor de corte** `backend/infrastructure/db/uuid_cutover.py`
  (`UuidCutover` + `TableSpec`): introspectivo (`PRAGMA table_info`), construye
  mapas `old_id → uuid` para todas las tablas up-front (resuelve auto-refs sin
  orden topológico), reescribe PK+FK a `TEXT`, valida conteos, corre
  `PRAGMA foreign_key_check`, todo en una transacción; aborta+rollback ante
  huérfanos (o `on_orphan="null"`).
- ✅ **8 tests** (`tests/unit/test_uuid_cutover.py`): PK/FK→UUIDv7, auto-ref,
  conteos, defaults/columnas preservadas, huérfano→abort+rollback, huérfano→null,
  unicidad, sin AUTOINCREMENT post-corte.
- ✅ **Migración 200 scaffold GATED** `migrations/standalone/200_uuid_identity_cutover.py`:
  **NO registrada** en `engine.py` (nunca auto-corre); rehúsa sin
  `SPJ_UUID_CUTOVER_CONFIRMED=1` y sin `SPEC_IS_COMPLETE=True`. Tests de gating
  (`tests/architecture/test_uuid_cutover_migration_gated.py`).
- ✅ **Auditoría de esquema + spec auto-generado.**
  `tools/refactor_control/build_cutover_spec.py` introspecciona la DB y resuelve
  FKs por convención (mapa columna→padre + exclusión de ids polimórficos/externos).
  Resultado sobre el esquema real: **256 tablas** especificadas, **21 junction/config
  `pk=None`** (PK compuesta o `clave`/`key`), **clausura referencial verificada**
  (test). Salida committeada en `migrations/standalone/_cutover_spec_generated.py`,
  importada por la migración 200. El motor se extendió para `pk=None`
  (reescribe FKs sin convertir PK; preserva PK compuesta).
- ⏳ **Pendiente para ejecutar el corte real:**
  1. Resolver las **24 FK restantes** (mayoría *context-dependent*: misma columna,
     distinto padre según la tabla) con overrides por-tabla:
     `turno_id` (ventas/cierres_caja/movimientos_caja → turnos), `parent_id/padre_id`
     (self-ref por tabla), `origen_id`/`destino_id` (transferencias → sucursales),
     `bib_id`/`reservation_id`, `transformation_group_id`, `partner_id`/`tercero_id`,
     `order_id`, `cuenta_id` (→plan_cuentas), `tarjeta_id`, `paquete_id`, `goal_id`,
     `ticket_id`, `target_id`, `operacion_id`, `turno_rol_id`.
  2. Pre-auditar integridad (FKs huérfanas) sobre datos reales.
  3. Backup verificado + app cerrada + `SPEC_IS_COMPLETE=True` +
     `SPJ_UUID_CUTOVER_CONFIRMED=1`.
  4. Tras el corte: bajar a 0 los baselines del cutover test y alinear los 10 rojos.

## 9. Resumen ejecutivo
El corte es grande (398 PK, 122 lastrowid, 58 casts, 191 tablas) pero **acotado y
secuenciable**: Fase A (runtime `str`, incremental, sin downtime, por módulo) y
Fase B (un único corte de esquema atómico, offline, respaldado y validado).
MERMA y PRODUCTOS ya prueban el patrón de Fase A. El siguiente paso accionable y
seguro es **PR-A0**: cerrar `legacy_id` (4→0) y arrancar Fase A por el módulo de
mayor deuda de identidad.
