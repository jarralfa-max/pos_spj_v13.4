# Fase 4b: guardrules de identidad — el escáner analizaba librerías de terceros

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `d7640636`.

## Hallazgo principal: el escáner entraba al virtualenv

`SKIPPED_DIR_PARTS` de `tests/architecture/architecture_guardrails.py` excluía `.git`,
`__pycache__`, las cachés y `tests`, pero **no el virtualenv**. Y existe un `.venv`
**dentro** del paquete (`pos_spj_v13.4/.venv`, **2570 archivos `.py`**), de modo que todo
guardrail construido sobre `collect_regex_violations(roots=(APP_ROOT,))` recorría el
código fuente de las dependencias y lo reportaba como deuda arquitectónica propia.

Lo que `test_no_int_id_casts` estaba reportando como violaciones nuevas:

```
.venv/Lib/site-packages/anyio/_core/_sockets.py:355  int(scope_id)
.venv/Lib/site-packages/fpdf/fpdf.py:1689            int(resource_id)
.venv/Lib/site-packages/fpdf/output.py:1731,1737     int(font_id), int(img_id)
```

Ninguna es nuestra ni se puede cambiar. Un guardrail cuyo fallo exige editar `anyio` no
comunica nada accionable.

Se añaden `.venv`, `venv`, `site-packages` y `node_modules` a la exclusión. Efecto
secundario medido: la suite de arquitectura pasó de **922 s a 484 s**.

## Hallazgo secundario: prosa reportada como código (tercera aparición)

Mismo patrón ya corregido en `test_no_app_container_in_view_or_pages` (ver
`04_GUARDRAIL_PRECISION.md`), ahora en los guards de identidad:

`test_no_lastrowid_entity_identity` marcaba `backend/infrastructure/db/schema/meat_processing_schema.py:5`,
que es una línea de docstring **prometiendo** justo lo contrario:

    No ``INTEGER PRIMARY KEY AUTOINCREMENT``, no ``lastrowid``.

Peor: su allowlist toleraba tres entradas más cuyo propio comentario las describía como
"menciones en docstrings/documentación embebida (no código ejecutable)". Se verificó una
por una con el escaneo `code_only`:

| Archivo | Coincidencias crudas | Coincidencias en código |
| --- | ---: | ---: |
| `scripts/seed_demo.py` | 1 | **0** |
| `tools/refactor_control/bootstrap_refactor_state.py` | 2 | **0** |

Las tres eran prosa. **`LASTROWID_ALLOWLIST` queda vacío** — ratchet a cero real, no una
tolerancia trasladada.

Por ser la tercera aparición del mismo patrón, la solución se centraliza en vez de
repetirse: `code_only_source_lines()` en `architecture_guardrails.py` borra comentarios y
literales de cadena conservando números de línea y columnas, y
`collect_regex_violations(..., code_only=True)` lo expone. Los guards de identidad
(`lastrowid`, `int(..._id)`) lo usan; los de SQL y colores hexadecimales siguen leyendo
texto crudo **a propósito**, porque lo que buscan sí vive dentro de cadenas.

`test_code_only_scan_still_catches_executable_lastrowid` fija que ignorar docstrings no
convierte el guard en un no-op: exige que `cur.lastrowid` real se siga detectando.

## Deuda REAL que queda abierta y NO se toca aquí

`test_text_pk_not_null` es una infracción genuina y grande:

- **489 tablas** declaran `PRIMARY KEY` sobre columna `TEXT` **sin `NOT NULL`**. SQLite,
  por compatibilidad histórica, solo obliga a no-nulo en `INTEGER PRIMARY KEY`; en
  cualquier otra PK acepta `NULL` en silencio.
- La prueba de humo confirma que no es teórico: **`historico_puntos.id` admitió una fila
  con PK NULL**.

No se corrige en esta fase, y conviene decir por qué en lugar de dejarlo implícito:
alcanza a 489 tablas repartidas en decenas de módulos de esquema y migraciones, y en
SQLite añadir `NOT NULL` a una columna existente exige reconstruir la tabla, no un
`ALTER`. Hacerlo a medias es peor que no hacerlo. Es trabajo de la fase de esquema
(UUIDv7/Money), con su propia migración y su propia validación born-clean.

## Pruebas y evidencia

Desde `pos_spj_v13.4/` con `QT_QPA_PLATFORM=offscreen`:

```text
python -m pytest tests/architecture -q -p no:cacheprovider --tb=no
```

| Momento | Resultado | Duración |
| --- | --- | ---: |
| Tras `d7640636` | 34 failed, 736 passed, 1 skipped | 922 s |
| Ahora | **30 failed, 741 passed, 1 skipped** | **484 s** |

Diferencia de conjuntos: **4 cerrados, 0 nuevos**
(`test_no_int_id_casts`, `test_no_lastrowid_entity_identity` x2, y
`test_no_hardcoded_paths::test_no_loose_relative_paths`, que también caía por el
virtualenv).

## Riesgos residuales

Excluir el virtualenv es correcto, pero conviene registrar que **durante un tiempo
indeterminado estos guardrules estuvieron midiendo dependencias de terceros**; cualquier
conteo histórico de "violaciones" anterior a este commit está inflado y no debe citarse
como línea base.

Los 30 fallos restantes siguen sin clasificar uno a uno. La proporción observada hasta
ahora (7 de 17 trabajados resultaron falsos positivos del propio guardrail) desaconseja
tratar el número como deuda de producto sin leer antes cada assert.

## Siguiente fase

Esquema: `test_text_pk_not_null` (489 tablas) y
`test_no_schema_changes_outside_migrations`, junto con el ratchet UUIDv7. Es la fase 4 del
plan y necesita migración propia, no parches por archivo.
