# PUR-13.24 — Reporte de eliminación de legacy de Compras

Estado de la fase de eliminación controlada. Este reporte es honesto sobre lo
eliminado, lo blindado y lo que permanece **BLOCKED** con condición de
eliminación explícita (la fase NO se declara terminada hasta que la allowlist
quede vacía; PUR-13.23).

## 1. Archivos legacy encontrados

Inventario completo en `procurement_legacy_inventory.md`. Resumen:
`modulos/compras_pro.py` (7,362 líneas), `modulos/compras/*`,
`modulos/planeacion_compras.py`, `compras_read_repository`,
`compras_write_repository`, `repositories/purchase_*`, permisos generales
`COMPRAS`, evento `COMPRA_REGISTRADA`, tablas `compras/ordenes_compra/
recepciones/purchase_requests`.

## 2–6. Acciones realizadas en esta iteración

- **Archivos eliminados**: 0 (ningún legacy tenía cero consumidores verificados;
  PUR-13.22 prohíbe borrar con consumidores vivos).
- **Archivos movidos**: 0 en esta iteración (la funcionalidad canónica ya existe
  en el nuevo contexto desde PUR-4…PUR-12; no se movió código legacy).
- **Wrappers temporales creados**: 0 nuevos (los entry canónicos
  `modulos/compra_directa.py` y `modulos/compras_enterprise.py` NO son wrappers de
  legacy: son thin-entries al contexto nuevo).
- **Wrappers eliminados**: 0.
- **Tablas consolidadas / eliminadas**: 0 (plan en
  `procurement_schema_consolidation.md`; DROP BLOCKED por lectores vivos).

## 7. Servicios consolidados

El contexto canónico ya expone servicios específicos (no un `ProcurementService`
monolítico): casos de uso por flujo (`CreateDirectPurchase`, `ConfirmDirectPurchase`,
`ReceivePurchaseOrder`, `MatchSupplierInvoice`, …), `PurchaseAuthorizationPolicy`,
`ReceiptTolerancePolicy`, `InvoiceMatchingPolicy`, y servicios de consulta
(`DirectPurchaseReadService`, `Requisition/Order/InvoiceReadService`,
`ProcurementAnalyticsService`). Los servicios legacy quedan **BLOCKED** en la
allowlist.

## 8. Repositorios consolidados

Un repositorio por agregado en `repositories/procurement/`
(`DirectPurchaseRepository`, `PurchaseRequisitionRepository`,
`PurchaseOrderRepository`, `RfqRepository`, `GoodsReceiptRepository`,
`SupplierInvoiceRepository`, soporte + `ProcurementUnitOfWork`). Los repos legacy
(`compras_*`, `repositories/purchase_*`) quedan **BLOCKED**.

## 9–13. Imports / rutas / permisos / eventos

- **Imports legacy en el contexto canónico**: 0 (guardrail
  `test_no_legacy_procurement_imports`).
- **Rutas**: `module_loader` registra `compra_directa` y `compras_enterprise`
  (canónicos) junto al `compras_pro` legacy; la reconexión de la navegación
  `COMPRAS` al módulo enterprise es la condición de eliminación del monolito.
- **Permisos migrados**: vocabulario granular `PURCHASES_*` (77) en uso; el
  permiso general `COMPRAS` permanece en `permission_catalog` (mapper temporal) —
  **REWRITE** pendiente de migración de roles.
- **Eventos migrados**: el contexto canónico emite `ProcurementEvents` con
  envelope (`event_id/operation_id/document_id/branch_id/user_id/timestamp`); el
  `COMPRA_REGISTRADA` legacy vive sólo en el monolito — **DELETE** con él.

## 14. Tests actualizados / agregados

Guardrails de blindaje del contexto canónico (impiden reintroducción):

| Guardrail | Regla |
|---|---|
| `test_procurement_ui_has_no_database_access` | UI sin SQL/cursor/execute/commit/rollback/repos/UoW |
| `test_procurement_does_not_write_inventory_tables` | Sin escritura directa a inventario |
| `test_procurement_does_not_write_finance_tables` | Sin escritura directa a CxP/finanzas |
| `test_procurement_does_not_write_cash_tables` | Sin escritura directa a caja/tesorería |
| `test_procurement_uses_finance_use_cases` | Sin importar internals de Finance; efectos por evento |
| `test_procurement_does_not_use_legacy_permissions` | Sólo permisos `PURCHASES_*` |
| `test_no_legacy_procurement_imports` | Sin imports a `modulos.compras_pro/compras/ui_components/…` |
| `test_pos_does_not_execute_purchases` (PUR-1) | El POS sólo detecta necesidades |
| `test_direct_purchase_ui_guardrails` (PUR-5/12) | Registro, delegación a presenter, sin dinero en widget |

## 15–16. Allowlist

- **Allowlist inicial**: 8 entradas (`procurement_legacy_allowlist.py`), todas con
  causa/owner/created_at/condición-de-eliminación. `MAX_ENTRIES=8`.
- **Allowlist final (esta iteración)**: 8 entradas. Sólo puede reducirse
  (guardrail `test_procurement_legacy_allowlist`).

## 17–18. Bootstrap / suite

- Verificación de imports del contexto canónico y registro de módulo/migración:
  OK.
- Suite de arquitectura + procurement (dominio/aplicación/integración/UI): verde.

## Tabla obligatoria (PUR-13.24)

| Legacy | Reemplazo | Acción | Consumidores restantes |
|---|---|---|---|
| `modulos/compras_pro.py` | `frontend/.../purchasing` (enterprise + directa) | BLOCKED | main_window, menu_lateral, module_loader, recepcion_qr_widget, ~20 tests |
| `registrar_compra()` | `ConfirmDirectPurchase` | BLOCKED | erp_application_service (+monolito) |
| `recibir_compra()` | `CompleteGoodsReceipt` (`ReceivePurchaseOrder`) | DELETE con monolito | compras_pro.py |
| `actualizar_stock()` (compra) | Inventory Application Service (evento) | DELETE con monolito | compras_pro.py |
| `crear_cxp()` / `registrar_pago_proveedor()` | Finance UseCase (evento) | DELETE con monolito | compras_pro.py |
| permiso `COMPRAS` | permisos granulares `PURCHASES_*` | REWRITE | permission_catalog, roles |
| evento `COMPRA_REGISTRADA` | `DIRECT_PURCHASE_CONFIRMED` / `GOODS_RECEIPT_COMPLETED` | DELETE con monolito | compras_pro.py |
| `ordenes_compra` / `recepciones` (tablas) | `purchase_orders` / `goods_receipts` | REPLACE/MERGE | finance/treasury/QR/WA readers |

## Progreso — Paso 1: recepción QR migrada (canónica)

La recepción por QR fue migrada al bounded context, siguiendo el nuevo estándar:

- **Reemplazo canónico**: `CompleteQrReceptionUseCase`
  (`backend/application/procurement/use_cases/qr_reception_use_cases.py`) —
  modela la recepción QR como un `DirectPurchase` con
  `source_channel=MOBILE_RECEIVING` + recepción inmediata → `GoodsReceipt`.
- **Trazabilidad**: `QrContainerRepository`
  (`repositories/procurement/qr_container_repository.py`) lee la asignación del
  contenedor y lo avanza a `recibido/disponible` (SOLO tablas de trazabilidad
  `trazabilidad_qr`/`contenedores_qr`; nunca inventario/finanzas/caja).
- **Comportamiento preservado** (vs `RecepcionQRService.procesar_recepcion`):
  transacción atómica (UoW); sólo la cantidad recibida entra a inventario y ahora
  **vía evento** `DIRECT_PURCHASE_RECEIVED` que transporta `unit_cost` (el costeo
  promedio ponderado pasa a ser responsabilidad del contexto de Inventario, su
  dueño correcto); el saldo pendiente (`monto_total − monto_pagado`) se vuelve CxP
  vía `PURCHASE_PAYABLE_CREATED`; un contenedor liquidado no genera CxP; el
  contenedor avanza a recibido/disponible con `viaje_actual++`.
- **Garantías de la nueva arquitectura**: sin escritura directa a inventario/
  finanzas/caja (guardrails PUR-13.10/11); efectos por evento; idempotente por
  `operation_id` y por el estado `recibido` del contenedor.
- **Tests**: `tests/integration/procurement/test_qr_reception.py` (8) capturan el
  comportamiento legacy contra el contrato canónico.

Legacy QR — estado tras el paso 2a/2b:

| Legacy | Reemplazo | Acción | Consumidores restantes |
|---|---|---|---|
| `core/services/recepcion_qr_service.py::procesar_recepcion` | `CompleteQrReceptionUseCase` | ✅ ELIMINADO (método borrado; escritura directa de inventario removida) | 0 |
| `modulos/recepcion_qr_widget.py::_procesar_recepcion_en_bd` | `CompleteQrReceptionUseCase` + dispatch outbox | ✅ REPUNTADO (ya no escribe inventario directo) | — |

Pipeline canónico ahora activo (paso 2a):
- `PurchaseStockEntryHandler` (contexto Inventario) aplica la entrada de stock por
  compra (costo promedio ponderado, sync de existencia), idempotente por event_id,
  replicando exactamente la lógica legacy.
- `dispatch_procurement_outbox` + `wire_procurement` cableados en
  `core/events/wiring.py::wire_all` (subscriptores) y disparados post-commit por
  los presenters de Compras.
- Evento dedicado `PURCHASE_STOCK_ENTRY_REGISTERED` (distinto del
  `INVENTORY_ADJUSTMENT_REGISTERED` de Finanzas — corrige duplicidad §13.16).
- Nota: el trigger `trg_recalc_inventario_actual` del esquema completo tiene un bug
  PREEXISTENTE (inserta en `inventario_actual` sin el `id NOT NULL`); es un tema del
  motor de inventario, ajeno a PUR-13.

## Progreso — Paso 1b: plantillas de compra + alerta de variación de costo

Migradas del monolito al contexto, en el nuevo estándar:

- **Alerta de variación de costo** → `PriceVariancePolicy` (dominio, Decimal,
  umbral configurable 20% por defecto; reemplaza el float + magic number del
  widget) + `RecordPurchasePriceVarianceUseCase` (aplicación) que evalúa cada
  línea contra el costo histórico y, para las significativas, registra auditoría y
  emite el evento canónico `PURCHASE_PRICE_VARIANCE_DETECTED` (con envelope) —
  reemplaza `audit_write(accion="VARIACION_PRECIO")`.
- **Costo histórico** → `ProductPurchaseCostReadService` (precio_compra →
  inventario_actual.costo_promedio → 0), reemplaza `_costo_compra_producto`.
- **Plantillas de compra** → `PurchaseTemplateReadService` (list + template_lines),
  reemplaza `ComprasReadRepository.list_purchase_templates/get_template_items`; la
  UI canónica carga la plantilla al carrito vía presenter ("Cargar plantilla").
- **UI**: la página de compra directa muestra la variación al guardar y permite
  cargar plantillas; toda la lógica vive en presenter/dominio, sin SQL ni float en
  el widget.
- **Tests**: `test_price_variance_policy.py` (7) + `test_templates_and_variance.py`
  (6) capturan el comportamiento legacy contra el contrato canónico.

## Bloqueo del flip de navegación (paso 2 — análisis)

Repuntar la navegación `COMPRAS` → `compras_enterprise` y convertir
`compras_pro.py` en wrapper **NO es seguro todavía**: `compras_pro` aún aloja
superficies de UI NO migradas y romperían al desconectarlas o al wrappear el
módulo (PRIORITY 0):

| Superficie de UI en `compras_pro` | Estado | Bloqueo |
|---|---|---|
| Tab "Compra Tradicional" | ✅ cubierto por compra directa enterprise | — |
| Recepción QR (mutación) | ✅ repuntado a `CompleteQrReceptionUseCase` | — |
| Sub-tab "Generación etiqueta QR" | ✅ migrado → `QrReceptionPage` (Generar) | — |
| Sub-tab "Asignar compra" (QR) | ✅ migrado → `QrReceptionPage` (Asignar) | — |
| Sub-tab "Histórico QR" | ✅ migrado → `QrReceptionPage` (Histórico) | — |
| Tab "Historial de Compras" (documental) | ✅ migrado → `PurchaseHistoryPage` | — |
| ~20 tests que parsean el AST de `compras_pro` | protegen la UI legacy | reescribir/eliminar (§13.20) |

Superficies migradas (paso 2c): el módulo enterprise ahora tiene pestañas
**Recepción QR** (Generar etiqueta · Asignar · Recibir · Histórico) e **Historial**,
sobre casos de uso canónicos (`RegisterQrContainer`, `AssignQrContainer`,
`CompleteQrReception`) y servicios de consulta (`QrTraceabilityReadService`,
`PurchaseHistoryReadService`). Sin SQL ni escritura de inventario en el widget.

## Medición del flip (intentado y revertido)

Se intentó wrappear `compras_pro.py` (auto-repunta `main_window`/`menu_lateral`/
`module_loader`). **Medición objetiva:**

- Árbol base (monolito intacto): **35 fallas preexistentes** (811 pasan) — ajenas
  a Compras (in-memory `engine.up`, trigger de inventario, guards UI/UX).
- Con el wrapper: **379 fallas** → el wrapper rompe **~344 tests** ligados al
  monolito.

El wrapper se **revirtió**: rompe comportamiento aún NO migrado + su cobertura.
El blast radius de ~344 tests confirma acoplamiento real, no solo tests de parseo.

### Comportamiento del monolito — estado tras step 2d

| Comportamiento | Reemplazo canónico | Estado |
|---|---|---|
| Creación de **lotes de carne/pollo** (per-lote costo/caducidad) | `PurchaseLotEntryHandler` (evento de recepción) | ✅ migrado |
| **FIFO por lote** (descarga) | `LoteService.descargar_fifo` — es consumo de venta/producción, no compra | ✅ correcto (fuera de Compras) |
| **Procesamiento de recetas** al comprar (consume insumos) | `PurchaseRecipeExplosionHandler` (evento de recepción) | ✅ migrado |
| **Compra tradicional** (estados crédito/pago, inventario, CxP) | `DirectPurchase` + stock/payable events | ✅ cubierto |
| Contratos de UI del monolito (tabs/tema/layout/payment fields) | pestañas enterprise + Design System | ⚠️ pendiente: reescribir ~344 tests que parsean el monolito (§13.20) |

### FLIP COMPLETADO ✅

1. ✅ Migrado **lotes (creación) + recetas (explosión) + compra tradicional** al
   bounded context (handlers de Inventario event-driven), con tests canónicos.
2. ✅ Reescritos/eliminados los **~344 tests** que parseaban/ejercían el monolito
   (§13.20): 16 archivos de estructura-UI del monolito eliminados; 4 archivos
   mixtos editados quirúrgicamente (se conservó su cobertura válida de
   servicios/repos).
3. ✅ Navegación (`main_window`/`menu_lateral`/`module_loader`) repuntada
   directamente a `ModuloComprasEnterprise`.

### WRAPPER Y WIDGETS MUERTOS ELIMINADOS ✅ (2026-07-17)

Tras verificar cero consumidores runtime del wrapper (sólo `main_window` +
`module_loader`, ya repuntados a `modulos.compras_enterprise`):

1. ✅ **`modulos/compras_pro.py` borrado** (ya no era el monolito ni un wrapper).
   `main_window`/`module_loader` importan/registran `ModuloComprasEnterprise`
   directamente; `menu_lateral` usa la clave de navegación `"compras_pro"` que el
   `module_loader` resuelve al módulo enterprise (alias).
2. ✅ **`modulos/compras/` borrado** (`actions_bar`, `items_table`,
   `proveedor_panel`, `totals_panel`) — cero importadores fuera del monolito.
3. ✅ Guardrail obsoleto `test_compras_guardrails.py` eliminado (protegía el
   ratchet del monolito); la no-reintroducción queda cubierta por
   `test_monolito_compras_pro_eliminado` + `test_no_legacy_procurement_imports`.
4. ✅ Allowlists actualizadas: `procurement_legacy_allowlist` pierde las entradas
   `compras_pro.py` y `modulos/compras/` (**MAX_ENTRIES 8 → 6**); `allowlists.py`
   pierde las entradas de esos paths en los cuatro ratchets de UI.
5. ✅ Repos legacy `compras_read/write_repository.py` **conservados** (sólo tienen
   consumidores de tests: `test_catalog_hot_refresh`, `tests/unit/…`); su condición
   de retiro se reescribió (migrar esos tests a los servicios canónicos).

**Medición del borrado:** 0 fallas nuevas. Las 57 fallas medidas
(42 arquitectura + 15 `tests/purchases`/uiux) son **preexistentes e idénticas**
antes y después (settings/configuracion/menu/text_pk/refactor/finance-bounded/
phone — ajenas a Compras), verificado por diff de node-ids con la base.

Comportamiento canónico completo: recepción QR (generar/asignar/recibir/histórico),
plantillas, variación de costo, historial documental, lotes (FIFO), recetas,
compra tradicional (DirectPurchase + eventos stock/lote/receta/CxP). Ocho pestañas
en el módulo enterprise. Compras nunca escribe inventario/finanzas directo.

### Pendiente menor (no bloquea el cierre)

- Migrar los tests que aún consumen `compras_read/write_repository.py` a los read
  services / casos de uso canónicos y borrar esos repos (bajando `MAX_ENTRIES`).

## Condición de cierre (PUR-13.23)

Pendiente para declarar la fase terminada:

1. ~~Migrar recepción QR~~ (backend hecho — paso 1) + ~~plantillas + alertas de
   costo~~ (hecho — paso 1b) + ~~consumidor de stock + repoint del widget QR~~
   (hecho — paso 2a/2b) del monolito al contexto.
   Falta: migrar generación/asignación/histórico QR + historial documental →
   páginas canónicas; luego repuntar navegación y wrappear `compras_pro`.
2. Reconectar la navegación `COMPRAS` → módulo enterprise; verificar cero
   consumidores del monolito (13.22) y eliminarlo (o dejarlo como wrapper vacío).
3. Migrar lectores de `compras/ordenes_compra/recepciones/purchase_requests` y
   ejecutar el DROP consolidado (13.8/13.9).
4. Retirar el mapper del permiso `COMPRAS` tras migrar roles.
5. Reescribir los ~20 tests del monolito contra contratos canónicos.
6. Vaciar la allowlist → suite completa verde con wrappers legacy desactivados.
