# Inventario — Plan de operacionalización de UI (post-auditoría externa)

## 0. Origen

Auditoría funcional externa del módulo de Inventario, recibida el 2026-08-08:

- Repositorio: `jarralfa-max/pos_spj_v13.4`
- Rama auditada: `claude/erp-financial-bounded-context-uqxz6b`
- Referencia: PR #326 (abierta al momento de la auditoría)
- Veredicto: **NO APROBADO COMO MÓDULO OPERATIVO** — backend e infraestructura
  de lectura completos, pero el frontend es casi exclusivamente de consulta;
  faltan comandos/acciones/formularios que conviertan las 21 páginas en
  workflows ejecutables.

Los hallazgos se verificaron contra el código real (no se asumió el reporte
como correcto sin comprobar). Confirmados por lectura directa:

- **P0-01** (`frontend/desktop/modules/inventory/presenter.py`): ~20 métodos
  de lectura, un solo comando (`generate_suggestions`).
- **P0-02** (`modulos/inventario_enterprise.py::_build_presenter`): solo
  `InventoryUseCaseFactory.generate_replenishment_suggestions()` se inyecta;
  ningún otro use case (ajustes, conteos, cuarentena, reservas...) llega al
  presenter aunque el factory ya los expone.
- **P0-03** (`backend/application/inventory/composition.py`): el backend sí
  tiene los builders (`create_adjustment`, `create_count`, `quarantine_stock`,
  `record_temperature_reading`, etc.) — está huérfano de interfaz, no ausente.
- **P0-09** y variante de **P0-06** encontrada en el mismo archivo: `_Session`
  (clase privada) congelaba `user_id`/`branch_id` en el `__init__`, antes de
  que el login pudiera completarse, y — más grave — construía
  `_Session(user_id, branch_id, branch_id)`: **`warehouse_id` recibía
  literalmente `branch_id`**, la violación explícita que CLAUDE.md prohíbe
  ("NO warehouse_id=branch_id"), en el propio composition root de la UI.

El orden de ejecución lo definió el usuario (no es una decisión automática):
empezar por **P0-A — Sesión y composition root**, por ser la base de la que
depende cualquier acción que se agregue después (sin sesión/scope reales,
un botón nuevo mutaría con identidad o alcance incorrectos).

## 1. Pendiente (orden del audit, seguirá con P0-B/C/D/E)

1. ~~P0-A: sesión y composition root~~ — **HECHO (slice 1, abajo)**.
2. ~~P0-B/C: página piloto (Cuarentena) — liberar/disponer~~ — **HECHO (slice 2,
   abajo)**.
3. ~~P0-D piloto: búsqueda canónica de producto + "Poner en cuarentena"~~ —
   **HECHO (slice 3, abajo)**. `InventoryPresenter.product_options()` y
   `EntitySearchInput` quedan listos para reutilizarse en Ajustes, Reservas,
   Lotes y Conteos — pendiente cablearlos ahí (mismo patrón, otro use case).
   Pendiente explícito: selector de ubicación (hoy `open_quarantine` asume la
   ubicación por defecto del almacén; sin selector de ubicación real).
4. **P0-C (Ajustes) — EN CURSO, pausado en un punto seguro (slice 4, abajo).**
   Se corrigió el mismo bug de `row_ids` que Cuarentena tenía (folio en vez de
   id real) y se expuso `InventoryUseCaseFactory.reverse_adjustment()` (existía
   el caso de uso, faltaba el builder). **Falta**: comandos en el presenter
   (`create_/approve_/post_/reverse_adjustment`), diálogos y botones en
   `AdjustmentsPage` — el mismo patrón que Cuarentena, retomar cuando se
   continúe P0-C.
5. P0-E: integración entre módulos (refresco por eventos tras venta/compra/
   producción; auditar y corregir `warehouse_id=branch_id` en los bridges de
   Ventas/Compras/Producción — el propio audit señala que ahí también existe).
   **← siguiente, en curso.**
6. P1: `InventoryUiEventBridge` (refresco reactivo) + pruebas de workflow por
   página (no solo de tablas).

## 2. Slices ejecutados

### Slice 1 — P0-A: sesión viva + fin de `warehouse_id=branch_id` en el shell — HECHO

**Archivos:**
- `modulos/inventario_enterprise.py`
- `frontend/desktop/modules/inventory/presenter.py`
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py` (nuevo)

**Cambio:**

1. `modulos/inventario_enterprise.py`: se eliminó la clase privada `_Session`
   y el atributo redundante `_live_session`. `ModuloInventarioEnterprise`
   ahora toma `container.session` (la instancia `SessionContext` viva, la
   misma que ve el resto del sistema) y la pasa **directamente** como
   `session_context` del presenter — no se construye ninguna copia. Sin
   `container.session` (arneses de prueba mínimos), queda en `None`: las
   lecturas devuelven vacío y las mutaciones se niegan aguas abajo (política
   real, fail-closed). Esto también resuelve P0-09: un login que completa
   después de construir el widget, o un cambio de sucursal, se observa en
   vivo sin reconstruir nada, porque `SessionContext` se actualiza in-place
   (`set_sucursal`/`set_warehouse`/`set_user`) y el presenter guarda la misma
   referencia.
2. `frontend/desktop/modules/inventory/presenter.py`: `default_branch()` y
   `default_warehouse()` leían `session.branch_id`/`session.warehouse_id` —
   atributos que la `_Session` congelada sí tenía (por eso "funcionaba"), pero
   que **`SessionContext` real no expone** (su API es `active_branch_id`/
   `active_warehouse_id`, ver `core/session_context.py`). Se corrigieron para
   leer primero los campos reales de `SessionContext` (`active_branch_id`,
   `active_warehouse_id`), con fallback a `branch_id`/`warehouse_id` para no
   romper dobles de prueba simples que ya usan esos nombres (p. ej. el
   `_Session` de test en `test_inventory_ui_presenter.py`). Sin este cambio,
   pasar `container.session` real habría dejado `default_branch()` siempre
   vacío (mismatch de atributos), rompiendo todas las lecturas con alcance de
   sucursal.

**Por qué no se tocó `InventoryUseCaseFactory.from_session(...)`:** esa parte
ya estaba correcta — recibía `self._live_session` (la sesión viva real) desde
antes; el bug estaba en que el *presenter* recibía la copia congelada en vez
de esa misma sesión viva. `InventorySessionPermissionChecker` (el checker real
de autorización) ya consume `session.tiene_permiso`/`session.user_id`
directamente, sin pasar por `_Session`.

**Evidencia:**
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py`
  (2, nuevo — no existía ningún test que construyera
  `ModuloInventarioEnterprise`): confirma `widget._session is
  container.session` (misma instancia, no copia); confirma que sin almacén
  fijado en la sesión `default_warehouse()` queda `""` (nunca cae en la
  sucursal); confirma que `set_sucursal`/`set_warehouse` posteriores a la
  construcción se reflejan sin reconstruir el widget; confirma degradación
  correcta (`None`, sin fabricar) cuando el contenedor no expone `.session`.
- Guardrails existentes (ya cubrían parte de esto, se mantienen en verde):
  `tests/architecture/test_inventory_authorization_fail_closed.py`
  (`test_inventory_ui_has_no_fabricated_identity_fallback` — verifica
  literalmente que `default_warehouse` no caiga en `default_branch()` y que
  no haya fallbacks `or "desktop"/"1"/...`), `test_fase_a_identity_clean_modules.py`,
  `test_inventory_no_silent_pass.py`, `test_inventory_no_legacy_permissions.py`,
  `test_inventory_ui_guardrails.py`, `test_app_container_inventory_canonical_route.py`
  → **58 passed** sin cambios.
- `tests/integration/inventory/test_inventory_ui_presenter.py` (su propio
  doble de sesión usa `branch_id`/`warehouse_id`, cubierto por el fallback) →
  sin cambios.
- Inventario completo (`tests/unit/inventory` + `tests/integration/inventory`):
  `2 failed / 575 passed` (2 pre-existentes — `test_legacy_reader_repoints.py`,
  ajenas; +2 tests nuevos).
- Arquitectura completa desde la raíz del repo: `29 failed / 534 passed`
  (línea base sin cambios; confirmado que `test_no_appcontainer_passed_to_services`
  sigue fallando por `backend/application/logistics/service.py`, sin relación
  con este cambio).
- `tests/integration/test_inventory_functional_phase8.py` (10) y
  `tests/test_fase1_uiux_refresh.py` (3) ya fallaban en la línea base por
  causas ajenas (mismatch int/str de `product_id` legacy; `modulos/productos.py`
  eliminado en el flip de Productos) — confirmado con `git stash` antes/después,
  mismo conjunto de fallas.

**Pendiente de P0-A (no cubierto por esta slice, queda para cuando existan más
comandos):** "prohibir `permissive_for_tests()` en rutas productivas" — hoy
el único comando (`generate_suggestions`) ya usa `InventoryUseCaseFactory`
cuando hay sesión viva; el resto de los `handlers` de Ventas/Producción/Compras
que instancian casos de uso directamente (P0-07) es un hallazgo aparte, fuera
del alcance de "sesión y composition root del shell de Inventario" — se
abordará junto con P0-E (integración entre módulos) o en una slice dedicada.

### Slice 2 — P0-B/C: página piloto Cuarentena — liberar/disponer — HECHO

**Por qué Cuarentena y no Ajustes:** `ReleaseQuarantineUseCase`/
`DisposeQuarantineUseCase` solo necesitan el `id` de una cuarentena ya
existente (visible en la fila seleccionada) — cero dependencia de búsqueda de
producto. `CreateAdjustmentUseCase` (y "Poner en cuarentena", la otra mitad de
esta misma página) sí la necesitan, y el propio audit marca la búsqueda
canónica de producto como P0-D, una fase posterior. Empezar por lo que no
tiene esa dependencia evita construir un formulario con un campo de texto para
`product_id` (el defecto P0-04 que el audit señala) que P0-D tendría que
rehacer.

**Bug descubierto al conectar la fila con el comando:** `QuarantineQueryService
.list_open()` nunca seleccionaba `id` — el `row_ids` de `quarantine_table` usaba
`lot_id or product_id`, que se repiten entre cuarentenas del mismo lote/producto.
Sin el id real, ninguna acción por fila es posible (no hay forma de saber cuál
cuarentena actuar). Se agregó `id` al SELECT y al dict devuelto, y `row_ids`
ahora usa ese id.

**Archivos:**
- `backend/application/inventory/queries/quarantine_query_service.py` — `id`
  agregado al SELECT/dict de `list_open`.
- `frontend/desktop/modules/inventory/view_models.py` — `quarantine_table`
  usa `r["id"]` como `row_ids` en vez de `lot_id or product_id`.
- `frontend/desktop/modules/inventory/presenter.py` — nuevos comandos
  `release_quarantine(quarantine_id)` y `dispose_quarantine(quarantine_id,
  reason="")`, y los parámetros `release_quarantine_uc`/`dispose_quarantine_uc`
  en el constructor (mismo patrón que `generate_suggestions_uc`: si no se
  inyectan, el comando responde "no disponible" en vez de fallar).
- `modulos/inventario_enterprise.py::_build_presenter` — con sesión viva,
  construye `factory.release_quarantine()`/`factory.dispose_quarantine()`
  (autorización RBAC real); sin sesión, cae a los use cases con su default
  `permissive_for_tests()` (mismo patrón que `generate_uc`).
- `frontend/desktop/modules/inventory/dialogs.py` (nuevo) —
  `DisposeQuarantineDialog(FormDialog)`: un campo de motivo (auditado por
  `DisposeQuarantineUseCase`), siguiendo el mismo patrón que
  `ReversalDialog` en Finanzas.
- `frontend/desktop/modules/inventory/pages/quarantine_page.py` — dos botones
  ("Liberar" / "Disponer", `create_secondary_button`/`create_danger_button`)
  gateados por `StandardTable.selected_row_id()`; "Liberar" confirma con
  `ConfirmationDialog`, "Disponer" abre `DisposeQuarantineDialog` (irreversible,
  requiere motivo); ambos llaman al presenter, muestran el resultado con
  `QMessageBox` y refrescan la tabla solo si la operación tuvo éxito.

**El patrón que queda de plantilla para las demás páginas** (tal como pide el
audit): Página (botón + selección de fila) → Diálogo de confirmación/formulario
→ Presenter (comando) → Caso de uso autorizado (`InventoryUseCaseFactory`) →
UoW → Ledger/movimiento de estado + Outbox → (evento — el refresco reactivo
por evento es P1, aquí el refresco es manual post-éxito) → tabla actualizada.

**Evidencia:**
- `tests/integration/inventory/test_inventory_ui_presenter.py`: 8 tests nuevos
  — `TestQuarantineCommands` (release/dispose exitosos con flujo real
  `QuarantineStockUseCase` → presenter → `quarantines()` vacío después;
  ambos comandos rechazan sin selección sin tocar el backend; ambos responden
  "no disponible" si no se inyectó el use case) + `TestPagesSmoke` (clic en
  "Liberar" con fila seleccionada llama al presenter real y la tabla queda en
  0 filas sin necesidad de refresh() manual; sin selección, advierte y NUNCA
  llama al presenter — verificado con `unittest.mock.patch.object`). Además
  `test_quarantines_view_model` ahora confirma que `row_ids[0]` es el id de la
  cuarentena, no el lote. **50 passed** (era 42; +8 nuevos, cero regresiones).
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py`
  (de la slice P0-A) sigue en verde con los dos use cases nuevos en el
  composition root.
- Guardrails de inventario sin cambios: `test_inventory_ui_guardrails.py`
  (incluye el nuevo `dialogs.py` en el escaneo de SQL/db-access — limpio),
  `test_inventory_authorization_fail_closed.py`,
  `test_app_container_inventory_canonical_route.py`,
  `test_inventory_no_silent_pass.py`, `test_inventory_no_legacy_permissions.py`,
  `test_fase_a_identity_clean_modules.py` → **16 passed**.
- Inventario completo: `2 failed / 583 passed` (2 pre-existentes, +8 nuevos).
- Arquitectura completa desde la raíz del repo: `29 failed / 534 passed`
  (línea base sin cambios).

**Pendiente explícito de esta página** (no ítems perdidos, decisiones
documentadas): "Poner en cuarentena" (crear) difiere a P0-D por la búsqueda de
producto; el refresco reactivo por evento (`INVENTORY_QUARANTINE_RELEASED`, ya
emitido por el use case) es P1 — hoy el refresco es manual post-éxito, que es
correcto pero no reactivo ante cambios de otras pantallas/usuarios.

### Slice 3 — P0-D piloto: búsqueda canónica de producto + "Poner en cuarentena" — HECHO

Completa el ciclo abrir→liberar/disponer de la página Cuarentena (lo que la
slice 2 dejó explícitamente diferido) y, de paso, entrega el patrón
reutilizable de búsqueda de producto que el audit pide para el resto de
páginas con creación (P0-D, hallazgo P0-04: "el usuario no debería conocer ni
escribir UUIDs").

**Componente reutilizado, no reinventado:** `EntitySearchInput` (Design
System, FASE DS-4) y `ProductQueryService.search_products()` (canónico,
`backend/application/queries/product_query_service.py` — el mismo que ya usa
Productos) ya existían. Solo faltaba conectarlos a Inventario. Se siguió el
patrón exacto de `DirectPurchasePresenter.supplier_options()` (Compras): el
**presenter**, no el diálogo, hace la búsqueda — la UI nunca toca el query
service ni SQL directamente.

**Archivos:**
- `frontend/desktop/modules/inventory/presenter.py` — nuevo método de lectura
  `product_options(query)` (delega en `product_query_factory`, atrapa
  excepciones → `[]`) y nuevo comando `open_quarantine(product_id, reason,
  quantity, branch_id=None, warehouse_id=None, reason_note="")` (valida
  producto seleccionado y motivo contra el enum real `QuarantineReason` antes
  de llamar al use case — nunca deja pasar un string arbitrario). También se
  agregó `_result_data()`, un helper que pliega `result.entity_id` dentro del
  dict devuelto — los tres comandos de Cuarentena (`release_`, `dispose_`,
  `open_quarantine`) y `generate_suggestions` ahora devuelven `entity_id`
  cuando aplica, como pide el audit en la sección 18 ("resultados
  normalizados: success, message, error_code, entity_id, data").
- `modulos/inventario_enterprise.py::_build_presenter` — nuevo
  `product_query_factory=ProductQueryService.from_connection` (classmethod,
  no la clase pelada — su `__init__` no toma la conexión como primer
  posicional) y `open_quarantine_uc` (vía `factory.quarantine_stock()` con
  sesión viva, o `QuarantineStockUseCase()` default en pruebas).
- `frontend/desktop/modules/inventory/dialogs.py` — `OpenQuarantineDialog`:
  `EntitySearchInput` (producto), `QComboBox` con motivos en es-MX
  (`QUARANTINE_REASON_ES`), `DecimalInput` (cantidad) y nota opcional.
- `frontend/desktop/modules/inventory/pages/quarantine_page.py` — botón
  "Nueva cuarentena"; valida producto seleccionado y cantidad > 0 en la propia
  página (el `FormDialog` base no valida por sí solo) antes de llamar al
  presenter.

**Limitación explícita de esta slice (documentada, no un descuido):**
`open_quarantine` no recibe `location_id` — no hay selector de ubicación
todavía en esta página. `QuarantineStockUseCase` cae a `warehouse_id` como
ubicación cuando no se especifica una, así que esta acción solo encuentra
saldo disponible si el stock vive exactamente en esa ubicación por defecto
(el caso común en almacenes sin desglose de ubicaciones). Un selector de
ubicación real es un follow-up de P0-D, no de esta slice.

**Bug atrapado en el propio proceso de escribir el test de extremo a extremo:**
el primer intento de test sembraba stock en `to_location_id="loc1"` (una
ubicación arbitraria) mientras `open_quarantine` (sin location_id) resuelve a
`warehouse_id="w1"` — el use case devolvía correctamente `"Inventario negativo
no permitido"` porque, en efecto, no había saldo en esa ubicación. Sirve como
confirmación en vivo de la limitación de arriba, no como fallo del código.

**Hallazgo operativo (afecta cómo se deben escribir tests de diálogos Qt en
adelante, no un bug de producto):** al mockear `exec_()` de un diálogo con una
función simple en vez de dejar que el flujo de error real llegara a un
`QMessageBox.warning` **sin mockear**, la prueba quedó colgada indefinidamente
bajo `QT_QPA_PLATFORM=offscreen` (un `QMessageBox` modal real nunca recibe la
interacción que necesita para cerrarse, y no hay timeout). Se resolvió
mockeando también `.warning` y aserting que no se llamó — pero además cambia
la práctica recomendada: **toda prueba de una página Qt en este módulo debe
mockear tanto `QMessageBox.information` como `.warning`**, nunca solo una,
independientemente de qué rama se espere ejercitar.

**Evidencia:**
- `tests/integration/inventory/test_inventory_quarantine_open.py` (10, nuevo):
  `TestProductOptions` (busca por nombre, por código, sin match, sin wiring);
  `TestOpenQuarantine` (crea cuarentena visible; usa branch/warehouse de la
  sesión, nunca fabricados; rechaza sin producto sin tocar backend; rechaza
  motivo inválido; responde "no disponible" sin wiring); `TestQuarantinePageOpenAction`
  (clic real en "Nueva cuarentena" con producto+cantidad capturados crea la
  cuarentena y refresca la tabla — sin colgarse, con ambos QMessageBox
  mockeados).
- `tests/integration/inventory/test_inventory_ui_presenter.py` (50) y
  `test_inventory_enterprise_session_wiring.py` (2) sin cambios.
- Inventario completo: `2 failed / 593 passed` (2 pre-existentes, +10 nuevos).
- Arquitectura completa desde la raíz del repo: `29 failed / 534 passed`
  (línea base sin cambios).

### Slice 4 — P0-C (Ajustes) — fixes de fondo, pausado antes de la UI — HECHO (parcial)

Se empezó a repetir el patrón de Cuarentena en la página de Ajustes
("Aprobar/Postear/Reversar" según §7.15 del audit) y, al llegar al mismo punto
donde la fila necesita un id real para operar sobre ella, se encontró el
**mismo bug exacto de Cuarentena (slice 2)**: `AdjustmentQueryService
.list_recent()` no seleccionaba `id`, y `adjustments_table()` usaba
`f"{folio}:{índice}"` como `row_id` — inútil para llamar a
`ApproveAdjustmentUseCase`/`PostAdjustmentUseCase`/`ReverseAdjustmentUseCase`,
que requieren el UUID real del ajuste. Se corrigió igual que en Cuarentena.

También se encontró que `InventoryUseCaseFactory` (el composition root)
**importaba pero nunca exponía** `ReverseAdjustmentUseCase` como builder —
`create_adjustment`, `approve_adjustment` y `post_adjustment` sí tenían su
método, `reverse_adjustment` no. Sin ese builder, la UI no podría construir el
caso de uso de reverso con el checker RBAC real (tendría que usar el
constructor permisivo, justo lo que P0-A prohíbe). Se agregó el import y el
builder que faltaba.

El usuario interrumpió con "P0-E" antes de completar el resto (comandos del
presenter, diálogos, botones de la página) — se dejaron esos dos fixes de
backend confirmados y probados como una mejora autónoma y segura, y el resto
de P0-C (Ajustes) queda pendiente explícito para retomar.

**Archivos:**
- `backend/application/inventory/queries/adjustment_query_service.py` — `id`
  agregado al SELECT/dict de `list_recent`.
- `frontend/desktop/modules/inventory/view_models.py` — `adjustments_table`
  usa `r["id"]` como `row_ids`.
- `backend/application/inventory/composition.py` — import de
  `ReverseAdjustmentUseCase` + builder `reverse_adjustment()`.
- `tests/unit/inventory/test_inventory_composition.py` — nuevo
  `test_factory_builds_reverse_adjustment`.
- `tests/integration/inventory/test_inventory_ui_presenter.py` —
  `test_adjustments_view_model` ahora confirma `row_ids[0] ==
  result.entity_id`.

**Evidencia:** inventario `2 failed / 594 passed` (2 pre-existentes, +1
nuevo); arquitectura `29 failed / 534 passed` (línea base sin cambios).

**Pendiente explícito para retomar P0-C (Ajustes):** presenter —
`create_adjustment` (folio + producto vía `product_options` + motivo +
cantidad con signo, una sola línea por envío como en Cuarentena),
`approve_adjustment`, `post_adjustment`, `reverse_adjustment` (con motivo);
composition root — wireado vía `factory.create_adjustment()` etc.; página —
botones "Nuevo ajuste"/"Aprobar"/"Postear"/"Reversar" con diálogos
(reutilizando `OpenQuarantineDialog`/`DisposeQuarantineDialog` como plantilla).
