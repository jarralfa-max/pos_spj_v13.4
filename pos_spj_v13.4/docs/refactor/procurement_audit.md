# FASE PUR-0 — Auditoría del módulo de Compras (Procurement)

> Auditoría previa al bounded context canónico de Compras. Principio: **el POS
> detecta necesidades; Compras abastece; Inventario recibe; Finanzas reconoce la
> obligación; Tesorería/Caja chica pagan.** No duplicar tablas, entidades,
> repositorios ni servicios.

Fecha: 2026-07-17.

## 1. Separación POS ↔ Compras (hallazgo clave)

**El POS NO ejecuta compras.** No hay ejecución de compra en `modulos/ventas.py`
ni `modulos/caja.py` (sin `INSERT INTO compras`, sin `ComprasWriteRepository`,
sin creación de órdenes/recepciones/CxP). Las compras se ejecutan en
`modulos/compras_pro.py` (módulo "COMPRAS" en la navegación).

→ La invariante #1 del prompt (`test_pos_does_not_execute_purchases`) **ya se
cumple** en la práctica; PUR-1 la **bloquea con un guardrail** y añade el
vocabulario canónico de necesidades de reposición.

## 2. Implementaciones existentes (inventario)

### Tablas (born-clean TEXT id ya en varias)
```
compras, ordenes_compra, contenedores                    (compras + órdenes + QR contenedores)
recepciones, recepcion_items, recepciones_pollo          (recepción, incl. pollo)
purchase_requests, purchase_request_items,               (solicitudes/necesidades)
  purchase_request_events
anticipos, anticipo_config, anticipo_reglas              (anticipos a proveedor)
```

### Código (FRAGMENTADO en varios stacks — riesgo de duplicación)
| Stack | Archivos | Nota |
|---|---|---|
| UI monolito | `modulos/compras_pro.py` (**7,362 líneas**) | Repos directos (`ComprasRead/WriteRepository`, `ConnectionUnitOfWork`), `design_tokens` inline, `kpi_card`/`ui_components` legacy. **Objetivo principal del refactor.** |
| Aplicación A | `application/purchases/` (`traditional_purchase_uc`, `purchase_order_uc`, `purchase_request_uc`, `states`, `commands`, `results`, `receive_po_adapter`) | Ruta "canónica Phase 2". |
| Aplicación B | `backend/application/use_cases/` (`create_purchase_order_use_case`, `receive_purchase_use_case`, `generate_purchase_plan_use_case`), `commands/purchase_commands.py`, `queries/purchase_planning_query_service.py` | Otra ruta. |
| Legacy | `core/services/purchase_service.py`, `core/use_cases/compra.py`, `core/services/compras_inventariables_engine.py`, `core/services/recepcion_qr_service.py`, `core/events/handlers/purchase_handler.py` | Servicios legacy. |
| Repos | `repositories/purchase_repository.py`, `purchase_order_repository.py`, `purchase_request_repository.py`, `backend/infrastructure/db/repositories/compras_read/write_repository.py` | Múltiples repos de compra. |
| Planeación | `modulos/planeacion_compras.py` + `PurchasePlanningQueryService` | Forecast/sugerencias (módulo aparte "PLANEACION_COMPRAS"). |

### Integración existente
- Recepción → finanzas: `backend/application/event_handlers/finance/purchase_received_handler.py`.
- Proveedores: `compras_*_repository` leen la tabla legacy `proveedores` (ver
  `supplier_management_audit.md`; el maestro canónico es `supplier_master`).
- Eventos actuales: `PURCHASE_ORDER_CREATED`, `PURCHASE_RECEIVED`,
  `PURCHASE_CREATED`, `PURCHASE_PLAN_GENERATED`, `PURCHASE_SUGGESTION_CREATED`.

## 3. Brechas contra el estándar objetivo

- **No existe** bounded context `backend/domain/procurement/`.
- **No existen** permisos granulares `PURCHASES_*` (§55-62) — solo nombres de evento.
- **No existen** límites monetarios (`UserPurchaseLimit`/`RolePurchaseLimit`/… §63).
- **No existe** autorización en caliente (§64) ni policies de segregación (§65).
- **No existe** "Compra directa" como flujo canónico con policy (§9-12); la
  compra rápida vive dispersa en `compras_pro.py`.
- **No existe** selección de flujo (`PurchaseWorkflowPolicy`, §9).
- UI: `compras_pro.py` usa colores hardcodeados, `QLineEdit` para cantidad/costo,
  SQL/repos directos — incumple el Design System y las reglas de UI.
- Fragmentación: 3+ stacks de aplicación para compra/orden/recepción → consolidar
  en un solo bounded context `procurement`.

## 4. Decisión arquitectónica

- **Bounded context nuevo y canónico:** `backend/domain/procurement/`,
  `backend/application/procurement/`, repos, y UI en
  `frontend/desktop/modules/procurement/`.
- **Identidad:** UUIDv7 + códigos humanos por tipo documental
  (SC/RFQ/COT/OC/CD/REC/DEV/FPR-AAAA-NNNNNN, §7).
- **Dinero/peso/cantidad:** `Decimal`, nunca `float`.
- **Proveedores:** consume el maestro canónico `supplier_master` (SUP-*), no la
  tabla legacy.
- **Finanzas/CxP/Tesorería:** consume los casos de uso financieros canónicos; no
  duplica CxP ni accede a las tablas de caja del POS.
- **Reutilización:** tablas existentes (compras/ordenes_compra/recepciones/
  anticipos/purchase_requests) se evalúan por fase; el esquema canónico se crea
  born-clean donde falte, sin romper lectores vivos (patrón usado en SUP-2).
- **Migración de stacks:** `application/purchases/` y `backend/application/use_cases/*purchase*`
  se consolidan en `procurement`; `compras_pro.py` → wrapper temporal → eliminación.

## 5. Plan por fases (dependencias)

```
PUR-0  Auditoría (este documento)                              ← ENTREGADO
PUR-1  Separación POS–Compras: eventos de reposición + guardrail
PUR-2  Seguridad base: permisos granulares + límites + segregación (dominio, tests)
PUR-3  Dominio (compra directa, solicitudes, cotizaciones, órdenes, recepción, factura, policies, eventos)
PUR-4  Persistencia (esquema, repos, constraints, índices, idempotencia, atomicidad)
PUR-5  Compra directa (UI en Compras: proveedor, escaneo, carrito, peso, totales, financiero, autorización, recepción, reverso)
PUR-6  Solicitudes y aprobación · PUR-7 Cotizaciones · PUR-8 Órdenes
PUR-9  Recepción (estándar/QR/peso/pollo/calidad/diferencias/devoluciones)
PUR-10 Factura y CxP · PUR-11 Integraciones · PUR-12 UI/UX+analytics · PUR-13 Validación
```

## 6. Riesgos

1. **Fragmentación**: consolidar 3+ stacks sin romper flujos vivos (recepción→
   finanzas, planeación). Migrar por fase con guardrails.
2. **Monolito UI** (`compras_pro.py`, 7.3k líneas): migración incremental a
   `procurement` con wrapper temporal.
3. **Tablas legacy** con lectores vivos: no dropear hasta migrar consumidores.

Estado global: **IN_PROGRESS** — PUR-1/PUR-2 (separación + seguridad) en construcción.
