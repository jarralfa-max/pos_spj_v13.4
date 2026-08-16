# CRM-41 — Fase 7: consecutivo transaccional + detección de duplicados sin full scan

Fecha: 2026-08-16. A petición del usuario de retomar "FASE 7 — BASE DE
DATOS". Dos hallazgos reales, ambos con el antipatrón exacto que el
prompt maestro nombra explícitamente.

## 1. `customer_number`: SELECT-último+1 sin reintento

`CustomerRepository.next_code()` es exactamente el antipatrón que el
prompt prohíbe: `SELECT customer_number ORDER BY ... DESC LIMIT 1` +
incremento en Python. La columna ya tenía `UNIQUE` (red de seguridad real
— nunca podía producirse un duplicado silencioso), pero sin reintento, un
choque bajo escritura concurrente (dos altas de cliente al mismo tiempo,
plausible en un POS multi-sucursal) hacía que la segunda transacción
recibiera un `sqlite3.IntegrityError` crudo sin manejar, en vez de
simplemente obtener el siguiente número real.

**Fix**: `CreateCustomerUseCase.execute()` ahora reintenta (máx. 5
intentos) específicamente ante una violación de `UNIQUE` en
`customer_number` — bajo el modelo de bloqueo de escritor único de
SQLite, para cuando un escritor recupera el lock y reintenta, la fila en
conflicto ya está comprometida y visible para la siguiente lectura de
`next_code()`, así que el reintento se resuelve correctamente sin
condición de carrera residual. Cualquier otra violación de integridad
(operation_id duplicado, etc.) se sigue propagando sin cambios — el
`except` solo atrapa colisiones de `customer_number` específicamente
(inspecciona el mensaje del error).

## 2. Detección de duplicados: cargaba TODOS los clientes en cada alta

`CustomerRepository.find_duplicate_rows()` no tenía ningún `WHERE` —
cargaba la tabla `customers` completa (con joins a tax_profiles/contacts)
en **cada creación de cliente**, para que `CustomerDuplicatePolicy`
comparara el candidato contra todos en Python. Con 2 filas en dev,
invisible; en producción real, un full scan en cada alta — el antipatrón
exacto de "Duplicados" que el prompt nombra ("no cargar todos los
clientes para cada búsqueda").

Confirmado que `CustomerDuplicatePolicy.find_matches()` solo reporta
coincidencias por **igualdad exacta** de cuatro claves (RFC, teléfono,
correo, nombre normalizado) — nunca fuzzy — lo que hace estas cuatro
claves candidatas perfectas para "blocking keys" en SQL: cualquier
duplicado real necesariamente comparte al menos una con el candidato.

**Fix**: nuevo método `find_duplicate_rows_matching(...)` que filtra por
SQL (`normalized_name`/`normalized_legal_name` — columnas nuevas,
mantenidas en sync en cada `save()`/`update()` — más `tax_identifier`,
`phone_e164`, `email` vía join) en vez de cargar todo. El método original
sin filtro (`find_duplicate_rows()`) se dejó intacto — dos llamadores
reales (`import_use_cases.py`, batch CSV; `duplicate_use_cases.py`, el
escaneo "detectar todos los duplicados del sistema") genuinamente
necesitan la tabla completa, no un candidato único — cambiar su
comportamiento habría sido una regresión real, no una optimización.

## Índices agregados

Coinciden con la lista explícita del prompt maestro que faltaban:
`customers.normalized_name`, `customers.normalized_legal_name`,
`customer_contacts.phone_e164`, `customer_contacts.email`,
`customer_tax_profiles.tax_identifier`. (`customer_number`, `status`,
`origin_branch_id`, `account_owner_user_id`, `territory_id` ya estaban
indexados desde CRM-2/3 — verificado, no reconstruido.)

## Migración

`migrations/standalone/197_customers_normalized_name_blocking_keys.py` —
agrega las dos columnas derivadas (idempotente, mismo patrón que la 193),
**backfillea** las filas ya existentes (de otro modo quedarían
invisibles para la detección de duplicados hasta su próxima edición), y
crea los cinco índices nuevos.

## Explícitamente NO tocado (con razón)

- **FTS5 para `search_lookup()`**: `CustomerLookupQueryService`/
  `CustomerRepository.search_lookup()` (typeahead de checkout) sigue
  usando `LIKE '%texto%'` — un wildcard inicial que no puede usar índice
  B-tree. Confirmado el antipatrón, pero implementarlo correctamente
  requiere sincronizar una tabla virtual FTS5 a través de DOS tablas
  (`customers` + `customer_contacts`, con teléfono/correo en la hija) vía
  triggers — una pieza de mayor riesgo/complejidad que el problema de
  duplicados (que no tenía límite de resultados ni ejecutaba en cada
  búsqueda, solo en cada alta). Con el límite (`LIMIT 20`) ya presente en
  `search_lookup()`, el impacto práctico hoy es menor que el de
  duplicados — se prioriza documentarlo con precisión en vez de apurar
  una migración de triggers sin la validación que merece.
- **Triggers/columnas/tablas legacy sin consumidores**: fuera del alcance
  de Clientes/CRM — no se auditó el esquema completo del ERP (cientos de
  tablas de otros bounded contexts), consistente con el alcance de toda
  esta sesión.

## Verificación

```bash
python -m pytest tests/integration/customers/ \
  tests/architecture/test_customers_crm_*.py -v
```
176 tests pasando (18 nuevos: 2 de reintento de customer_number, 16 de
blocking keys/sync), cero regresiones. Migración 197 verificada
ejecutándose limpia vía `migrations.engine.up()` completo.
