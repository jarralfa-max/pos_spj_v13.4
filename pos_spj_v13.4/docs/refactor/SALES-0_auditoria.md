# SALES-0 - Auditoria de realidad del bounded context Ventas/POS

Fecha: 2026-08-16
Alcance: `modulos/ventas.py`, `presentation/sales/`, `backend/domain/` (sales), `backend/application/` (sales),
`backend/infrastructure/db/repositories/sales_read_repository.py`, `core/use_cases/venta.py`,
`core/services/sales_service.py`, `core/services/sales/`, `core/services/sales_reversal_service.py`,
`core/services/stock_reservation_service.py`, `core/services/printer_service.py`, `hardware/*.py`,
`core/security/permission_catalog.py`, tests relacionados.

> **FASE 0 — solo lectura.** Este documento mapea realidad contra el master prompt de 73 secciones
> (Ventas/POS bounded context, POS-0..POS-23). No se cambio codigo.

---

## Veredicto FASE 0

Ventas/POS **no es** hoy un bounded context DDD. Es un modulo UI-heavy (`modulos/ventas.py`, ~4989
lineas) que ya paso por una limpieza quirurgica previa (docs `VENTAS_*`, 2026-05-27/28: dedupe de
rutas de calculo, bloqueo de escrituras legacy, fix de bugs de ticket/fidelidad/reserva) pero que
nunca recibio el tratamiento completo que Caja (`CASH-0..CASH-25`) y Clientes/CRM (`CRM-0..CRM-42`)
ya recibieron en este mismo repositorio.

`docs/refactor/refactor_state.json` y `docs/refactor/MODULE_QUEUE.md` marcan `VENTAS: DONE`, pero
ese "DONE" pertenece al pipeline mas antiguo y mas angosto de `SPJ_REFACTOR_SKILL.md` — su propio
reporte vinculado, `docs/refactor/modules/ventas.md`, lo dice explicitamente: solo se completo
"Fase A" (quitar casts `int()` de identidad, quitar defaults `sucursal=1`, extraer 6 SELECT de la UI
a `sales_read_repository.py`); su seccion "Pendiente" declara abierta la "Fase B: identidad de
escritura del sales service (`lastrowid`) + esquema TEXT". Es el mismo patron de "DONE angosto" ya
documentado para CRM en memoria — confirmado por lectura directa, no asumido.

Este documento abre una pipeline nueva y propia, `SALES-N`, paralela y con la misma disciplina que
`CASH-N`/`CRM-N`/`TRF-N`: fases numeradas, un `docs/refactor/SALES-N_<tema>.md` por fase, guardrails
de arquitectura que solo se endurecen, y **cero perdida de logica de negocio** (CLAUDE.md Prioridad
0). El master prompt de 73 secciones es la estrella polar; no se implementa en un solo golpe.

---

## Baseline no ejecutado

No se corrio `pytest` en esta fase (auditoria de solo lectura). Se inventariaron ~35+ archivos de
test relacionados a ventas/sale (ver seccion "Inventario actual por capas > Tests"). **Primera accion
obligatoria de SALES-1**: correr `python -m pytest tests/ -k "sale or venta" -v` para establecer el
baseline real antes de tocar cualquier linea, siguiendo el mismo protocolo que CASH-00.

---

## Contrato visual — estado actual (mapeo contra la seccion 1 del master prompt)

`modulos/ventas.py::init_ui` (lineas 1447-2075) ya produce, en la practica, casi exactamente el
layout de dos paneles que el master prompt exige preservar:

| Zona | Contenido real (orden) | Match vs. contrato |
|---|---|---|
| Barra superior (`cashier_bar`, 1454-1492, 48px fijo) | Titulo, `_lbl_cashier_meta` (vacio, nunca se llena con nombre de cajero), badge estatico "● Abierto", boton "⚖ Báscula", boton "💳 Terminal", boton "📋 Corte Z" → `_ir_a_caja()` | Parcial. El badge de estado no esta atado a `finance_service.get_estado_turno`; es texto estatico. El boton "Terminal" esta **re-propuesto cosmeticamente** (1326-1331, 1372-1373) para mostrar el nombre de sucursal, no el estado real de un terminal de pago. |
| Panel izquierdo (1505-1628) | Busqueda + scanner, badge de estado de scan, categorias (pills), selector de vista (lista deshabilitada, "próximamente"), grid de productos con `ProductCard` (colores por stock: agotado/critico/bajo, 174-190) | Coincide con el contrato casi 1:1. |
| Panel derecho (1635-2065) | Header carrito → tabla carrito (7 cols) / estado vacio → seccion cliente (nombre, puntos, telefono, "Cambiar") → tarjeta de totales (Subtotal, Descuento, IVA, TOTAL con mini-tarjetas de bascula/puntos-a-ganar/comision) → banner sin-impresora → botones descuento rapido (5/10/15/20/Personalizado) → **COBRAR** (F9, dominante, ancho completo, verde) → Suspender(F6)/Reanudar(F7)/Cancelar(F8) → Devolución(F10)/Factura(F11)/Reimpr.(F12) | Coincide 1:1, incluyendo los atajos F6-F12 y la dominancia visual de Cobrar. |

**Veredicto:** el layout es un candidato **REUSE** directo — es exactamente lo que la Regla Visual
No Negociable (seccion 1 del master prompt) pide conservar. El trabajo de SALES-N no es rediseñar
esto; es re-cablear sus bindings (estado de turno real, terminal real) y mover cada handler a
Presenter/UseCase sin mover un pixel.

---

## Inventario actual por capas

### UI (`modulos/ventas.py`)

Logica de negocio todavia embebida en la ventana (clasificacion REWRITE — pertenece a
`application/sales/use_cases` + `domain/sales/policies`):

| Concern | Metodo / lineas | Detalle |
|---|---|---|
| Calculo de totales/descuento | `calcular_totales` 3590-3654 | Delega a `core.services.sales.cart_calculator.CartCalculator` (mejora real post-mayo), pero cae a una suma float inline si hay excepcion (3603-3611); la UI sigue dueña del formateo y la vista previa de puntos. |
| Gate de turno de caja abierto | `procesar_pago` 4082-4100 | Llama `container.finance_service.get_estado_turno(...)` directo y bloquea con `QMessageBox` — regla de negocio ("sin turno, no hay venta") vive en la UI. |
| Preview de fidelidad | `procesar_pago` 4103-4122 | Closure que llama `container.loyalty_service.preview_redemption` directo. |
| Validacion de credito | `procesar_pago` 4137-4228 | ~90 lineas con **tres rutas** distintas que pueden decidir si una venta a credito se permite: eligibilidad CRM advisory, `customer_credit_service.validate_credit`, y un tercer fallback (4204-4228) que re-deriva el limite/saldo via `ClienteRepository.get_by_id` inline. |
| Guardrail de venta bajo costo | `finalizar_venta` 4308-4340 | Construye DTOs `ItemCarrito` y llama `uc_venta.validar_precios_bajo_costo` desde la UI. |
| Saga de Mercado Pago pendiente | `finalizar_venta` 4257-4306 | La UI orquesta directamente `create_pending_payment_sale` → `crear_link` → `attach_pending_payment_link` → cancela carrito local. |
| Apertura de cajon, reconciliacion de puntos, armado de ticket | `_aplicar_resultado_venta` 4404+ | Abre cajon, reconcilia puntos con llamada viva a `loyalty_service.saldo()` si el payload luce no confiable (4419-4424). |

Construccion de repos/servicios directamente en el widget (la UI actua como su propio composition
root — clasificacion MOVE hacia un composition root canonico, mirror de `cash_register_factory.py`):
`ClienteRepository` (1010, 1055, 3675/3715), `StockReservationService` (1212, 1320),
`HardwareSettingsQueryService` (1214, 1322), `SalesReadRepository` (1215, 1323),
`TicketSettingsQueryService` (1216, 1324), `CreateCustomerUseCase` (1217, 1325),
`ProductCatalogQueryService` (1293), `CustomerLookupService` (1303), `CardBatchEngine` (2885),
`SalesReversalService` (4969).

SQL directo: **ninguno** queda en `modulos/ventas.py` (`Fase A` del pipeline viejo ya lo saco); el
unico `sqlite3` restante es `except sqlite3.Error as e:` (3752), un import de tipo de excepcion, no
una query.

### Dominio (`backend/domain/`)

**No existe `backend/domain/sales/`** — confirmado, a diferencia de `backend/domain/cash_register/`
o `backend/domain/crm/`, que si son bounded contexts completos.

Existe, en el `domain/` de raiz del repo (**no** `backend/domain/`, distincion importante), un
`Sale`/`SaleItem` (`domain/entities/sale.py`) y `Money` (`domain/value_objects/money.py`) **muertos**:
`producto_id: int` (FK entera, no UUID), dinero como `float` — exactamente el anti-patron que el
master prompt prohibe. Solo los referencia `domain/services/sale_domain_service.py` y
`tests/test_domain_entities.py`; **nada en la ruta de venta real los importa**. Clasificacion:
**DELETE** (o REWRITE-y-reubicar bajo `backend/domain/sales/value_objects/` si se decide conservar
el nombre de clase con semantica Decimal/UUIDv7 real) — pero no debe confundirse con avance real.

### Aplicacion (`backend/application/`)

Piezas delgadas que ya existen, todas en modo adaptador (clasificacion WRAP_TEMPORARILY — utiles
como shim de compatibilidad durante la migracion, no como destino final):

- `use_cases/create_sale_use_case.py` — pass-through puro (delega a `app_service` o `handler`, si no hay ninguno retorna `not_implemented`).
- `use_cases/cancel_sale_use_case.py` — `DelegatingUseCase`, cuerpo `pass`.
- `services/sales_application_service.py::SalesApplicationService.create()` — traduce `CreateSaleCommand` (ingles) a los DTOs legacy `DatosPago`/`ItemCarrito` de `core/use_cases/venta.py` y llama `ProcesarVentaUC.ejecutar(...)`. Su propio docstring lo confiesa: *"The existing and protected sales business flow remains in core.use_cases.venta.ProcesarVentaUC and core.services.sales_service. This service is an application-layer adapter."*
- `commands/sales_commands.py` — `CreateSaleCommand`/`CancelSaleCommand`, `items: tuple[Mapping[str, Any], ...]` (bags sin tipar, no un value object `SaleLine`).
- `infrastructure/db/repositories/sales_read_repository.py` — 5 metodos de solo lectura, todos SQL de texto sobre `ventas`/`detalles_venta` (no repository-pattern sobre un aggregate).

**La logica real de orquestacion vive en `core/`, no en `backend/application/sales/`**:
`core/use_cases/venta.py` (469 lineas: `ProcesarVentaUC`, `ItemCarrito`, `DatosPago`,
`ResultadoVenta`) y `core/services/sales_service.py` (1615 lineas: `_execute_sale_core`,
`execute_sale_result`) + `core/services/sales/` (`cart_calculator.py`, `sale_execution_result.py`,
`unified_sales_service.py`).

`presentation/sales/workers/sale_checkout_worker_factory.py::_clone_uc` (copy.copy superficial de
servicios) ya fue marcado **DELETE/BLOCK** por `VENTAS_CLEANUP_DELETE_LIST.md`; el worker asociado
esta anotado "KEEP TEMPORARILY (no usado por UI)" — incluso la pasada quirurgica previa lo considero
peligroso.

### Identidad (Regla Cero UUIDv7)

Buena noticia relativa: el esquema **ya nacio limpio en el eje TEXT-id**
(`migrations/m000_base_schema.py::_create_ventas`, 617-684): `ventas.id`, `detalles_venta.id`,
`payments.id`, `sale_refunds.id` — todos `TEXT NOT NULL PRIMARY KEY`. La generacion real usa
`new_uuid()` (UUIDv7 valido, `core/services/sales_service.py:1560` y folios en 76/86/327).

Pendientes reales:
- `SalesReadRepository.find_sale_by_folio_or_id` hace `WHERE folio=? OR CAST(id AS TEXT)=?` (linea
  61) — un `CAST` defensivo que solo tiene sentido si hay filas historicas no-TEXT; verificar con
  datos reales en SALES-1, no solo con el DDL.
- `core/services/sales_reversal_service.py::cancel_sale(self, sale_id: int, ...)` (linea 278) — el
  type hint dice `int` aunque los ids reales son strings UUIDv7 (no rompe en runtime, Python no lo
  fuerza, pero señala que la migracion de identidad no se propago a las anotaciones de tipo).
- Dinero es **float** de punta a punta en la ruta real (`cart_calculator.py`:
  `float(it.get('cantidad', 0)) * float(it.get('precio_unitario', 0))`, `round(..., 2)`) — Decimal
  no ha empezado.
- Nadie llama `validate_uuidv7`/`is_uuidv7` (ya existen en `backend/shared/ids.py`) en los limites de
  `SalesReadRepository` o `sales_reversal_service` — no hay un value object `SaleId`/`SaleLineId`
  formal todavia.

### Hardware (`hardware/*.py` + acoplamiento en `modulos/ventas.py`)

| Dispositivo | Estado real | Clasificacion |
|---|---|---|
| Cajon de dinero | `modulos/ventas.py::_abrir_cajon` (3036-3044) ya enruta por `container.hardware_service.open_cash_drawer()` — comentario explicito: "La UI no maneja transporte de hardware". `hardware/cajon_dinero.py::CajonDinero` (con fallback hardcodeado `/dev/ttyS0`@9600) parece huerfano de la ruta de ventas — confirmar consumidores antes de borrar. | REUSE (gateway ya abstraido); `CajonDinero` DELETE-candidato pendiente de confirmar. |
| Bascula | `inicializar_bascula`/`leer_peso` (3112-3170) abre `serial.Serial(puerto, baud, timeout=0.2)` **directo en la UI**, con `puerto = self._hw_bascula_cfg.get("puerto", "COM3")` (3151) — **COM3 hardcodeado como fallback** — a pesar de que ya existe un `ScaleGateway` Protocol en `backend/infrastructure/hardware/scale_gateway.py` (con `StubScaleGateway`/`ManualScaleGateway`, construido para catch-weight de inventario/carnico) sin usar por Ventas. | REWRITE — reapuntar a `ScaleGateway` existente. |
| Scanner | Dos implementaciones paralelas: `_ScanContextFilter` (event filter custom sobre `txt_busqueda`/`txt_cliente`, dentro de `modulos/ventas.py`) vs. `hardware/lector_qr.py::LectorQR`/`LectorQRSerial` (default `/dev/ttyUSB0`@9600 hardcodeado). Ninguna reusa la otra. | REWRITE/MOVE — converger en un `ScannerGateway` unico. |
| Impresora de etiquetas | `hardware/impresora_etiquetas.py` — no se usa para tickets POS (eso pasa por `printer_service.py`). Baud 9600 hardcodeado como default, puertos/IP via `from_config`. | Fuera de alcance directo de Sales. |
| Terminal de pago (tarjeta) | **No existe integracion real en ninguna forma.** El boton "💳 Terminal" de la barra superior es cosmetico (muestra sucursal). No hay `PaymentTerminalGateway` en `backend/infrastructure/hardware/` ni en `backend/application/`. | BLOCKED — trabajo 100% nuevo. |

### Pagos

- Efectivo/cambio: preview via `CartCalculator`; calculo autoritativo final en
  `sales_service.py::_execute_sale_core` (hallazgos H13/H14 de `VENTAS_ERRORES_PERSISTENTES_AUDIT.md`
  no re-verificados linea por linea en esta pasada, marcar para re-chequeo en SALES-1).
- Pago mixto: `PaymentPolicy.validate_mixed_payment(total, efectivo, tarjeta)`, llamado desde
  `presentation/sales/dialogs/payment_dialog.py:261` — logica real, capa incorrecta (WRAP_TEMPORARILY,
  reubicar a `domain/sales/policies/`).
  Falta confirmar el path exacto de `PaymentPolicy` en `core/services/...` durante SALES-1.
- Mercado Pago: integracion real (`container.mercado_pago_service`), pero orquestada como saga
  multi-paso **dentro de la UI** (`finalizar_venta`) — REWRITE hacia un use case de aplicacion.
- Tarjeta/terminal: ver tabla de hardware — BLOCKED, no existe.

### Ventas suspendidas / devoluciones / reversos

**Hallazgo critico**: `suspender_venta` (3957-3997) reserva stock de forma solida via
`StockReservationService.reservar()` (persistido, SAVEPOINT-atomico, UUIDv7 `reserva_id`, TTL 30 min
via `RESERVATION_TTL_MINUTES` en `stock_reservation_service.py:14`) — **pero el sobre de la venta
suspendida (carrito, cliente, totales, nombre) solo vive en `self.ventas_en_espera`, un dict en
memoria del propio QWidget `ModuloVentas`** (3982-3987). `reanudar_venta` (4013-4025) lee del mismo
dict. **No existe tabla de BD para el sobre de venta suspendida** — si el proceso del POS se
reinicia o cae, o si otra estacion quiere ver/reanudar la venta, los datos se pierden y solo queda
una reserva de stock huerfana (que eventualmente expira via `expirar_huerfanas()`). Esto bloquea
directamente el requisito de "ventas suspendidas" del master prompt (seccion 40-41, incluye
`allow_cross_workstation_resume`). Clasificacion: **BLOCKED / construir desde cero** — no es un
problema de logica mal ubicada, es una ausencia real.

`StockReservationService` en si (192 lineas): bien estructurado — `reservar`/`liberar`/`confirmar`/
`marcar_revision`, SAVEPOINT-atomico, expiracion por TTL, publica eventos `AJUSTE_INVENTARIO`.
Clasificacion: **REUSE** como base de la politica de "stock hold" de SALES-N.

`core/services/sales_reversal_service.py` (889 lineas): `cancel_sale` (278+) es atomico
(`BEGIN IMMEDIATE`), tiene estado transicional `CANCEL_PENDING`, trigger de BD
`trg_block_double_cancel` que previene doble cancelacion, reversa inventario via ledger "SALE_RETURN
canonico", y **escribe compensacion directo en `movimientos_caja` legacy** — el propio comentario del
archivo lo admite: `# INSERT en movimientos_caja directamente para reversiones` (linea 18). Esto
corrobora, desde el lado de Ventas, el hallazgo ya documentado en CASH-00 de que Ventas todavia tiene
rutas directas hacia `movimientos_caja` en vez de pasar por
`backend/application/cash_register/sales_integration.py`. `refund_items` (440+) valida sobre-reembolso
por item; el path de nota de credito (667+) tambien compensa contra `movimientos_caja` legacy.
Clasificacion: **WRAP_TEMPORARILY** — la logica de atomicidad/idempotencia es genuinamente buena, solo
necesita re-apuntar sus escrituras de caja al contrato canonico que CASH-9/CASH-17 ya construyeron.

### Tickets/impresion

`core/services/printer_service.py` (915 lineas) ya tiene forma real de "PrintJob": enums
`PrintJobType`/`PrintJobStatus` (25, 42), dataclass `PrintJob` (59), `PrintTransport` (79),
`PrintQueue` (182), `print_ticket()` (696). Segun `VENTAS_ERRORES_PERSISTENTES_AUDIT.md` (H09-H12,
no re-verificado en esta pasada si ya se corrigio en la limpieza de mayo): `PrintQueue._worker`
ignoraba `PrintTransport.send()==False` como si fuera exito, y varios `except Exception: pass`
silenciaban errores de config/callback — **re-chequear en SALES-1**.

`modulos/ventas.py::generar_html_ticket` (4521+, >150 lineas) arma el HTML completo del recibo
**dentro de la clase UI** (aunque ya lee configuracion via query service, no SQL crudo) — genera QR
inline con la libreria `qrcode`. `_imprimir_ticket_consolidado` (3046-3088) enruta por
`printer_service.print_ticket()` cuando esta disponible, si no cae a
`_imprimir_ticket_legacy_real` (3094-3110) → `core/ticket_escpos_renderer.py`.
Clasificacion: REUSE `PrintJob`/`PrintQueue`/`PrintTransport`; **MOVE** `generar_html_ticket` fuera de
la UI hacia un `ReceiptRenderer` de aplicacion/infraestructura (mirror del patron de CASH-24).

### Permisos

**No existe clave `VENTAS` en `core/security/permission_catalog.py::CANONICAL_MODULE_PERMISSIONS`**
(308 lineas, leido completo). La entrada relevante es `"POS": ["ver", "crear", "cancelar",
"descuento"]` (linea 11) — 4 acciones planas, sin punto, en contraste marcado con el catalogo
granular ya establecido para `CAJA` (54 acciones dotted), `INVENTARIO`, `COMPRAS`, `CRM`, `CLIENTES`.

`core/session_context.py` (linea 17) menciona en docstring un codigo `"ventas.cancelar"` (minuscula,
con prefijo de modulo) que **no corresponde** a ninguna entrada real del catalogo (`POS` en
mayuscula, sin puntos) — inconsistencia documental, no solo de codigo.

`modulos/ventas.py::set_usuario_actual` (1309-1315) todavia gatea el boton Devolucion por **nombre de
rol**: `roles_con_devolucion = {"admin", "gerente"}` — exactamente el patron que este repo ya dejo
atras para Caja/Compras/Inventario (ver memoria `feedback_permissions_compras_standard`).

Clasificacion: **BLOCKED / construir desde cero** — un catalogo granular `VENTAS` (dotted, tipo
`sale.crear`, `sale.cobrar`, `sale.suspender`, `sale.reanudar`, `sale.cancelar`, `sale.devolucion`,
`sale.descuento.aplicar`, `sale.descuento.autorizar`, `sale.factura.generar`, `sale.reimprimir`, etc.)
no existe y debe seguir el estandar Compras/Inventario, no el de Losses (ver memoria). El check de
rol en linea 1313-1315 debe reescribirse.

### Tests

Cobertura mayor a lo que sugiere la documentacion previa — ~35+ archivos ya relacionados a
sale/venta:
- Raiz `tests/`: ~24 archivos (`test_sales.py`, `test_sales_event_flow.py`,
  `test_sales_operation_id_contract.py`, `test_credit_sale_backend_validation.py`,
  `test_credit_sale_cxc.py`, `test_fase1_procesar_venta_uc_rich_mapping.py`,
  `test_fase9_legacy_sales_blocked.py`, `test_legacy_venta_repository_guardrail.py`,
  `test_phase10_sales_reversal_events.py`, `test_sale_execution_result.py`,
  `test_ventas_customer_dialog_regression.py`, etc.).
- `tests/architecture/`: `test_ventas_guardrails.py` (el que referencia
  `docs/refactor/modules/ventas.md`), `test_sales_no_sql_in_ui.py`, `test_sales_no_commit_in_ui.py`,
  `test_sales_does_not_write_inventory_tables.py`, `test_sales_uses_catalog_query_service_only.py`,
  `test_sales_ticket_settings_no_direct_sql.py`, `test_sales_manual_quantity_defaults_zero.py`,
  `test_cash_sales_boundary.py`.
- `tests/integration/`: `test_credit_sale_creates_cxc_and_updates_balance.py`,
  `test_combo_sale_deducts_components.py`, `test_sales_inventory_stock_consistency.py`,
  `test_sqlite_sales_repository_uuid.py`, `test_bi_sales_metrics.py`,
  `test_growth_ledger_sale_id_cutover.py`.
- `tests/unit/`: `test_sales_application_refactor.py`, `test_sales_read_repository.py`,
  `test_sales_stock_validation_uses_query_service.py`.

No se ejecuto pytest en esta fase (solo inventario). Clasificacion: **REUSE** — red de regresion real,
comparable en tipo (no necesariamente en profundidad) a la de Caja.

---

## Matriz de capabilities (contra seccion 8 del master prompt)

| Capability objetivo | Estado hoy | Clasificacion |
|---|---|---|
| `Sale`/`SaleLine` aggregate (`backend/domain/sales/entities`) | No existe | BLOCKED |
| Value objects (`Money`, `Quantity`, `SaleTotals`, snapshots) | No existen con Decimal/UUIDv7; version muerta con float/int en `domain/` raiz | BLOCKED / DELETE lo muerto |
| Policies (checkout, descuento, suspension, cancelacion, devolucion) | Dispersas en `modulos/ventas.py` + `sales_service.py` | REWRITE |
| `SaleTotalsService`/`CartCalculator` | `CartCalculator` real, float-based | WRAP_TEMPORARILY → REWRITE a Decimal |
| Repositorios de Sales sobre aggregate | Solo `SalesReadRepository` (SQL de texto, solo lectura) | REWRITE |
| `ScaleGateway` | Existe y funciona (para inventario/carnico), Ventas no lo usa | REUSE (reapuntar) |
| `ScannerGateway` | No existe unificado; 2 implementaciones paralelas | REWRITE/MOVE |
| `PaymentTerminalGateway` | No existe en ninguna forma | BLOCKED |
| `CashDrawerGateway` | Existe (`hardware_service.open_cash_drawer()`), ya en uso | REUSE |
| `CustomerDisplayGateway` | No auditado en esta pasada (fuera de alcance de tiempo) — pendiente SALES-1 | Pendiente |
| Reserva de inventario | `StockReservationService`, solido | REUSE |
| Suspension persistente de venta | Solo en memoria (`self.ventas_en_espera`) | BLOCKED |
| Checkout atomico + idempotencia | `_execute_sale_core` tiene partes atomicas; no hay UnitOfWork/Outbox formal para Sales | REWRITE |
| Devoluciones/reversos | `SalesReversalService`, atomico, trigger-guarded, pero escribe `movimientos_caja` legacy | WRAP_TEMPORARILY |
| PrintJob/ticket | `printer_service.py` ya tiene el concepto | REUSE |
| Permisos granulares dotted | No existen (`POS` con 4 acciones planas) | BLOCKED |
| UUIDv7 en ids | Ya presente en schema y generacion (`ventas`, `detalles_venta`, `payments`, `sale_refunds`) | REUSE |
| Decimal en dinero | float de punta a punta | BLOCKED |

---

## Consumidores externos por revisar/migrar

- `backend/application/cash_register/sales_integration.py` — punto canonico de Caja que
  `sales_reversal_service.py` deberia usar en vez de escribir `movimientos_caja` directo (cruce
  confirmado con hallazgo ya documentado en CASH-00).
- WhatsApp / `whatsapp_service/erp/bridge.py` y `api/routers/pedidos.py` — consumidores de venta que
  no se auditaron en profundidad en esta pasada (fuera de presupuesto de tiempo); confirmar en SALES-1
  si llaman `sales_service.execute_sale` directo o pasan por `ProcesarVentaUC`.
- `CRM` (`CustomerCommercialEligibilityQuery`) — ya integrado (CRM-25) como chequeo advisory dentro de
  `procesar_pago`; mantener el contrato al mover esa logica a un use case.
- `presentation/sales/workers/sale_checkout_worker_factory.py::_clone_uc` — ya marcado
  DELETE/BLOCK por la auditoria previa; confirmar en SALES-1 si sigue sin uso real antes de borrar.
- `hardware/cajon_dinero.py`, `hardware/lector_qr.py` — candidatos DELETE, confirmar cero
  consumidores fuera de Ventas antes de borrar (no verificado exhaustivamente en esta pasada).
- `domain/entities/sale.py`, `domain/services/sale_domain_service.py`,
  `domain/value_objects/money.py` (raiz del repo, no `backend/domain/`) — confirmar que
  `tests/test_domain_entities.py` es su unico consumidor antes de DELETE.

---

## Riesgos priorizados

1. **P0 — Suspension de venta no persistida.** Perdida de datos ante crash/reinicio; bloquea
   requisito multi-terminal del master prompt. (seccion "Ventas suspendidas" arriba)
2. **P0 — Triple ruta de validacion de credito en la UI.** Tres caminos distintos pueden autorizar
   una venta a credito; alto riesgo de inconsistencia/bypass. (`procesar_pago` 4137-4228)
3. **P0 — Dinero en float en toda la ruta real.** Viola la Regla Cero-adyacente de este repo
   (Decimal-only) y es fuente de errores de redondeo acumulados en descuentos/impuestos/cambio.
4. **P1 — Reversos escriben `movimientos_caja` legacy directamente.** Duplica el hallazgo de CASH-00
   desde el lado de Ventas; riesgo de doble contabilizacion si Caja tambien reacciona al evento de
   reverso.
5. **P1 — Permisos de Ventas siguen en nombre de rol** (`admin`/`gerente` hardcodeado) en vez de
   codigos granulares — inconsistente con el resto del ERP y con CLAUDE.md (SQL/permite por rol
   prohibido).
6. **P1 — Bascula con `serial.Serial` directo en la UI y COM3 hardcodeado**, ignorando el
   `ScaleGateway` ya existente — viola explicitamente la seccion 4/18 del master prompt.
7. **P2 — Boton "Terminal" cosmetico** (muestra sucursal, no estado de hardware) — UX engañosa, no
   solo deuda tecnica.
8. **P2 — Dos implementaciones de captura de scanner** sin converger — riesgo de comportamiento
   divergente entre pantallas.

---

## Plan de ejecucion propuesto (pipeline SALES-N)

Siguiendo el mismo patron que CASH-N/CRM-N (una fase, un documento, tests antes de tocar logica
critica), y priorizando los riesgos P0 de arriba antes que cobertura exhaustiva de las 73 secciones
del master prompt:

- **SALES-0** (este documento) — auditoria, sin cambios de codigo.
- **SALES-1** — guardrails de arquitectura (tests que ratchean: sin SQL/commit en UI de Ventas ya
  existen parcialmente — extender con permisos-por-rol prohibidos, Decimal-only, UUIDv7-only para
  Sales) + baseline real de pytest.
- **SALES-2** — seguridad: catalogo granular `VENTAS`/`POS` dotted (mirror Compras/Inventario, no
  Losses), reemplazar el check `admin`/`gerente` hardcodeado.
- **SALES-3** — dominio: `Sale`/`SaleLine`/`SaleTotals` con UUIDv7 + Decimal en
  `backend/domain/sales/`, dejando explicito que `domain/entities/sale.py` (raiz) queda DELETE.
- **SALES-4+** — suspension de venta persistida (el gap P0 mas claro), consolidacion de la triple
  ruta de credito en un unico policy/use case, migracion de `SalesReversalService` al contrato
  canonico de Caja, `ScaleGateway`/`ScannerGateway` reales, y el resto de fases POS-N del master
  prompt (pagos, checkout atomico, hardware, offline, UI decomposition, eliminacion de legacy) en el
  orden que el usuario priorice — no se asume el orden completo por adelantado.

El layout visual (seccion 1-2 del master prompt) se preserva desde el inicio: ninguna fase de este
plan mueve, oculta o redisena el carrito, el panel de catalogo, ni el boton Cobrar.

---

## Evidencia de busquedas

Agente de auditoria (`general-purpose`, solo lectura) ejecuto lectura completa de:
`modulos/ventas.py` (init_ui, calcular_totales, procesar_pago, finalizar_venta,
_aplicar_resultado_venta, generar_html_ticket, suspender_venta/reanudar_venta, _abrir_cajon,
inicializar_bascula/leer_peso, set_usuario_actual), `hardware/scale_reader.py`,
`hardware/cajon_dinero.py`, `hardware/lector_qr.py`, `hardware/impresora_etiquetas.py`,
`backend/domain/` (busqueda de subpaquete `sales`, no encontrado), `backend/application/use_cases/
create_sale_use_case.py`, `cancel_sale_use_case.py`, `backend/application/services/
sales_application_service.py`, `backend/application/commands/sales_commands.py`,
`backend/infrastructure/db/repositories/sales_read_repository.py`,
`presentation/sales/workers/*.py`, `core/use_cases/venta.py`, `core/services/sales_service.py`,
`core/services/sales/*.py`, `core/services/sales_reversal_service.py`,
`core/services/stock_reservation_service.py`, `core/services/printer_service.py`,
`core/security/permission_catalog.py` (308 lineas completas), `migrations/m000_base_schema.py`
(`_create_ventas`), `docs/refactor/modules/ventas.md`, `docs/refactor/refactor_state.json`,
`docs/refactor/MODULE_QUEUE.md`, y los 6 documentos `VENTAS_*` previos listados en el encabezado.
Inventario de tests por patron de nombre en `tests/`, `tests/architecture/`, `tests/integration/`,
`tests/unit/` (no ejecutados).
