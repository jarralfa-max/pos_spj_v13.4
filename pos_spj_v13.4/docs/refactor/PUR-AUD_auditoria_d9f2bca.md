# PUR-AUD — Respuesta a la auditoría directa de Compras (d9f2bca)

Fecha: 2026-10-11/14. Auditoría recibida: «Auditoría directa del módulo de Compras»
(27 hallazgos, 31 escenarios, base 486/490). Cada hallazgo se volvió a comprobar
contra el código actual; se corrigió o se deja abierto con su motivo.

Migración: **334** (esquema de Compras). Las compensaciones financieras usan el
perfil `PURCHASE_RETURN` que Finanzas agrega al arrancar (late additions).
Pruebas nuevas: `tests/integration/procurement/test_audit_pur_d9f2bca.py` (27) y
`tests/integration/finance/test_procurement_compensation.py` (4).

## Decisiones tomadas por defecto (revisables)

| Tema | Decisión | Por qué / cómo cambiarla |
|---|---|---|
| Qué entra a existencias (C04) | `INVENTORY`, `CONSUMABLE`, `PACKAGING`. Gasto, servicio, mantenimiento y activo se reciben pero no son stock; Finanzas reconoce CONSUMABLE/PACKAGING como inventario. | `STOCK_NATURES` en `domain/procurement/enums.py`. |
| Cumplimiento de la orden (C09) | Por lo **aceptado**: un rechazo deja la orden/compra pendiente de reposición; cerrar el faltante es una acción explícita con motivo (`COMPRAS.orden.cerrar`). | Antes 10 recibidas / 0 aceptadas = RECEIVED. |
| Tolerancia de recepción (C07) | Mide aceptado previo + todo el lote actual; lo rechazado no cuenta (su reposición cabe en lo pedido). | |
| Reserva de factura (C22) | Sólo una factura conciliada/aprobada **consume** cantidad; capturada o con diferencias **reserva** (visible aparte) y se libera cancelándola. | |
| Devolución → finanzas (C12) | Factura con CxP abierta: nota de crédito (Dr Proveedores / Cr Inventario, Cr IVA). Excedente (pagada o contado): anticipo a proveedor (1140). Sin facturar: sin asiento; la factura debe venir por menos. | Perfil `PURCHASE_RETURN`. |
| Reversos con factura (C12) | Reversar una recepción o compra directa ya facturada se rechaza: primero se cancela/corrige la factura. | |
| Alcance por sucursal (C18) | Sucursal activa siempre; asignadas con `COMPRAS.ver.sucursales_asignadas`; cualquiera con `COMPRAS.ver.todas_sucursales`. Igual que Caja. | En la base real admin/gerente/system_owner tienen todas; almacén la suya. |
| Límites acumulados (C17) | Rebasar el acumulado diario/mensual del usuario exige la autorización en caliente (no bloquea). | El límite por rol no se aplica todavía (no hay rol del actor en el caso de uso). |

## Hallazgo por hallazgo

| # | Prioridad | Estado | Qué se hizo | Prueba |
|---|---|---|---|---|
| C01 | P0 | Cerrado | Despachador y traductores publican en modo **estricto**; eventos con efecto económico (`REQUIRES_CONSUMER`) exigen consumidor o quedan PENDING con error, reintento y DEAD_LETTER; commit por fila. Los eventos derivados tienen identidad **determinista** (`derived_uuidv7`): reentregar no duplica (antes la explosión de recetas, idempotente por `event_id` derivado, duplicaba). Despacho al arrancar ya existía; se mantiene. | `TestC01DeliveryIsConfirmed` |
| C02 | P0 | Cerrado | Captura y conciliación validan proveedor, moneda, pertenencia de línea y producto contra el documento de origen; resultados `SUPPLIER_/CURRENCY_/PRODUCT_MISMATCH` no liberables. | `test_wrong_identity_never_matches` |
| C03 | P1 | Cerrado | La cantidad facturada por línea de origen suma las líneas de ESTA factura más lo aplicado antes. | `test_two_lines_on_one_source_cannot_bill_it_twice` |
| C04 | P1 | Cerrado | `purchase_nature` se persiste (migr. 334) y se toma del origen; cambiarla se rechaza. Sólo naturalezas de stock generan entrada de inventario (orden y directa). | `test_asset_nature_survives...`, `test_expense_line_does_not_enter_stock` |
| C05 | P1 | Cerrado | Subtotales por naturaleza **netos de descuento**; antes de confirmar se verifica que naturalezas + impuesto = total pagado. | `test_discount_is_net_...` |
| C06 | P1 | Cerrado | Costo de inventario neto de descuento en orden (precio neto por unidad facturable) y en compra directa. | idem |
| C07 | P1 | Cerrado | Tolerancia sobre el acumulado de la línea. | `test_split_over_delivery_...` |
| C08 | P1 | Cerrado | Línea recibida debe pertenecer a la orden y ser del mismo producto; cantidades finitas y no negativas (también en la entidad); al menos una positiva. | `test_wrong_product_and_negative...` |
| C09 | P1 | Cerrado | Cumplimiento por aceptado; reposición posible; `ClosePurchaseOrderRemainderUseCase` + botón «Cerrar faltante». | `test_fully_rejected_delivery...` |
| C10 | P1 | Cerrado | Compra directa con `PARTIALLY_RECEIVED`, remanente por línea (`direct_purchase_line_id`, migr. 334), recepción sin captura recibe sólo lo pendiente; cierre explícito de faltante. | `test_partial_receipt_keeps_the_rest_pending` |
| C11 | P1 | Cerrado | Reverso agrupa por línea de origen y suma todos los lotes; inversa exacta (sin recorte a cero). | `test_reversal_undoes_every_lot...` |
| C12 | P0 | Cerrado | Cableados `GOODS_RECEIPT_REVERSED` y `DIRECT_PURCHASE_REVERSED` → reverso de inventario (por cada recepción) y del asiento de contado; `PURCHASE_RETURN_CONFIRMED` → salida de inventario + nota de crédito. El manejador de devolución escucha CONFIRMED (el borrador no mueve stock). Reversos de documentos facturados se rechazan. La salida resuelve su **lote** (por `lot_id`, por código o por el movimiento de la recepción de origen; con varios lotes exige indicarlo): sin esto toda devolución de producto con lote se rechazaba como inventario negativo. | `test_compensation_consumers...`, `test_procurement_compensation.py`, `TestSupplierReturnLotResolution` |
| C13 | P1 | Cerrado | La devolución exige recepción completada, mismo proveedor/sucursal/almacén, línea y producto de la recepción y cantidad ≤ aceptado − devoluciones no canceladas; se revalida al confirmar. Lo devuelto confirmado deja de ser facturable. | `test_return_validates_origin...` |
| C14 | P1 | Cerrado | La recepción directa (completa, contada o inmediata) aplica el perfil de Productos: lote, caducidad, temperatura, peso. La inmediata con producto controlado pide confirmar con recepción pendiente y captura. | `test_traceability_profile_...` |
| C15 | P1 | Cerrado | Adjudicación: línea de la misma RFQ, proveedor que la cotizó, cantidad ≤ cotizada, una sola adjudicación por RFQ; la generación de órdenes revalida el proveedor. | `test_wrong_supplier_excess_and_second_award...` |
| C16 | P1 | Cerrado | La orden hereda moneda, descuento e impuesto proporcionales de la cotización; moneda extranjera exige tipo de cambio. | `test_order_keeps_quoted_currency...` |
| C17 | P1 | Cerrado (sin rol) | Acumulado diario y mensual del usuario (misma moneda, sin canceladas/reversadas) exige autorización. | `test_daily_limit_requires_authorization` |
| C18 | P1 | Cerrado en comandos | `require_branch` en crear orden, recibir orden, crear/confirmar/recibir compra directa, crear devolución. **Abierto:** lecturas por ID. | `test_session_cannot_operate_another_branch` |
| C19 | P2 | Cerrado | Huella de contenido en orden, factura y compra directa: misma clave con otro contenido → `IDEMPOTENCY_CONFLICT`. | `test_reused_key_with_other_content...` |
| C20 | P1 | Cerrado | `ProcurementUnitOfWork` sólo confirma si es la más externa de la conexión (registro que retiene la conexión para que su id no se reutilice); `owns_transaction=False` para otro contexto. | `test_nested_use_case_does_not_commit...` |
| C21 | P2 | Cerrado | El guardado de factura conserva `matched_by_user_id`/`released_by_user_id` y no borra `payable_id`. | `test_match_actor_is_kept_on_the_header` |
| C22 | P2 | Cerrado | Aplicado vs reservado; `CancelSupplierInvoiceUseCase` + botón; la pantalla de captura muestra lo reservado aparte. | `test_unmatched_draft...` |
| C23 | P2 | Cerrado | `Money` rechaza no finitos, códigos de moneda inválidos y sumas entre monedas. | `test_money_rejects_...` |
| C24 | P1 | Cerrado | KPI, alertas y gráficas reciben sucursal, periodo y moneda del mismo `_scope()` que las listas. | `test_alerts_are_calculated_in_query_service_not_ui` |
| C25 | P2 | Cerrado | Diálogo de factura: moneda y naturaleza del origen, confirma dentro del diálogo con `operation_id` estable y conserva la captura ante rechazo. | suite UI de Compras |
| C26 | P2 | Cerrado | Ruta «Devoluciones y reversos» (reversar recepción, devolver por línea, confirmar/cancelar devolución), «Cerrar faltante» en la orden y «Cancelar factura». | `returns_page.py` (smoke) |
| C27 | P2 | Parcial | Lo facturable usa la MISMA regla de aceptado que la conciliación; la analítica ya no convierte una tabla ausente en cero; política de contabilización de compras unificada (Finanzas). **Abierto:** duplicación entre los dos presentadores (contexto/lookup). | |

## Pruebas heredadas corregidas

- `test_11_credit_purchase_ends_in_a_paid_payable` y `test_variable_weight_order_pays_the_real_weight`: proveedores de prueba `sup-1/sup-2` cambiados por UUIDv7 (ahora pasan de punta a punta, incluido el pago con evidencia de Finanzas).
- `test_real_purchase_return_event_is_consumable_by_supplier_return_handler`: ahora parte de una recepción completada, confirma y consume `PURCHASE_RETURN_CONFIRMED`; ya no documenta la falla de ubicación (resuelta) sino que la existencia baja 10 → 7 dentro del lote.
- `test_purchase_and_reception_use_canonical_inventory_service` y `test_navigation_has_one_canonical_purchasing_route`: reescritas contra la composición viva (`core/` ya no existe).

## Abierto, con motivo

- **Alcance en lecturas por ID** (C18) y **límite por rol** (C17).
- **Duplicación entre presentadores** de Compras (C27).
- **Conversión cambiaria**: monedas distintas se rechazan; no se convierten.
- Compra directa: el **cierre de faltante** existe como caso de uso pero aún no tiene botón en el historial de compra directa (sí en la orden).

## Validación

Regresión amplia (finanzas, compras, e2e, caja, arranque, fidelidad, RRHH, shell,
crédito, ventas, CRM, clientes, inventario, arquitectura): 2284 aprobadas antes del
ajuste de lotes. Tras él, inventario + compras + e2e + compensaciones: 1094 aprobadas.
Las fallas restantes son previas y ajenas: módulos `core`/`repositories` que ya no
existen, la analítica de Inventario sin catálogos de Mermas en su fixture,
`nav.losses`, la guarda de esquema con rutas `/` vs `\` en Windows y
`test_purchasing_root_is_sidebar_shell_not_tab_widget` (cambio a `PageStack` de otra
persona).
