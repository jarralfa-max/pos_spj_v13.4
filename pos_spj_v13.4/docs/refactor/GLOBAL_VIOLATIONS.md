# Violaciones globales del refactor

## Estado

Preflight global inicial ejecutado el 2026-06-14.

El proyecto permanece en `IN_PROGRESS`; el módulo actual es `CONFIGURACION` en `AUDIT`. Las violaciones UUIDv7 se conservan como hallazgos globales y deben tratarse dentro de cada módulo aplicable.

## Comandos ejecutados

```text
python -m compileall pos_spj_v13.4
python -m pytest pos_spj_v13.4/tests/architecture -q
rg -n --pcre2 -i <patrón> pos_spj_v13.4
```

## Resultado preflight

| Gate | Resultado |
| ---- | --------- |
| Raíz correcta | PASS |
| Carpetas de refactor externas nuevas | PASS |
| compileall | PASS |
| tests de arquitectura | PASS: 89 passed, 4 skipped |
| Búsqueda negativa global | FAIL: 4197 coincidencias clasificadas |
| SQLite integrity_check | PENDING: requiere selección de DB real de prueba |
| Migraciones pendientes | PENDING: requiere auditoría de migraciones durante UUIDV7_CUTOVER |

## Categorías obligatorias

### Identidad UUIDv7

- OPEN: `INTEGER PRIMARY KEY AUTOINCREMENT` — 803 coincidencias.
- OPEN: `lastrowid` — 147 coincidencias.
- OPEN: `legacy_id` — 14 coincidencias.
- OPEN: `int(product_id)` — 33 coincidencias.
- OPEN: `int(branch_id)` — 28 coincidencias.
- OPEN: `int(sale_id)` — 5 coincidencias.
- OPEN: `int(customer_id)` — 2 coincidencias.
- OPEN: `int(reservation_id)` — 4 coincidencias.

### SQL en UI

- OPEN: requiere clasificación por archivo de `CREATE TABLE`, `ALTER TABLE`, SQL directo y rutas PyQt durante la auditoría UUIDv7.

### Commit o rollback en UI

- OPEN: `commit()` — 743 coincidencias globales pendientes de clasificar por capa.
- OPEN: `rollback()` — 39 coincidencias globales pendientes de clasificar por capa.

### Schema fuera de migrations

- OPEN: `CREATE TABLE` — 1212 coincidencias globales pendientes de clasificar por ubicación.
- OPEN: `ALTER TABLE` — 132 coincidencias globales pendientes de clasificar por ubicación.

### Rutas duplicadas

- OPEN: pendiente de grafo de dependencias por módulo.

### Fuentes duplicadas de verdad

- OPEN: `productos.existencia` — 31 coincidencias.
- OPEN: `branch_inventory` — 229 coincidencias.

### Defaults numéricos hardcodeados

- OPEN: `QInputDialog.getDouble` — 12 coincidencias pendientes de revisar valor inicial visible.
- OPEN: `setValue(...)` distinto de cero — 164 coincidencias pendientes de revisar si son captura visible o estado interno.

### Estilos hardcodeados

- OPEN: colores hexadecimales — 558 coincidencias pendientes de clasificar contra design tokens.

### Excepciones silenciosas

- OPEN: `except Exception: pass` — 251 coincidencias.

### Código legacy

- OPEN: coincidencias de identidad legacy, fuentes de stock legacy y rutas antiguas detectadas arriba.

### Tests

- PASS: arquitectura actual `89 passed, 4 skipped`.
- PASS: protección inicial UUIDv7 creada para generador canónico, fallback UUIDv7, colisión offline y no incremento de patrones prohibidos.
- PENDING: ampliar protección a schema/FK y migración atómica global.

## Hallazgos registrados

```text
ID: GLOBAL-PREFLIGHT-001
Severidad: CRITICAL
Categoría: Identidad UUIDv7
Módulo: UUIDV7_CUTOVER
Archivo: Repositorio completo
Línea: N/A
Descripción: Existen coincidencias globales de AUTOINCREMENT, lastrowid, legacy_id y casts int(..._id).
Causa raíz: El corte UUIDv7 global aún no ha sido implementado y conviven patrones de identidad entera/legacy.
Test de protección: Crear tests anti-AUTOINCREMENT, anti-lastrowid, anti-legacy_id y anti-int-cast.
Estado: OPEN
Iteración detectada: 1
Iteración corregida:
```

```text
ID: GLOBAL-PREFLIGHT-002
Severidad: CRITICAL
Categoría: Schema fuera de migrations
Módulo: UUIDV7_CUTOVER
Archivo: Repositorio completo
Línea: N/A
Descripción: Existen coincidencias globales de CREATE TABLE y ALTER TABLE pendientes de clasificar por ubicación.
Causa raíz: La auditoría de migraciones y schema runtime no ha sido cerrada.
Test de protección: Crear/fortalecer tests de schema únicamente en migrations.
Estado: OPEN
Iteración detectada: 1
Iteración corregida:
```

```text
ID: GLOBAL-PREFLIGHT-003
Severidad: HIGH
Categoría: Fuentes duplicadas de verdad
Módulo: UUIDV7_CUTOVER
Archivo: Repositorio completo
Línea: N/A
Descripción: Existen referencias a productos.existencia y branch_inventory incompatibles con inventory_stock como fuente canónica.
Causa raíz: Persisten fuentes antiguas o referencias documentales/legacy de inventario.
Test de protección: Tests de fuente única inventory_stock e inexistencia de lecturas operativas legacy.
Estado: OPEN
Iteración detectada: 1
Iteración corregida:
```

```text
ID: GLOBAL-PREFLIGHT-004
Severidad: HIGH
Categoría: Excepciones silenciosas
Módulo: UUIDV7_CUTOVER
Archivo: Repositorio completo
Línea: N/A
Descripción: Existen coincidencias de except Exception: pass.
Causa raíz: Manejo de errores silencioso no auditado.
Test de protección: Test arquitectónico anti except Exception: pass fuera de allowlist justificada.
Estado: OPEN
Iteración detectada: 1
Iteración corregida:
```

## Regla

No borrar hallazgos corregidos.

Cambiar su estado a `RESOLVED` para conservar trazabilidad.

```text
ID: GLOBAL-PREFLIGHT-005
Severidad: HIGH
Categoría: Tests
Módulo: UUIDV7_CUTOVER
Archivo: pos_spj_v13.4/tests/architecture/test_uuidv7_cutover_protection.py
Línea: N/A
Descripción: Se agregó protección inicial para generación UUIDv7 canónica y para impedir que aumenten patrones prohibidos de identidad.
Causa raíz: Antes no existía prueba de protección del generador único ni baseline ejecutable de identidad.
Test de protección: test_uuidv7_cutover_protection.py
Estado: OPEN
Iteración detectada: 2
Iteración corregida:
```

```text
ID: GLOBAL-PREFLIGHT-006
Severidad: HIGH
Categoría: Rutas duplicadas
Módulo: UUIDV7_CUTOVER
Archivo: pos_spj_v13.4/docs/refactor/work_queue.json
Línea: N/A
Descripción: Las infracciones globales fueron agrupadas en lotes ejecutables; UUID-02-SCHEMA_GRAPH queda activo para clasificar schema/PK/FK antes de migrar.
Causa raíz: El contador global no era ejecutable por causa raíz.
Test de protección: test_refactor_work_queue.py
Estado: OPEN
Iteración detectada: 4
Iteración corregida:
```

```text
ID: GLOBAL-PREFLIGHT-007
Severidad: HIGH
Categoría: Schema fuera de migrations
Módulo: UUIDV7_CUTOVER
Archivo: pos_spj_v13.4/docs/refactor/UUIDV7_SCHEMA_CLASSIFICATION.json
Línea: N/A
Descripción: UUID-02-SCHEMA_GRAPH quedó cerrado con clasificación inicial de tablas funcionales, técnicas y pendientes de revisión.
Causa raíz: Era necesario convertir señales schema dispersas en inventario clasificable antes de diseñar migración.
Test de protección: test_refactor_work_queue.py
Estado: OPEN
Iteración detectada: 5
Iteración corregida:
```
