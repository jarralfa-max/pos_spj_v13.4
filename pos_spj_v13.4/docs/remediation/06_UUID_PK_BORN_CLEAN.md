# Fase 4c: PRIMARY KEY TEXT no nulable — mitad born-clean cerrada

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `6f4db158`.

## El problema

En SQLite, **solo `INTEGER PRIMARY KEY` obliga a no-nulo**. Cualquier otra PRIMARY KEY
—incluida `TEXT PRIMARY KEY`, que es la forma canónica de UUIDv7 en este sistema— acepta
`NULL` en silencio por compatibilidad histórica. Un `INSERT` que omita la PK escribe una
fila sin identidad y no falla.

`test_text_pk_not_null` reportaba **489 tablas** en esa situación, y su prueba de humo
confirmaba que no era teórico: `historico_puntos.id` admitió efectivamente una fila con PK
NULL.

Es la deuda **real** más grande del inventario de arquitectura: a diferencia de los siete
falsos positivos corregidos en `04_` y `05_`, aquí el guardrail tenía razón.

## El patrón ya existía en el repositorio

`migrations/standalone/165_products_profile_pk_notnull.py` resolvió exactamente esto para
tres tablas de perfiles de producto, y su docstring documenta el procedimiento en dos
pasos:

1. corregir el DDL canónico en `*_schema.py` a `TEXT NOT NULL PRIMARY KEY`;
2. una migración **idempotente y guardada** que reconstruye las tablas **existentes**,
   sin pérdida de datos, y que no hace nada sobre un bootstrap limpio.

Se siguió ese patrón en lugar de inventar uno nuevo.

## Paso 1 (hecho): DDL canónico

Transformación sobre `backend/infrastructure/db/schema/**` y `migrations/**`:

    ^(\s*)(\w+)(\s+)TEXT PRIMARY KEY   ->   \1\2\3TEXT NOT NULL PRIMARY KEY

Anclar la expresión al inicio de línea es lo que la hace segura. Validado en seco contra
los casos peligrosos antes de escribir nada:

| Línea | ¿Se reescribe? | Por qué importa |
| --- | --- | --- |
| ``- Every id is ``TEXT PRIMARY KEY`` holding…`` | **No** | docstring; reescribirlo sería el mismo error de "prosa como código" de `05_` |
| `if not create_sql or "product_id TEXT PRIMARY KEY" not in create_sql:` | **No** | literal de la migración 165; alterarlo rompería su guarda de idempotencia |
| `id TEXT PRIMARY KEY,` | Sí | DDL real |
| `id TEXT PRIMARY KEY CHECK({_uuid('id')}),` | Sí | DDL real; el `CHECK` se conserva intacto |
| `id TEXT NOT NULL PRIMARY KEY,` | **No** | ya correcta |

Resultado: **492 definiciones de columna reescritas en 41 archivos**. Los únicos
`TEXT PRIMARY KEY` restantes son prosa de docstring y el literal de la migración 165.
Adicionalmente se alinearon 19 docstrings que enunciaban la regla sin el `NOT NULL`.

## Paso 2 (NO hecho): reconstrucción de instalaciones existentes

**Esto es lo importante de este documento.**

Falta la migración que reconstruye las tablas ya creadas. No se escribió, y la razón es
concreta, no falta de tiempo: la migración 165 pudo reconstruir sus tres tablas porque,
según su propio docstring, *"las 3 tablas no tienen índices propios"*. **Su lógica de
rebuild no preserva índices.** Generalizarla a 489 tablas —muchas con índices,
constraints y triggers propios— los eliminaría en silencio, degradando rendimiento e
integridad sin que ninguna prueba lo detectara.

Una reconstrucción masiva segura necesita, como mínimo: releer `sqlite_master` para
índices y triggers de cada tabla, recrearlos tras el swap, verificar
`PRAGMA foreign_key_check` y `PRAGMA integrity_check` al final, y una prueba que compare
el esquema completo (no solo las PKs) antes y después. Es un diseño propio, no una
extrapolación del caso de tres tablas.

## Consecuencia honesta del estado actual

**Una base de datos nueva ya nace correcta. Una instalación existente sigue con PKs
nulables — y el guardrail está ahora en verde.**

`test_text_pk_not_null` construye una DB born-clean, así que valida el paso 1 y no dice
absolutamente nada sobre el paso 2. Su verde **no** debe leerse como "el problema de PKs
nulables está resuelto en producción".

Se deja escrito aquí y en el commit porque un verde que oculta media verdad es exactamente
el patrón que `04_` y `05_` documentan como el fallo más caro de este repositorio.

## Pruebas y evidencia

Desde `pos_spj_v13.4/` con `QT_QPA_PLATFORM=offscreen`:

```text
python -m pytest tests/architecture/test_text_pk_not_null.py -q -p no:cacheprovider
```
Resultado: **6 passed** (antes 2 failed: 489 tablas y la prueba de humo).

```text
python -m pytest tests/unit/bootstrap/ tests/integration/bootstrap/ \
  tests/integration/security/ tests/integration/shell/ -q -p no:cacheprovider
```
Resultado: **359 passed**. Estas suites construyen esquema born-clean completo, que es la
superficie que este cambio toca.

```text
python -m compileall backend/infrastructure/db/schema migrations
```
Resultado: **exit 0**.

## Riesgos residuales

El paso 2 pendiente es el riesgo principal y está descrito arriba.

El cambio altera el DDL que producen migraciones ya publicadas. Para una instalación
existente esto no reescribe nada (el DDL solo corre en `CREATE TABLE IF NOT EXISTS`), pero
sí significa que dos instalaciones de distinta antigüedad tendrán esquemas divergentes en
la nulabilidad de la PK hasta que exista la migración de reconstrucción.

No se ejecutó validación manual sobre una base de datos operativa real.

## Siguiente fase

Money/Decimal: `test_no_monetary_float.py` y `test_no_monetary_real_schema.py` que §39 del
prompt maestro exige **todavía no existen**, de modo que la deuda de dinero `REAL`/`float`
no está medida por ningún guardrail. Crearlos es el paso "IDENTIFICAR → TEST QUE DEMUESTRE
EL PROBLEMA" antes de tocar esquema monetario.

---

## Anexo — tres pruebas fijaban la forma DÉBIL

Detectado al comparar los **conjuntos** de fallos de `tests/integration` antes y después,
no sus totales. Los totales coincidían exactamente (91 failed / 3350 passed / 17 errors en
ambas corridas) y aun así **había una regresión**: una prueba se arregló y otra se rompió,
compensándose. Confiar en el total habría dejado pasar el fallo.

Tres pruebas afirmaban la presencia literal de la forma sin `NOT NULL`:

| Prueba | Afirmaba |
| --- | --- |
| `tests/integration/test_transfers_schema.py` | `"ID TEXT PRIMARY KEY" in ddl` |
| `tests/architecture/test_cash_offline_first_boundary.py` | `assertIn("ID TEXT PRIMARY KEY", migration)` |
| `tests/architecture/test_pricing_uses_uuidv7.py` | `"id TEXT PRIMARY KEY" in joined` |

Las tres se **endurecen** a la forma fuerte y además se les añade la negación de la débil
(`assert "id TEXT PRIMARY KEY" not in ...`), de modo que un retroceso futuro las rompa.
No se relajó ninguna.

Resultado tras el endurecimiento:

```text
python -m pytest tests/architecture -q -p no:cacheprovider --tb=no
```

| Momento | Resultado | Duración |
| --- | --- | ---: |
| Tras `6f4db158` | 30 failed, 741 passed, 1 skipped | 484 s |
| Ahora | **28 failed, 743 passed, 1 skipped** | 385 s |

Diferencia de conjuntos: **2 cerrados, 0 nuevos**.

**Lección para las fases siguientes**: comparar conjuntos, nunca totales. Un cambio de
esquema amplio puede arreglar y romper el mismo número de pruebas.
