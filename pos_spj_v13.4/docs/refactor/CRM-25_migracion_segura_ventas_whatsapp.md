# CRM-25 — Migración segura de Ventas/WhatsApp fuera del stack legacy

Fecha: 2026-08-14. Tras el refresh de CRM-0 (`docs/architecture/
CRM_0_CUSTOMER_MASTER_AUDIT.md` §15), el usuario eligió cerrar el hallazgo
central que sigue abierto desde CRM-21/24: Ventas checkout y WhatsApp/API
REST siguen corriendo enteramente sobre el stack legacy de clientes
(`ClienteRepository`, `ClienteService`, `CustomerCreditService`, SQL directo
contra `clientes`), no sobre el nuevo Customer Master. Entre tres alcances
posibles, eligió el **subconjunto seguro** (permission checker + backfill +
bridging eager + limpieza de SQL directo), dejando el gate de crédito para
una fase futura dedicada — ver la investigación que motivó esa elección más
abajo.

## Por qué no fue un cutover completo

Tres agentes de investigación en paralelo mapearon cada punto de contacto
antes de escribir código. Hallazgo central: **el gate de crédito de Ventas
(`container.customer_credit_service.validate_credit`, el bloqueo real, no
el aviso de CRM-21) lee `cuentas_por_cobrar.cliente_id` — la identidad
LEGACY, nunca migrada al `customers.id` nuevo (brecha documentada desde
CRM-8).** Moverlo al Customer Master hoy calcularía exposición CERO para
cualquier cliente que solo existiera en el modelo nuevo — una regresión de
control financiero real, no solo una limpieza arquitectónica. Arreglarlo de
verdad requiere migrar `cuentas_por_cobrar.cliente_id` (Finanzas), fuera de
alcance aquí. El usuario confirmó explícitamente: "safe subset now, credit
gate later."

## Qué se hizo

### 1. Permission checker real para Ventas (prerrequisito)

`core/app_container.py`: se agregó `container.customer_authorization_policy`
— un `CustomerAuthorizationPolicy` respaldado por un
`CustomerSessionPermissionChecker(self.session)` real, mismo patrón que
`CashSessionPermissionChecker` ya usa en la misma clase. Antes de esto, el
único punto del repo que construía un `PermissionChecker` real para el
Customer Master era `frontend/desktop/modules/customers_crm/composition.py`
— cualquier llamada desde Ventas a un caso de uso autorizado del stack
nuevo fallaba en silencio (fail-closed, `CustomerAuthorizationPolicy()` sin
checker).

`modulos/ventas.py:4045+` (el aviso CRM-21 de elegibilidad comercial): ahora
pasa `container.customer_authorization_policy` en vez de depender del
default sin wire. **Segundo hallazgo real durante la implementación**: el
código pasaba `actor_user_id=str(self.usuario_actual or "")` — pero
`self.usuario_actual` es el NOMBRE DE USUARIO (username), mientras que
`CustomerSessionPermissionChecker` compara contra `session.user_id` (el id
real). Con solo el fix del checker, este aviso habría seguido siendo un
no-op permanente, ahora por un motivo distinto (mismatch de actor, no falta
de checker). Corregido a `str(self.container.session.user_id or "")`.

**Pendiente manual, no de código**: para que este aviso deje de degradarse
silenciosamente, el rol que usan los cajeros necesita el permiso
`CustomerPermissions.COMMERCIAL_ELIGIBILITY_CHECK` otorgado vía la matriz
de roles existente (`core/security/permission_catalog.py` +
tabla `roles_permisos`) — una decisión de datos/administración, no algo que
este código deba asumir u otorgar por sí mismo.

### 2. Fix de un bug real de migración, encontrado al aplicar contra datos reales

Migración 193 nunca se había corrido contra una base de datos real
(solo contra bootstraps en memoria en tests) — al aplicarla por primera vez
contra `data/spj_pos_database.db` falló: `create_customers_crm_schema(conn)`
crea incondicionalmente un índice único sobre `customers.legacy_customer_id`
ANTES de que la migración agregara esa columna. Corregido invirtiendo el
orden (agregar columna primero). Ver `migrations/MIGRATION_LOG.md` para el
detalle completo. Backup de la base tomada antes de aplicar (scratchpad de
la sesión — este repo no tiene red de seguridad de git para archivos reales,
hallazgo ya documentado desde CRM-21).

### 3. Backfill ejecutado

`tools/crm/backfill_legacy_customers.py --db data/spj_pos_database.db`
corrido con éxito tras el fix de la migración: 1 cliente legacy existente
(único cliente real en esta base de desarrollo) puenteado a una fila
`customers` nueva. El puente ya no depende solo de la resolución perezosa.

### 4. Bridging eager en la creación de clientes (Ventas + API)

- `modulos/ventas.py::guardar_nuevo_cliente` — nuevo método
  `_bridge_customer_to_crm(legacy_customer_id)`, llamado inmediatamente tras
  crear (o reseleccionar vía tarjeta ya asignada) un cliente. Antes, el
  único punto que resolvía el puente era el aviso de elegibilidad en el
  cobro — un cliente creado en Ventas podía tardar hasta el primer cobro a
  crédito en aparecer en el Customer Master.
- `api/routers/clientes.py::crear_cliente` — mismo patrón,
  `_bridge_customer_to_crm(db, cliente_id)` tras el alta.

### 5. Bug real encontrado y corregido: `guardar_nuevo_cliente` estaba roto

Al escribir tests de regresión ANTES de tocar `guardar_nuevo_cliente`
(`tests/test_ventas_customer_dialog_regression.py`), se confirmó que la
función está rota en producción HOY, sin relación con el alcance original
de esta fase:

```python
cliente_id = int(result["id"])          # result["id"] es un UUIDv7 string
self.seleccionar_cliente(int(result["id"]))   # este método NO EXISTE en la clase
```

`result["id"]` es un UUIDv7 (`backend/application/use_cases/
create_customer_use_case.py::CreateCustomerUseCase.execute()` siempre
devuelve `str(customer_id)`, nunca un entero) — `int(...)` sobre un UUID
lanza `ValueError` inmediatamente. El cliente SÍ se crea en la base (el
`commit()` ya ocurrió dentro del use case antes del cast), pero la UI
muestra "Error al guardar cliente" y nunca lo deja seleccionado para la
venta en curso. La rama de "tarjeta ya asignada" además llamaba a
`self.seleccionar_cliente(...)`, un método que nunca existió en
`ModuloVentas` (solo existe `_seleccionar_cliente` en una clase de diálogo
distinta) — habría lanzado `AttributeError` de no haber fallado antes el
`int()`.

**Corregido**: se eliminaron ambos casts a `int`, y la rama de "cliente
existente" ahora busca el registro completo vía `self._cli_repo.get_by_id(...)`
y llama a `self.actualizar_info_cliente()`, el mismo patrón ya establecido
en la rama de creación nueva. Regresión verificada: el test reproduce el
fallo contra el código original (falla), pasa tras el fix.

### 6. `api/routers/clientes.py` reescrito fuera de SQL directo

4 de 5 endpoints (`buscar_clientes`, `get_cliente`, `crear_cliente`,
`get_puntos`) hacían SQL directo sin pasar ni siquiera por
`ClienteRepository` — hallazgo original de la auditoría CRM-0 (§3/§11),
nunca cerrado. Ahora usan `ClienteRepository` para todo lo que es identidad
propia de Clientes; las lecturas cross-context (últimas ventas, saldo de
`loyalty_ledger`) se mantienen como SQL directo — mismo patrón sancionado
que `CustomerHistoryQueryService` ya usa para leer otros bounded contexts
de solo lectura. `crm-summary` (CRM-21) no se tocó, ya estaba correcto.

Dos ajustes de paridad de comportamiento encontrados al hacer el rewrite:
`ClienteRepository.crear()` no soporta `rfc`/`nivel` en su firma — el
endpoint original siempre fijaba `nivel='Bronce'` explícitamente, mientras
que el default real de la columna en producción es `'normal'` (no
`'Bronce'`); se preservó el comportamiento original con un `UPDATE`
puntual tras la creación, documentado inline. El fixture de tests
(`tests/test_fase_g_api_gateway.py`) tenía un esquema de `clientes` más
angosto que el real (sin `notas`/`fecha_alta`) — silenciosamente compatible
con el SQL directo anterior, pero no con `ClienteRepository.crear()`, que sí
las usa; corregido agregando esas dos columnas al fixture (con los mismos
defaults que la base real).

### 7. `whatsapp_service/erp/bridge.py` — mismo bug de identidad, en el fallback dev-only

`_create_cliente_minimo_impl` (alcanzable solo cuando `ERP_API_URL`/`KEY`
no están configurados — bloqueado en producción por
`_assert_sqlite_write_allowed`) insertaba sin especificar `id` y devolvía
`cursor.lastrowid` — para una tabla con `id TEXT PRIMARY KEY` (no
`INTEGER PRIMARY KEY`, que sí alias-ea el rowid), esto inserta una fila con
`id = NULL` silenciosamente. Corregido: nuevo helper `_new_customer_id()`
(usa `backend.shared.ids.new_uuid` del ERP vía el mismo truco de
`sys.path` que `erp/events.py` ya usa, con fallback a `uuid4` si el ERP no
es importable) y `_bridge_customer_to_crm()` en `ERPBridge`, mismo patrón
que Ventas/API. Verificado manualmente (la suite de tests de
`whatsapp_service` tiene una colisión de nombres preexistente, ver más
abajo) y con 2 tests nuevos.

## Explícitamente NO tocado en esta fase

- `container.customer_credit_service.validate_credit` — el gate real de
  crédito, sigue en el stack legacy (ver "Por qué no fue un cutover
  completo" arriba).
- `cuentas_por_cobrar.cliente_id` — prerequisito de lo anterior, fase
  futura de Finanzas.
- `CardBatchEngine`/escaneo de tarjetas de fidelidad
  (`modulos/ventas.py:2884+`) — correctamente dominio de Fidelidad, no del
  Customer Master (guardrail existente lo prohíbe).
- Búsqueda de clientes en checkout (`buscar_cliente`,
  `_customer_lookup_svc`) — el plan original consideraba migrarla
  defensivamente al `CustomerLookupQueryService` nuevo con fallback al
  legacy. **Se descartó al leer su firma real**: devuelve `customer_id` en
  el espacio de identidad NUEVO (`customers.id`), no el legacy
  `clientes.id` que el resto del checkout asume (`ventas.cliente_id`, el
  gate de crédito, el escaneo de tarjeta). Usarlo como fuente primaria de
  búsqueda habría requerido traducir de vuelta en cada tecla, sin beneficio
  real (el DTO ni siquiera trae puntos/saldo — esos siguen siendo de
  Fidelidad/Finanzas). `buscar_cliente` queda exactamente como estaba.
- `GET /clientes/{id}`'s joins a `ventas`/`loyalty_ledger` y
  `GET /clientes/{id}/puntos` — pertenecen a otros bounded contexts, solo
  se migró la porción de identidad propia de Clientes.

## Hallazgo no relacionado, solo documentado

Migración 165 (`product_catch_weight_config`, Productos — nada que ver con
Clientes) sigue fallando contra `data/spj_pos_database.db` con "table
product_catch_weight_config__new already exists" — nunca quedó registrada
en `schema_migrations`, deja una tabla `__new` huérfana de un intento
previo fallido. No es de este bounded context; no se tocó.

`whatsapp_service/tests/` tiene una colisión de nombres preexistente (no
introducida aquí): el microservicio tiene su propio paquete `config/`, pero
el ERP tiene un `config.py` de nivel superior — según el orden en que
`sys.path.insert(0, ...)` se llama, uno u otro gana. Los tests existentes
(`test_bridge_notification_routing.py`) insertan el path del ERP DESPUÉS
del propio, haciendo que el `config.py` del ERP gane y falle la colección
con `ModuleNotFoundError: No module named 'config.settings'`. El nuevo test
de esta fase invierte el orden correctamente y sí corre. No se tocó el
resto de la suite (fuera de alcance).

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/customers/ tests/unit/crm/ \
  tests/integration/customers/ tests/integration/crm/ \
  tests/test_ventas_customer_dialog_regression.py \
  tests/test_fase_g_api_gateway.py tests/test_ventas_fixes.py -q
```

- 636 tests pasando; 6 fallas confirmadas preexistentes y sin relación
  (4 de `TestGetStockSucursal`, lógica de inventario por sucursal ajena a
  Clientes; 2 substring-checks obsoletos en `test_ventas_fixes.py` que ya
  fallaban antes de esta fase — verificado leyendo el código original antes
  de tocarlo).
- `tests/test_ventas_customer_dialog_regression.py` (nuevo, 3 tests):
  reproduce el bug real de `guardar_nuevo_cliente` contra el código
  original (falla), confirma el fix, más una prueba de referencia para
  `buscar_cliente` antes de decidir NO tocarlo.
- `tests/test_fase_g_api_gateway.py::TestClientesRouter` (7 tests
  preexistentes): siguen pasando idénticos tras el rewrite del router.
- `whatsapp_service/tests/test_bridge_create_cliente_minimo.py` (nuevo, 2
  tests): verifican el id UUID real y unicidad entre llamadas.
- Sintaxis y import limpios en todos los archivos tocados
  (`core/app_container.py`, `modulos/ventas.py`, `api/routers/clientes.py`,
  `migrations/standalone/193_*.py`, `whatsapp_service/erp/bridge.py`).
- `tools/crm/backfill_legacy_customers.py` corrido contra la base de
  desarrollo real, verificado con conteo antes/después (1 cliente → 1
  fila puenteada).
- Suite completa `tests/architecture/` corrida en segundo plano para
  confirmar que ningún guardrail repo-wide reaccionó a estos cambios más
  allá de lo ya esperado.

## Pendiente (fases futuras)

- Migrar `cuentas_por_cobrar.cliente_id` a la identidad nueva — prerequisito
  real para poder mover el gate de crédito de Ventas.
- Una vez migrado eso: mover `container.customer_credit_service.validate_credit`
  al Customer Master.
- Otorgar `CustomerPermissions.COMMERCIAL_ELIGIBILITY_CHECK` (y las que
  correspondan) a los roles reales de cajero/vendedor vía la matriz de
  permisos — sin esto, el aviso CRM sigue degradándose en silencio (por
  diseño, nunca bloquea la venta).
- Migración 165 (Productos) — corromper la base de desarrollo con una tabla
  huérfana `product_catch_weight_config__new`; fuera de este alcance pero
  vale la pena que alguien de Productos lo revise.
