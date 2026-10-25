# Slice 0 — Base transaccional local (ADR-006)

Fecha: 2026-10-24. Rama `claude/erp-financial-bounded-context-uqxz6b`, sin commit. Cierra **R-01** y **R-02**
del registro de riesgos (06). Es la precondición del Outbox de replicación (Slice 2): sin una frontera
transaccional confiable, un outbox «transaccional» puede publicar eventos de cambios que se revirtieron.

## Qué cambió

### R-01 — Una sola regla transaccional para todas las unidades de trabajo

**Antes.** Las 21 UoW de contexto (y `ConnectionUnitOfWork`) tenían cada una su propio `__enter__`,
`__exit__`, `commit` y `rollback`, copiados con pequeñas variantes. Ninguna abría la transacción: dependían
de que la conexión lo hiciera.

- La conexión del escritorio (`sqlite3.connect` en `DatabaseIntegrityStep`) abre transacciones implícitas,
  así que ahí funcionaban.
- El pool (`connection._new_connection`, `isolation_level=None`) confirma cada sentencia sola, y ahí
  `rollback()` no deshacía nada.
- Una UoW anidada en otra confirmaba la transacción de la de afuera a mitad del flujo. RRHH y Compras ya
  lo habían corregido cada una por su lado (HR-26), con registros separados.

**Ahora.** `backend/infrastructure/db/transaction.py::TransactionalUnitOfWork` es la base de todas. Regla
por conexión e hilo:

| Situación al entrar | Qué hace | Al salir bien | Al fallar |
|---|---|---|---|
| UoW más externa, sin transacción abierta | `BEGIN` | `COMMIT` | `ROLLBACK` |
| UoW anidada (de cualquier contexto) | `SAVEPOINT uow_N` | `RELEASE` (no confirma la de afuera) | `ROLLBACK TO` + `RELEASE` (sólo lo suyo) |
| `owns_transaction=False` | se une a la del llamador | nada | nada (decide el llamador) |
| UoW externa con una transacción ya abierta por código ajeno a una UoW | la hereda | `COMMIT` | `ROLLBACK` (igual que antes) |

Detalles que se conservan del contrato anterior:

- Caja rechaza un segundo `commit()` (`_reject_double_commit`).
- Una UoW usada sin `with` sigue confirmando con `commit()`.
- La propiedad `owns_transaction` de RRHH sigue existiendo.

**Duplicación eliminada:** 19 archivos `repositories/*/unit_of_work.py` pierden sus cuatro métodos, y RRHH y
Compras pierden su registro `_OPEN_DEPTH`.

### R-02 — Llaves foráneas en la conexión del escritorio

Nuevo paso de arranque `ForeignKeyEnforcementStep`, que corre **después** de migrar y validar el esquema,
nunca antes. Varias migraciones históricas reconstruyen tablas, y con FK activas su `DROP` borraría en
cascada o fallaría.

- Mide `PRAGMA foreign_key_check`. Con 0 violaciones, activa `foreign_keys=ON`.
- Con violaciones, **no** las activa: el POS abre igual, por continuidad de ventas. El arranque lo reporta
  como advertencia (`FOREIGN_KEYS_NOT_ENFORCED`) con las tablas y el número de registros afectados.

## Cambio de comportamiento deliberado

Una UoW anidada **ya no confirma** la transacción exterior; el efecto se hace durable cuando confirma la
UoW más externa. Si la exterior falla después, también se revierte lo de la anidada. Antes eso quedaba
confirmado a medias, que es justo el defecto que HR-26 encontró en RRHH.

Consecuencia operativa: otra conexión no ve esas escrituras hasta que termina la UoW exterior. Ninguna
prueba existente dependía de lo contrario (ver resultados).

## Evidencia

**Pruebas de contrato** (`tests/integration/shared/test_unit_of_work_transaction_contract.py`): 93 pasan.
Cada UoW real, descubierta del disco, se prueba con las **dos** conexiones reales de la app, la del
escritorio y la del pool:

- un rollback no deja filas;
- un éxito es visible desde otra conexión;
- la anidada revierte sólo lo suyo y espera a la exterior;
- `owns_transaction=False` no toca la conexión;
- Caja sigue rechazando el doble `commit`;
- el paso de FK activa las llaves o reporta los huérfanos;
- una guarda impide que una UoW vuelva a implementar su propio `commit`.

**Antes y después de R-01 sobre el pool:** con el contrato anterior, una fila insertada sobrevive al
rollback (1); ahora no (0).

**Impacto de activar FK, medido** forzando `foreign_keys=ON` en toda conexión durante las suites de
integración (plugin de medición fuera del repo):

- Ventas, Caja y Fidelidad: 432 pasan y 3 fallan. Las 3 vienen de la siembra a mano de las pruebas, que
  inventa ids padre (`draw_id=new_uuid()`, cortes sin conteo); no hay fallas de código de producción.
- Resto de contextos, archivo por directorio:
  - sin fallas: Compras, Finanzas, RRHH, Clientes, CRM, Proveedores, Precios y Costos;
  - Inventario: 3 fallas; Cárnico: 4; Productos: 10, más una caída de Qt en una prueba de diálogo.

  Las **29** fallas, sin excepción, vienen de pruebas que siembran ids inventados (`"prod-1"`,
  `"refresco"`, `species_id="pollo"`) o que no crean la tabla padre (`sucursales`). Sin el plugin, las
  mismas pruebas pasan. Los repositorios de producción tocados en esas trazas (despiece, recetas, códigos
  de barras) usan `ON CONFLICT DO UPDATE`, que no borra filas, así que son seguros con FK activas.
- Copia de la base real: 518 llaves foráneas en 354 tablas, 0 violaciones.

## Hallazgo colateral corregido

La medición destapó una regresión de la ronda de permisos (PERM-AUD), ajena a las FK. Desde que el dueño
es acceso total, su lista de permisos es el comodín `*`. La identidad móvil de Logística filtraba los
códigos por prefijo `LOGISTICA`, así que el dueño llegaba al teléfono **sin ninguna acción** y todo
respondía 403. `mobile_credentials._permissions` ahora decide con la regla única `is_granted`, que entiende
el comodín y `LOGISTICA.*`. La prueba que esperaba «dueño sin siembra = sin sesión» contradecía la
decisión de acceso total; se reemplazó por dos pruebas:

- el dueño tiene todas las acciones de Logística;
- un cajero sin permisos de Logística no obtiene sesión.

## Resultados

Regresión del 2026-10-24 con el código del Slice 0, sin plugins:

| Bloque | Resultado |
|---|---|
| Fidelidad, cupones y vales, sorteos, Ventas/POS, Caja, contrato de UoW | 1 180 pasan |
| Productos y Precios | 1 144 pasan |
| Inventario, Mermas, Proveedores, Compras | 1 618 pasan, 1 falla previa (`test_losses_schema_born_clean`) |
| Finanzas, RRHH, CRM, Clientes, Logística, Pedidos, Crédito, Cotizaciones | 1 492 pasan; 2 de etiquetas QR fallan por carga en la corrida paralela y pasan solas (18/18) |
| Seguridad, Configuración, Arranque | 746 pasan; 2 conteos de pasos actualizados por el paso nuevo, luego 254/254 en arranque |
| Procesamiento cárnico y Costos | 828 pasan |
| Arquitectura | 869 pasan; las mismas 23 fallas previas, ninguna nueva, ninguna toca archivos de este slice |

En una base nueva, la conexión de la app queda con `foreign_keys=1` (prueba de arranque).

## Reversión

- **R-01:** revertir `transaction.py` y los `unit_of_work.py` restaura el contrato anterior. No hay
  migración ni cambio de datos.
- **R-02:** quitar `ForeignKeyEnforcementStep` de `default_steps.py` y `run_database_bootstrap.py` vuelve a
  dejar las llaves apagadas. Tampoco cambia datos.

## Siguiente

**Slice 1:** contrato de evento de sincronización. Se extiende `SyncEnvelope` (CASH-19) con los campos del
§6.1 del prompt, con versión de esquema y serialización Decimal/UUIDv7, y se fija con pruebas unitarias.
