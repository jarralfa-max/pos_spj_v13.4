# PROD Fase 11 — Reporte de aceptación del contexto Productos

Cierre del bounded context canónico de **Productos / Product Master Data** bajo la
REGLA CERO (UUIDv7), Decimal-only, master-data-driven, event-driven y el Design
System JUANIS. Este reporte fija la evidencia de validación, el estado honesto del
corte de legacy (repoint-to-zero) y el camino seguro al DROP.

_Fecha: 2026-07-30 · Rama: `claude/erp-financial-bounded-context-uqxz6b`._

---

## 1. Alcance construido (PROD-0 → PROD-20)

El maestro canónico vive en `backend/{domain,application,infrastructure}/products`
+ `frontend/desktop/modules/products`, mismo patrón que Finance / RRHH / Supplier /
Procurement / Inventory. Capacidades cerradas y verdes:

| Bloque | Estado | Evidencia |
| ------ | ------ | --------- |
| Seguridad: 60 permisos granulares `PRODUCTS_*`, `ProductsAuthorizationPolicy` (segregación crea≠aprueba, alcance por sucursal, autorización en caliente), auditoría `ProductAuditEntry` | ✅ | PROD-1 |
| Product Master (UUIDv7, **sin existencia/precio**, 25 `ProductType`, ciclo de vida) + VOs `ProductCode`/`ProductName` + eventos `PRODUCT_*` | ✅ | PROD-2 |
| Clasificación cárnica **multi-especie** (species/regiones/cortes jerárquicos) | ✅ | PROD-3 |
| Esquema born-clean `products_schema.py` (TEXT PK UUIDv7, sin REAL, catálogos por FK) + migración 136 | ✅ | PROD-4 |
| Unidades + peso variable (conversiones Decimal, catch-weight, scale barcode) | ✅ | PROD-5 |
| Productos internos / WIP / semi-terminados | ✅ | PROD-6 |
| Barcodes + códigos alternos (checksum GS1, unicidad de activos) | ✅ | PROD-7 |
| Calidad / vida útil / logística (cadena de frío) | ✅ | PROD-8 |
| Recetas versionadas (DRAFT→…→ACTIVE, inmutable, explosión Decimal) | ✅ | PROD-9 |
| Rendimientos multi-especie (tolerancia configurable) | ✅ | PROD-10 |
| Despiece multi-especie | ✅ | PROD-11 |
| Preparación para sacrificio (contratos solo-lectura) | ✅ | PROD-12 |
| Combos / paquetes (virtual/stocked, versionado) | ✅ | PROD-13 |
| Sucursales y canales (`branch_product` sin precio/stock, surtidos) | ✅ | PROD-14 |
| Catálogos externos (Open Food Facts, supplier, CSV) + **cliente HTTP real OFF** | ✅ | PROD-15 + §15 |
| Notificaciones + WhatsApp (severidad, throttle, detectores) | ✅ | PROD-16 |
| Integraciones por `product_id` (Inventory/Purchase/POS/Quality) + guardrail de fronteras | ✅ | PROD-17 |
| UI/UX enterprise (presenter sin SQL, navegación sidebar, páginas JUANIS) | ✅ | PROD-18 |
| Categorías jerárquicas, marcas, atributos+variantes, imágenes, import CSV/XLSX | ✅ | P1-01..P1-03, import |

**Fronteras garantizadas por guardrails:** Productos define *qué es* un artículo;
no almacena existencia, no registra movimientos, no ejecuta producción/sacrificio,
no calcula precio final, no contabiliza.

## 2. Evidencia de validación (esta sesión)

- **Suite de Productos:** `tests/unit/products` + `tests/integration/products` →
  **575 passed**.
- **Bootstrap limpio:** `scripts/bootstrap_db.py` → **147 migraciones** ejecutadas,
  cobertura 80.0 %, sin migraciones pendientes.
- **Integridad referencial:** `PRAGMA foreign_key_check` → **sin violaciones**.
- **Guardrails de arquitectura de Productos (verdes):**
  `test_productos_guardrails`, `test_products_integration_boundaries`,
  `test_products_unit_is_uuid`, `test_sql_in_ui_ratchet`,
  `test_pricing_context_has_no_legacy_price_reads`,
  `test_products_legacy_consumers_ratchet`, y el nuevo
  `test_products_pk_not_null`.

### Invariantes probados

- UUIDv7 como única identidad (`test_products_unit_is_uuid`, sin `int(_id)`).
- Decimal-only en cantidades/factores (sin REAL en el esquema de Productos).
- Sin SQL en la UI (`test_sql_in_ui_ratchet`, host de Productos = 0 coincidencias).
- Product Master sin existencia ni precio (guardrails de fronteras).
- Precio → Pricing, existencia → Inventory (query services canónicos).
- **PK TEXT del contexto Productos nunca admite NULL** (`test_products_pk_not_null`).

## 3. Fase 11 — acciones de cierre (esta sesión)

1. **Regresión born-clean corregida (PROD-8):** los perfiles
   `product_catch_weight_config`, `product_quality_profiles` y
   `product_logistics_profiles` nacieron con `product_id TEXT PRIMARY KEY` sin
   `NOT NULL`; como todas sus demás columnas tienen default, un `INSERT DEFAULT
   VALUES` colaba una fila con PK NULL. Corregido a `TEXT NOT NULL PRIMARY KEY` en
   `products_schema.py` + **migración 165** (rebuild guardado por introspección,
   idempotente, preserva datos, `foreign_key_check` OK).
2. **Guardrail de alcance:** `test_products_pk_not_null` fija en cero el invariante
   "ninguna tabla de `PRODUCT_TABLES` admite PK NULL".

Con esto, el smoke global `test_insert_default_values_never_yields_null_pk_smoke`
pasó de **4 → 1** ofensores; el único restante es `historico_puntos.id` (Fidelidad,
fuera del contexto Productos — ver §5).

## 4. Corte de legacy (repoint-to-zero) — estado honesto

El objetivo del corte es dejar en **cero** los consumidores de la tabla legacy
`productos` para poder ejecutar el DROP destructivo (paso 10 de
`products_legacy_removal_report.md`).

- **Ratchet armado y honesto:** `test_products_legacy_consumers_ratchet` congela la
  allowlist en **74 archivos** que aún leen `productos` por SQL directo. El guardrail
  garantiza que la lista **sólo puede decrecer** (no se admiten nuevos consumidores)
  y que **no tiene entradas obsoletas** (al repuntar un archivo se borra de la lista).
- **DROP bloqueado:** aún hay 74 consumidores vivos (POS/Ventas/Compras/Producción/
  BI/forecast/CFDI). El DROP es irreversible y sólo se ejecuta con allowlist vacía.

### Camino seguro a cero (lección INV-27)

Repuntar **lecturas** de catálogo a `products` mientras las **escrituras** del
maestro siguen en `productos` produce lecturas obsoletas → regresión. El orden
seguro, ya establecido en el removal report, es:

1. **Flip de escritura** del maestro a `products` — **hecho** (paso 7b:
   `ProductMasterRepository` + `Create/UpdateProductMasterUseCase`, escribe y lee el
   mismo maestro `products`).
2. **Backfills aditivos** de recetas (152) y rendimientos (153) legacy → canónico —
   **hechos**.
3. **Repunte incremental de lecturas** de cada consumidor a `products` /
   `ProductCatalogReadService` / `PricingReadFacade` / `inventory_balances`,
   borrándolo de la allowlist con verificación de cero regresiones — **pendiente
   (74 → 0)**. Es un esfuerzo multi-incremento sobre la app viva; no debe hacerse en
   un solo commit.
4. **DROP** de ~20 tablas legacy (env-guard `PRODUCTS_ALLOW_LEGACY_DROP=1`) — cuando
   la allowlist quede vacía.

## 5. Residuos conocidos (fuera del alcance de Productos)

- **`historico_puntos.id` (Fidelidad):** único ofensor restante del smoke global de
  PK NULL. Pertenece al contexto Fidelidad/Loyalty, no a Productos.
- **`test_all_single_column_text_pk_are_not_null` (sistémico):** la mayoría de las
  tablas born-clean de **todos** los módulos (finance, hr, inventory, supplier,
  procurement, transfers, pricing y products) declaran `id TEXT PRIMARY KEY` sin
  `NOT NULL`. Es un **riesgo residual documentado** (`cierre_global.md §6`),
  mitigado en la práctica porque las demás columnas NOT NULL rechazan un INSERT sin
  PK; el smoke de `DEFAULT VALUES` es la prueba dura y ya está acotada. Endurecer
  las ~178 tablas a `NOT NULL` es un cambio transversal, no específico de Productos.
- **74 consumidores legacy de `productos`:** ver §4; su repunte es incremental.

## 6. Veredicto

El contexto **Productos está funcionalmente completo y validado** (575 tests,
bootstrap limpio, FK OK, guardrails verdes, invariantes born-clean de Productos en
cero). El **corte atómico de legacy** tiene la escritura ya flipada y los backfills
hechos; resta el repunte incremental de 74 lecturas antes del DROP — trabajo
acotado por el ratchet y seguro de ejecutar por lotes sin romper la app viva.
