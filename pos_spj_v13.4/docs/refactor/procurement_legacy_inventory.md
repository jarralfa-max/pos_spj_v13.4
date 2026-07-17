# PUR-13.1 — Inventario de legacy de Compras

Inventario basado en evidencia (grep) del código legacy de Compras y su
clasificación (PUR-13.2). Reemplazo canónico = bounded context construido en
PUR-0…PUR-12 (`backend/domain|application|infrastructure/procurement`,
`frontend/desktop/modules/purchasing`).

Clasificación: **REUSE · MOVE · WRAP_TEMPORARILY · REWRITE · DELETE · BLOCKED**.

## 1. Módulos / UI

| Archivo | Responsabilidad antigua | Reemplazo canónico | Acción | Consumidores |
|---|---|---|---|---|
| `modulos/compras_pro.py` (7,362 líneas) | UI + lógica monolítica de compras, recepción QR, plantillas, alertas de costo, recetas | `frontend/desktop/modules/purchasing/` (enterprise + compra directa) | **BLOCKED** | `interfaz/main_window.py`, `interfaz/menu_lateral.py`, `core/ui/module_loader.py`, `recepcion_qr_widget`, ~20 tests |
| `modulos/compras/` (actions_bar, items_table, proveedor_panel, totals_panel) | Widgets UI extraídos del monolito | Componentes DS + páginas enterprise | **WRAP_TEMPORARILY** | sólo `compras_pro.py` |
| `modulos/planeacion_compras.py` | Forecast/planeación de compras | `ReplenishmentIntakeHandler` (PUR-11) + UI enterprise | **REWRITE** | `main_window.py` (`PLANEACION_COMPRAS`) |
| `modulos/compra_directa.py` (nuevo) | Entry wrapper → página compra directa | — | **REUSE** (canónico) | `module_loader` |
| `modulos/compras_enterprise.py` (nuevo) | Entry wrapper → módulo enterprise | — | **REUSE** (canónico) | `module_loader` |

## 2. Servicios / mutaciones

| Símbolo | Responsabilidad antigua | Reemplazo canónico | Acción | Consumidores |
|---|---|---|---|---|
| `core/services/erp_application_service.py::registrar_compra` (int IDs, float) | Mutación directa de compra | `ConfirmDirectPurchaseUseCase` | **BLOCKED** | por verificar (13.22) |
| `helper registrar_compra / guardar_compra / procesar_compra` (en monolito) | Mutación directa | `CreateDirectPurchase` + `ConfirmDirectPurchase` | **DELETE** con el monolito | `compras_pro.py` |
| `recibir_compra / recepcion local` | Entrada directa a inventario | `ReceivePurchaseOrderUseCase` → `GoodsReceipt` → evento inventario | **DELETE** con el monolito | `compras_pro.py` |
| `registrar_pago_proveedor / crear_cuenta_por_pagar` | CxP/pago directo | evento `PAYABLE_CREATED` / `SUPPLIER_PAYMENT_SCHEDULED` → Finance/Tesorería | **DELETE** con el monolito | `compras_pro.py` |

## 3. Repositorios

| Archivo | Responsabilidad antigua | Reemplazo canónico | Acción | Consumidores |
|---|---|---|---|---|
| `backend/infrastructure/db/repositories/compras_read_repository.py` | Lecturas de compra | `application/procurement/queries/` | **WRAP_TEMPORARILY** | `compras_pro.py` |
| `backend/infrastructure/db/repositories/compras_write_repository.py` | Escrituras de compra | casos de uso procurement | **WRAP_TEMPORARILY** | `compras_pro.py` |
| `repositories/purchase_repository.py` | Compras (IDs enteros) | `DirectPurchaseRepository` | **BLOCKED** | por verificar |
| `repositories/purchase_order_repository.py` | Órdenes legacy | `PurchaseOrderRepository` | **BLOCKED** | por verificar |
| `repositories/purchase_request_repository.py` | Solicitudes legacy | `PurchaseRequisitionRepository` | **BLOCKED** | por verificar |
| `repositories/proveedor_repository.py` | Proveedores | Supplier context (SUP-*) | **BLOCKED** | finanzas/compras legacy |

## 4. Permisos generales (13.15)

| Legacy | Reemplazo | Acción |
|---|---|---|
| `permission_catalog: "COMPRAS": ["ver","crear","recibir"]` | `PURCHASES_*` granulares (77) | **REWRITE** (mapper temporal → roles) |
| `"ver_compras"` en rol admin | `PURCHASES_VIEW*` | **REWRITE** |
| `compras_pro.py: "COMPRAS": frozenset({"procesar",...})` | `PurchasePermissions.*` | **DELETE** con el monolito |

## 5. Eventos duplicados (13.16)

| Legacy | Canónico | Acción |
|---|---|---|
| `COMPRA_REGISTRADA` | `DIRECT_PURCHASE_CONFIRMED` / `GOODS_RECEIPT_COMPLETED` | **DELETE** con el monolito |
| `PURCHASE_ORDER_WA` | `PURCHASE_ORDER_CREATED` | **REWRITE** (WhatsApp) |
| (varios ad-hoc sin `event_id/operation_id`) | vocabulario `ProcurementEvents` (con envelope) | **DELETE** |

## 6. Recepciones paralelas (13.13)

| Origen | Tipo real | Canónico | Acción |
|---|---|---|---|
| Compras (`compras_pro`) | Recepción de compra | `GoodsReceipt` | **BLOCKED** (migrar QR) |
| `recepcion_qr_widget` / `recepcion_qr_service` | Recepción de compra vía QR | `GoodsReceipt` + evento | **BLOCKED** (lógica útil, migrar) |
| Transferencias | `TransferReceipt` | contexto Inventario | **REUSE** (distinto) |
| Producción | `ProductionInput/Output` | contexto Producción | **REUSE** (distinto) |

## Notas de método

- Ningún archivo se marca DELETE sin verificar **cero consumidores** (PUR-13.22):
  imports estáticos, instanciaciones, rutas, tests y referencias dinámicas
  (`importlib`, `getattr`, `MODULE_REGISTRY`, `main_window`, `menu_lateral`).
- Los `BLOCKED` viven en `tests/architecture/procurement_legacy_allowlist.py`
  con causa/owner/dependencia/riesgo/condición-de-eliminación. La allowlist sólo
  puede reducirse (guardrail `test_procurement_legacy_allowlist.py`).
- El contexto canónico ya está blindado contra reintroducción por los guardrails
  PUR-13.5/10/11/15/18 (ver `procurement_legacy_removal_report.md`).
