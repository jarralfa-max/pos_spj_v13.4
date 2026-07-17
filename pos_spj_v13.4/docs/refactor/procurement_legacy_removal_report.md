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

## Condición de cierre (PUR-13.23)

Pendiente para declarar la fase terminada:

1. Migrar recepción QR + plantillas + alertas de costo del monolito al contexto.
2. Reconectar la navegación `COMPRAS` → módulo enterprise; verificar cero
   consumidores del monolito (13.22) y eliminarlo (o dejarlo como wrapper vacío).
3. Migrar lectores de `compras/ordenes_compra/recepciones/purchase_requests` y
   ejecutar el DROP consolidado (13.8/13.9).
4. Retirar el mapper del permiso `COMPRAS` tras migrar roles.
5. Reescribir los ~20 tests del monolito contra contratos canónicos.
6. Vaciar la allowlist → suite completa verde con wrappers legacy desactivados.
