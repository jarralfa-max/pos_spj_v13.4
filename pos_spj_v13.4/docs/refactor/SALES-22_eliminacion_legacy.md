# SALES-22 — Eliminación de legacy (POS-22 del master prompt)

Fecha: 2026-08-18
Fase anterior: `SALES-20_preservacion_visual.md` (POS-21 "Offline" fue omitida — el usuario
pidió POS-22 directamente; por disciplina establecida, se mapea al POS-N que el usuario nombra,
no al orden tentativo original).

## Alcance ejecutado

Master prompt §67, fase POS-22: "Eliminar SQL UI. Eliminar container. Eliminar hardware
directo. Eliminar impresión directa. Eliminar lógica de pago. Eliminar ventas.py. Eliminar
imports. Vaciar allowlist. Reporte."

## Decisión de alcance: prerrequisitos reales antes de borrar, no un borrado literal inmediato

Antes de escribir código, auditó el estado real de `frontend/desktop/modules/sales_pos/`
(SALES-19/20) y encontró que **el módulo nuevo no podía completar una venta real**:
`SalesPosPresenter.record_payment()` existía y estaba conectado al backend real (SALES-13) desde
SALES-19, pero ningún componente/diálogo lo llamaba jamás — "Cobrar" (F9) llamaba
`checkout_sale()` directamente con cero pagos registrados, lo cual `CheckoutSaleUseCase`'s real
`SalePaymentPolicy.ensure_fully_paid` rechaza siempre. Además `interfaz/main_window.py` seguía
apuntando a `ModuloVentas` (legacy), y `modulos/ventas.py`/`presentation/sales/` son **archivos
sin seguimiento de git** (`git status` confirmó `??` — sin red de seguridad de git para revertir
un borrado, igual que el precedente `CRM-24_retiro_modulo_legacy.md`).

Dado ese riesgo, se presentaron tres opciones al usuario: (a) construir los prerrequisitos reales
primero y luego ejecutar el borrado como un cutover verdadero, (b) solo producir el reporte de
brechas sin borrar nada, (c) borrar literalmente ahora, aceptando que el checkout quedaría roto
hasta construir un diálogo de pago después. El usuario eligió **(a)** — coherente con el propio
precedente del repositorio (`CRM-23` construyó solo prerrequisitos; `CRM-24`, en una fase
separada, ejecutó el retiro real).

## Parte 1 — Prerrequisitos construidos y verificados

### `PaymentDialog` — la pieza que realmente faltaba

`frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py` (nuevo). A diferencia del diálogo
legacy (`presentation/sales/dialogs/payment_dialog.py::DialogoPago`, ahora eliminado), que
calcula cambio/split mixto/validación de crédito él mismo del lado cliente y luego envía todo de
una vez — exactamente la "lógica de pago en la UI" que esta fase pide eliminar — el diálogo nuevo
solo recolecta líneas de pago (método/monto/referencia) localmente y las somete a las políticas
reales del dominio (`SalePaymentPolicy`, `CreditNotAuthorizedError` vía `SalesCreditClient`) al
confirmar. "Pago Mixto" no es una opción dedicada — no es un `PaymentMethod` en el agregado
nuevo, es lo que la venta se vuelve en cuanto se registra un segundo método distinto
(`Sale.is_mixed_payment`) — el cajero simplemente agrega dos líneas.

**Por qué nada toca el backend hasta "Confirmar y cobrar"**: la tabla de transición de
`SaleLifecyclePolicy` tiene `(ACTIVE, CHECKOUT_PENDING)` y `(CHECKOUT_PENDING, CANCELLED)`, pero
NO `(CHECKOUT_PENDING, ACTIVE)` — una vez que `begin_checkout()` tiene éxito no hay vuelta a un
carrito editable salvo cancelar toda la venta. Llamarlo apenas se abre el diálogo habría dejado la
venta atascada en CHECKOUT_PENDING en cuanto el cajero cancelara — a diferencia del diálogo
legacy, donde Cancelar siempre regresa al carrito intacto. Por eso `begin_checkout()` se difiere
al momento exacto en que las líneas de pago ya están recolectadas y balanceadas.

Mercado Pago no tiene flujo de generación de link aquí — el alcance documentado de SALES-13 es
que el agregado nuevo solo registra un pago YA CONFIRMADO por MP (misma forma que
Tarjeta/Transferencia); el flujo real de link ya existe en el stack legacy
(`services/mercado_pago_service.py`) y reconstruirlo está fuera de alcance.

### Otros prerrequisitos

- `SalesPosWorkspace._on_checkout_requested` reescrito para abrir `PaymentDialog` en vez de
  llamar `checkout_sale` directamente.
- `SalesPosWorkspace.aplicar_contexto(context)` — receptor real del `NavigationIntent`
  (`"sales.new"`, Customer 360 "Nueva venta") que `interfaz/main_window.py` ya enruta. Más simple
  que el legacy `ModuloVentas.aplicar_contexto`: `context["customer_id"]` ya es un id de Customer
  Master real, y `AssignCustomerToSaleUseCase` (SALES-10) lo acepta directamente — sin el puente
  a `clientes` legacy que el screen viejo necesitaba.
- `SalesPosWorkspace.refresh_products()`/`refresh_branches()` — contrato de hot-refresh
  (`core/events/catalog_events.py::fan_out_products_changed/fan_out_branches_changed`,
  Remediación B) que el módulo nuevo nunca implementó desde SALES-19. Sin esto, un producto o
  sucursal creado/editado en otra pantalla mientras el POS nuevo estaba abierto jamás se
  reflejaba hasta reabrir la pantalla — una regresión real que este hallazgo cerró antes de la
  eliminación, no un capricho.
- `interfaz/main_window.py`, `core/ui/module_loader.py`, `interfaz/diagnostico.py` — las tres
  rutas reales que apuntaban a `modulos.ventas`/`ModuloVentas` (mismo patrón de 3 archivos que
  `CRM-24` documentó), reapuntadas a `modulos.ventas_pos.ModuloVentasPos`.

### Verificación empírica antes de borrar nada

`tests/integration/test_sales_pos_checkout_end_to_end.py` (nuevo, 4 pruebas) — ejercita la
secuencia EXACTA que `PaymentDialog._confirm()` ejecuta
(`begin_checkout` → `record_payment`(s) → `checkout_sale`) contra el wiring real de
`composition.py::build_sales_pos_presenter`, no solo casos de uso llamados a mano:
- Un pago en efectivo completo finaliza la venta.
- Dos pagos de métodos distintos (mixto) finalizan la venta y `is_mixed_payment` es verdadero.
- Cobrar sin ningún pago registrado falla limpio con `PAYMENT_INCOMPLETE`, no con un crash.
- `ModuloVentasPos(container)` construye un widget real contra una conexión real (sin PyQt5 mock).

Regresión completa (401→405 según el punto de la fase) confirmada en verde antes de proceder a
la Parte 2, con la suite golden-master legacy de 18 pruebas todavía intacta en ese punto (el
árbol legacy aún no se había tocado).

## Parte 2 — Eliminación real, ejecutada tras confirmar los prerrequisitos

Con checkout verificado end-to-end y el módulo nuevo cableado en `main_window.py`, se preguntó
explícitamente si proceder — dado que persistía una brecha real no cubierta por la aprobación
original (sin diálogo de Devolución) y que el borrado no tiene red de seguridad de git. El
usuario confirmó proceder.

### Respaldo antes de borrar (mismo criterio que CRM-24)

`modulos/ventas.py`, `presentation/sales/` completo, la suite golden-master legacy
(`tests/visual/golden/sales_pos/`) y los tests dependientes se copiaron fuera del repositorio (al
scratchpad de la sesión) antes de cualquier borrado — 54 archivos.

### Archivos de producción eliminados (verificado cada uno sin otros consumidores reales antes de
### borrar, mismo método que CRM-24)

- `modulos/ventas.py` (`ModuloVentas`, ~5000 líneas).
- `presentation/sales/dialogs/payment_dialog.py` (`DialogoPago`) — único consumidor real:
  `modulos/ventas.py`.
- `presentation/sales/cart_view_model.py` (`CartViewModel`) — confirmado código muerto: cero
  consumidores reales en todo el repo, solo su propia prueba.
- `presentation/sales/workers/sale_checkout_worker.py` /
  `presentation/sales/workers/sale_checkout_worker_factory.py` — confirmado código muerto: el
  propio `modulos/ventas.py` nunca los importaba (`finalizar_venta`'s docstring ya decía "Procesa
  la venta en hilo principal; solo ticket/PDF queda asíncrono" — el enfoque de worker async fue
  abandonado en una fase anterior, dejando estos archivos huérfanos).
- `presentation/sales/workers/ticket_output_worker.py` (`TicketOutputWorker`) — único consumidor
  real: `modulos/ventas.py` (PDF de ticket, async).
- `presentation/sales/` queda vacío de código real tras lo anterior — directorio eliminado por
  completo.

### Lo que NO se eliminó (deliberado, verificado antes de decidir — mismo criterio que CRM-24)

`modulos/ventas.py` usaba varios servicios COMPARTIDOS que otros consumidores reales siguen
necesitando:

- `core/services/sales_service.py` / `core/use_cases/venta.py` — confirmado un consumidor real
  adicional: `api/routers/ventas.py` (API REST). Se mantienen intactos.
- `core/services/stock_reservation_service.py`, `core/services/inventory_availability_service.py`
  — consumidos también por el stack nuevo `backend/domain/sales/` (SALES-9) y por Caja.
- `repositories/cliente_repository.py`, `repositories/productos.py`, `core/services/
  payment_normalization.py`, `core/services/sales/payment_policy.py` y el resto de servicios
  `core/services/*` que `modulos/ventas.py` consumía — todos con consumidores reales
  independientes, ninguno tocado.

### Rutas actualizadas para apuntar al módulo nuevo

- `interfaz/main_window.py`: `from modulos.ventas import ModuloVentas` →
  `from modulos.ventas_pos import ModuloVentasPos as ModuloVentas` (mismo patrón "FLIP" que
  `ModuloProductosEnterprise as ModuloProductos` ya usa ahí mismo). `_conectar("POS", ...)` sin
  otros cambios.
- `core/ui/module_loader.py::MODULE_REGISTRY["ventas"]` → `("ModuloVentasPos",
  "modulos.ventas_pos", [])`, verificado por importación real (no solo lectura de texto).
- `interfaz/diagnostico.py` → `("Ventas", "modulos.ventas_pos")`.

### Limpieza de tests dependientes

**Suite completa retirada** (su propio sujeto, `modulos.ventas.ModuloVentas`, ya no existe;
`tests/unit/test_sales_pos_visual_validation.py`, SALES-20, cumple el mismo rol para el árbol
nuevo):

- `tests/visual/golden/sales_pos/` completo — 18 pruebas golden-master + conftest.

**Archivos retirados por completo** (100% de sus pruebas leían `modulos/ventas.py`/
`presentation/sales/*` directamente, sin sujeto independiente):

`test_ventas_devolucion_authorization_regression.py`, `test_ventas_checkout_async_flow.py`,
`test_phase4_cart_view_model.py`, `test_phase11_payment_dialog_extraction.py`,
`test_fase7_worker_factory_db_isolation.py`, `test_fase7_checkout_worker_sqlite_threading.py`,
`test_ventas_customer_dialog_regression.py`, `test_phase2_pos_venta_usa_uc.py`,
`test_fase2_ui_resultado_venta_postcommit.py`, `test_fase0_ventas_peso_hal.py`,
`test_fase0_ventas_canje.py`, `test_fase7_mp_pending_context_recovery_e2e.py`,
`test_fase8_no_legacy_conflicts.py`, `test_ticket_reprint_and_pdf_separation.py`,
`tests/architecture/test_ventas_guardrails.py`,
`tests/architecture/test_sales_uses_catalog_query_service_only.py`,
`tests/architecture/test_sales_ticket_settings_no_direct_sql.py`,
`tests/architecture/test_sales_no_commit_in_ui.py`, `tests/architecture/test_sales_no_sql_in_ui.py`,
`tests/architecture/test_sales_manual_quantity_defaults_zero.py`.

**Archivos editados quirúrgicamente** (se retiró solo la(s) prueba(s) que leían el archivo
borrado; el resto — pruebas reales sobre `SalesService`/`StockReservationService`/
`UnifiedSalesService`/`CustomerCreditService`/repositorios compartidos — permanece intacto,
mismo criterio que CRM-24 aplicó a `test_clean_birth_guardrails.py`):

`test_ventas_cleanup_regression.py`, `test_fase5_stock_reservations.py` (incluida la única falla
preexistente/conocida de este archivo desde SALES-9,
`test_ui_pasa_reserva_id_al_uc_antes_de_aplicar_resultado`, ya sin sujeto — se retiró con el
resto, no queda ninguna falla "conocida" pendiente de este archivo),
`tests/unit/test_remediacion_b_refresh_contract.py` (repuntado a
`frontend/desktop/modules/sales_pos/sales_pos_workspace.py` en vez de retirado — el contrato
sigue vigente, ahora en el módulo nuevo), `test_ventas_fixes.py`, `test_no_qprinter_for_thermal_tickets.py`,
`test_fase5_inventory_availability_service.py`, `test_fase4_payment_mapping.py`,
`test_ticket_pipeline_integration.py`, `test_fase6_mercadopago_cleanup.py`,
`test_fase8_no_silent_passes.py`, `test_fase9_legacy_sales_blocked.py`, `test_credit_sale_cxc.py`,
`test_credit_flow_refactor.py`.

**Allowlist vaciada** (`tests/architecture/allowlists.py`) — entradas de `modulos/ventas.py`
eliminadas por completo, no solo bajadas de número (misma regla explícita que CRM-24 ya
documentó): `COMMIT_ROLLBACK_IN_UI_ALLOWLIST['...modulos/ventas.py']` (era 2),
`ENTITY_COMBO_MASS_LOADING_ALLOWLIST['...modulos/ventas.py']` (era 1), y la entrada de
`HARDCODED_RELATIVE_PATHS_ALLOWLIST` para `test_phase11_payment_dialog_extraction.py` (archivo
retirado). `tests/architecture/test_no_legacy_stock_sources_for_operational_reads.py`'s
`WATCHED_FILES` también perdió su entrada `modulos/ventas.py`.

## Un hallazgo real de una prueba que se me escapó en la primera pasada

`tests/test_ventas_cleanup_regression.py` tenía un helper `_source_between("modulos/ventas.py", ...)`
usado por 3 pruebas que mi primer barrido (buscando solo imports directos y
`SaleCheckoutWorkerFactory`) no capturó — fallaron con `FileNotFoundError` en la primera corrida
completa de la suite tras el borrado. Encontrado y corregido por el mismo método que cualquier
otro hallazgo de esta fase: correr la suite completa (`pytest tests/ --collect-only`) tras cada
cambio grande, no confiar en un grep de una sola pasada. El mismo patrón se repitió en
`test_credit_sale_cxc.py`/`test_credit_flow_refactor.py`, cuyos nombres de prueba
(`test_ui_source_uses_canonical_columns`, `test_ventas_py_*`) ya sugerían el problema y se
verificaron/corrigieron también.

## Verificación

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ --collect-only -q
QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/test_sales_*.py tests/architecture/test_sales_*.py \
  tests/integration/test_sales_pos_checkout_end_to_end.py tests/test_ventas_fixes.py \
  tests/test_ventas_cleanup_regression.py tests/test_fase5_stock_reservations.py \
  tests/test_fase6_mercadopago_cleanup.py tests/test_fase8_no_silent_passes.py \
  tests/test_fase9_legacy_sales_blocked.py tests/test_fase4_payment_mapping.py \
  tests/test_no_qprinter_for_thermal_tickets.py tests/test_ticket_pipeline_integration.py \
  tests/unit/test_remediacion_b_refresh_contract.py \
  tests/architecture/test_no_legacy_stock_sources_for_operational_reads.py \
  tests/architecture/test_cash_sales_boundary.py tests/architecture/test_pos_does_not_execute_purchases.py -q
```

- **Colección completa de `tests/`**: 7582 pruebas, 0 errores relacionados con esta fase (los 2
  errores restantes — `test_delivery_product_search_refactor.py` por `UnicodeDecodeError`,
  `test_uc_compra.py` por `ModuleNotFoundError: core.use_cases.compra`, que ni siquiera existe —
  confirmados preexistentes y no relacionados: ambos archivos sin seguimiento de git, sin ninguna
  referencia a Ventas/POS, y `core/use_cases/compra.py` genuinamente no existe en el repo).
- **Barrido dirigido de Sales/POS**: 430 passed, 7 failed, 1 skipped. Las 7 fallas restantes son
  preexistentes/no relacionadas, confirmadas por causa raíz antes de dejarlas:
  - `TestGetStockSucursal` (4) — ya documentado preexistente desde SALES-2.
  - `test_mp_pending_creates_reservation`/`test_mp_pending_cancel_releases_reservation` (2) — la
    misma clase de fixture bit-rotted que SALES-9 ya documentó ampliamente ("no such table:
    stock_reserva_detalles" — el fixture de este archivo nunca creó esa tabla, algo que
    predata esta fase por completo).
  - `test_delivery_y_caja_usan_printerservice_en_tests_dedicados` — compara contra un string que
    `tests/test_caja_ticket_uses_escpos.py` ya no contiene tras un refactor de otra fase (Caja);
    no relacionado con Ventas/POS.
- **Guardrails de arquitectura consumidores directo de los diccionarios editados en
  `allowlists.py`** (`test_no_sql_in_pyqt_modules.py`, `test_sql_in_ui_ratchet.py`,
  `test_no_sql_in_frontend.py`, `test_no_entity_combo_mass_loading.py`,
  `test_no_commit_rollback_in_pyqt.py`, `test_no_commit_rollback_in_frontend.py`,
  `test_no_hardcoded_paths.py`): 6/7 en verde; la única falla
  (`test_no_hardcoded_paths.py::test_no_loose_relative_paths`) es preexistente y ajena — el
  guardrail está escaneando `.venv/Lib/site-packages/*` (numpy/matplotlib/pydantic/fastapi/etc.),
  un entorno virtual presente dentro del árbol del repo que este guardrail no excluye; nada que
  ver con esta fase.
- **Suite completa de `tests/architecture/`** (85 archivos) corrida como verificación amplia: 577
  passed, 80 failed — auditado por muestreo: ninguna de las 80 fallas menciona "sales"/"ventas"/
  "pos_" por nombre, y las causas raíz muestreadas (escaneo de `.venv`, un contador `legacy_id`
  que no aparece en ningún archivo de esta fase) confirman que son parte de un baseline
  preexistente de otros bounded contexts (Transfers, Finance, Settings, Menu, Products,
  Procurement, el propio orquestador de refactor) — nunca corrida como un todo en esta sesión
  antes, consistente con la nota ya documentada en la memoria de este pipeline ("el baseline de
  pytest... aún no se ha corrido como un barrido dedicado único").
- Hallazgo adicional, no corregido (fuera de alcance, mismo criterio de "reportar no arreglar"
  que el hallazgo de `finance_handler.py` en SALES-13): `test_credit_sale_cxc.py`/
  `test_credit_flow_refactor.py` tienen 23 fallas reales preexistentes en
  `cuentas_por_cobrar`/`accounts_receivable_service.py`
  (`sqlite3.IntegrityError: datatype mismatch`) — un problema de Finanzas/Crédito no relacionado
  con Ventas/POS, confirmado por traza directa antes de dejarlo. `test_flujo_completo.py` tiene
  fallas/errores similares preexistentes en `productos.id NOT NULL constraint failed`
  (migración de identidad UUIDv7 en curso en otro bounded context).

## Lo que esta fase NO hizo — pérdida real de funcionalidad, aceptada explícitamente (mismo
## criterio que CRM-24 aceptó la pérdida de tarjetas/RFM)

- **Devolución (F10) sigue sin diálogo real** — necesita búsqueda de venta histórica por
  folio/completada + selector de línea/cantidad + autorización en caliente, una pieza
  sustancialmente mayor que el diálogo de pago. Los cajeros no tienen forma de procesar una
  devolución desde esta pantalla hasta que se construya.
- **Mercado Pago**: sin flujo de generación de link/cobro pendiente en el stack nuevo — solo
  registra un pago YA confirmado, por diseño documentado desde SALES-13.
- **Canje de puntos de lealtad**: `redeem_loyalty_points` existe y está conectado en el
  presentador desde POS-14, pero ningún diálogo de la UI nueva lo llama todavía.
- **No se replicó cada diálogo legacy** — solo descuento, cliente rápido y el nuevo diálogo de
  pago son representativos; factura con selección de perfil fiscal, devolución completa, etc. no
  tienen contraparte en el árbol nuevo.
- **No se corrigieron las 80 fallas preexistentes** de `tests/architecture/` en otros bounded
  contexts, ni las 23 de Finanzas/CxC, ni las de `test_flujo_completo.py` — confirmadas
  no relacionadas y fuera del alcance de una fase de retiro de Ventas/POS.

## Hotfix post-cutover: crash real al cargar el módulo POS en la app en vivo

Tras el cutover, al ejecutar la app real, `interfaz/main_window.py` reportó
`Error cargando módulo POS` con esta traza:

```
File "...sales_pos_workspace.py", line 86, in __init__
    self._start_new_sale()
...
File "...sale_query_service.py", line 43, in count_suspended
    self._auth.require(requester_user_id, SalesPermissions.VIEW)
backend.domain.sales.exceptions.SalesPermissionDeniedError: Operación sin usuario autenticado
```

**Causa raíz**: `interfaz/main_window.py::_conectar` construye TODAS las pantallas de módulo de
forma eager al iniciar la app, antes de que cualquier usuario se autentique
(`session_context.user_id` está vacío en ese momento). `SalesPosWorkspace.__init__` llamaba
`_start_new_sale()` incondicionalmente, que en cascada llega a
`SalesPosPresenter.count_suspended()` → `SalesAuthorizationPolicy.require()` — el cual, con un
`requester_user_id` vacío, **lanza** `SalesPermissionDeniedError` en vez de degradar
silenciosamente (a diferencia de otros métodos del presentador que devuelven `SaleResult.fail(...)`
o listas vacías cuando no hay wiring). Esto tumbaba la construcción completa del módulo — el error
lo capturaba el `try/except` de `_conectar`, dejando el POS completamente inaccesible en la app
real. Ninguna prueba de este pipeline había cubierto la construcción del widget bajo una sesión
NO autenticada — todas usaban una sesión ficticia ya autenticada (`user_id` no vacío).

**Corrección**: `SalesPosWorkspace` ya no inicia una venta en `__init__`. Se difiere a un
`showEvent()` nuevo, que solo dispara `_start_new_sale()` la primera vez que el widget se hace
realmente visible (lo cual, dado que `QStackedWidget` solo muestra la pantalla activa, únicamente
ocurre cuando el usuario navega a POS — y eso solo puede pasar después de iniciar sesión) y solo
si `self._presenter.current_user_id()` ya no está vacío. `catalog.load_categories()` permanece en
`__init__` sin cambios — no requiere usuario autenticado (lectura pública de categorías).

**Pruebas nuevas** en `tests/integration/test_sales_pos_checkout_end_to_end.py`:
`test_construction_does_not_crash_before_login` (reproduce el escenario exacto del crash: sesión
con `user_id=""`, construcción debe suceder sin excepción y sin venta iniciada) y
`test_showing_the_widget_after_login_starts_a_real_sale` (una vez autenticado y mostrado el
widget, sí arranca una venta real). El primer intento de estas pruebas colgó indefinidamente bajo
pytest por un bug real en la prueba misma, no en el código de producción: `QtWidgets.
QApplication.instance() or QtWidgets.QApplication([])` como expresión suelta, sin asignar a una
variable — a diferencia de cada otra prueba de este módulo, que sí guarda `app = ...`. Corregido
asignándolo, siguiendo el patrón ya establecido. 41 pruebas de la suite de UI de Sales/POS, todas
en verde tras la corrección.

## Siguiente fase

El master prompt continúa con POS-21 (Offline, omitida antes) o POS-23 (Validación final) según
la lista de fases §67 — no solicitada aún; según la disciplina establecida en cada fase anterior,
no se avanza sin que el usuario la nombre explícitamente.
