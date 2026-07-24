# PRC-9 — Reporte de validación final del contexto Pricing / Costing

Cierre del bounded context canónico de **Precios y Costos** (born-clean, UUIDv7,
Money/Decimal, event-driven, security-first, Design System JUANIS). Valida el
trabajo PRC-0 → PRC-8 contra REGLA CERO y los criterios de terminado.

## 1. Resultado

| Suite | Resultado |
| ----- | --------- |
| Dominio + aplicación + integración (`tests/{unit,integration}/pricing`) | **114 passed** |
| Guardrails de arquitectura de Pricing (6) | **10 passed** |
| **Total Pricing** | **124 passed, 0 fallas** |
| Bootstrap DB vacía (migraciones 149/150/151) | **limpio** (136 migraciones, cobertura 80%) |

29 archivos de código canónico (dominio/aplicación/infra/UI), sin `__init__`.

## 2. Auditorías (REGLA CERO)

| Auditoría | Guardrail | Estado |
| --------- | --------- | ------ |
| UUIDv7 única identidad (sin AUTOINCREMENT / `lastrowid` / `int(_id)`) | `test_pricing_uses_uuidv7.py` | ✅ |
| Money/Decimal-only (sin REAL en esquema, sin `float()` en el contexto) | `test_pricing_uses_money_decimal.py` | ✅ |
| UI sin acceso a BD (delega en `PricingReadService` vía presenter) | `test_pricing_ui_has_no_database_access.py` | ✅ |
| Pricing no lee tablas legacy de precio/costo | `test_pricing_context_has_no_legacy_price_reads.py` | ✅ |
| Sin nuevos lectores de tablas de precio legacy (ratchet) | `test_no_new_legacy_pricing_reads.py` | ✅ |
| El maestro `products` no posee precio/costo | `test_product_master_does_not_own_pricing.py` | ✅ |

## 3. Fases entregadas

| Fase | Entregable |
| ---- | ---------- |
| PRC-0 | Auditoría + plan (`pricing_legacy_inventory.md`, `pricing_refactor_execution_plan.md`) |
| PRC-1 | 22 permisos `PRICING_*` + `PricingAuthorizationPolicy` (segregación, alcance, hot-auth) |
| PRC-2 | Dominio: `Money`, `MarginPolicy`, enums, `PriceList`/`ProductPrice`/`VolumePrice`/`ProductCost`, eventos |
| PRC-3 | Esquema born-clean (8 tablas, TEXT PK UUIDv7, Money=TEXT Decimal, sin REAL), migración 149 |
| PRC-4 | `PricingResolutionService` (volumen>cliente>lista>base) + query services + `PricingRepository` |
| PRC-5 | Backfill 150 (productos/precios_lista/precios_volumen/branch_products → canónico) |
| PRC-6 | Costo por evento (`AverageCostingService` + `ProductCostProjectionHandler` + `wire_pricing`) + `PricingReadFacade` + migración 151 |
| PRC-7 | UI enterprise (read service, view_models es-MX, presenter, navegación, 5 páginas) |
| PRC-8 | Legacy eliminado: `pricing_service` → shim delegante; DROP diferido; ratchet guardrail |

## 4. Definición de terminado — checklist

- [x] Un solo contexto Pricing/Costing (UUIDv7, Money/Decimal).
- [x] Resolución volumen > cliente > lista > base, con precio mínimo (`below_minimum`).
- [x] Costo promedio ponderado canónico (móvil por evento de compra/producción).
- [x] Query services / facade que sirven a los 44 consumidores.
- [x] Backfill validado (idempotente, Decimal, aditivo).
- [x] UI enterprise sin SQL (Design System JUANIS).
- [x] `pricing_service` legacy reescrito (sin SQL de precio legacy); tablas legacy con DROP diferido.
- [x] `products` sin precio/costo (guardrail de refuerzo).

## 5. Pendientes fuera del contexto Pricing

- **Ejecución del DROP diferido** (`PRICING_ALLOW_LEGACY_DROP=1`): manual, en el corte
  final junto con PROD-19.
- **Repunte físico de lectores de `productos.precio`/`costo`** (BI, forecast, reportes,
  merma, fidelidad, delivery, activos): se ejecuta en **PROD-19 pasos 4-10**, que ahora
  tienen destino canónico (`PricingReadFacade`). Contexto Pricing **desbloqueó** PROD-19.
- **Guardrails repo-wide pre-existentes** ajenos a Pricing (settings pendiente DS-9;
  `test_text_pk_not_null` sistémico en todos los contextos born-clean —
  finance/hr/inventory/supplier/products/pricing por igual): fuera de alcance de PRC-9.

## 6. Conclusión

El bounded context **Pricing / Costing** queda **cerrado y verde** (124/124), born-clean
UUIDv7 + Money/Decimal, con precio y costo canónicos, integraciones event-driven, UI
enterprise y legacy neutralizado. Habilita el cierre de Productos (PROD-19/PROD-20).
