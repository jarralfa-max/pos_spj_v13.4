# FASE SUP-0 — Auditoría del módulo de Gestión de Proveedores

> Auditoría previa a construir el bounded context canónico de proveedores.
> Principio: **un solo maestro de proveedores, múltiples puntos de acceso, una
> sola fuente de verdad.** No duplicar tablas, servicios ni entidades.

Fecha: 2026-07-17.

## 1. Implementaciones existentes (inventario)

| Elemento | Ubicación | Estado |
|---|---|---|
| Tabla `proveedores` (legacy es) | `migrations/m000_base_schema.py` | Mínima: nombre/rfc/telefono/email/direccion/categoria/credito. `id TEXT` (UUID). |
| Tabla `suppliers` (legacy) | `m000_base_schema.py`, `035_finance_erp.py` | Mínima: nombre/rfc/tipo/condiciones/saldo/banco. `id TEXT`, `proveedor_id TEXT`. |
| `supplier_payments` | `backend/infrastructure/db/schema/finance_schema.py` | CxP. `supplier_id TEXT NOT NULL` **sin FK** (opaco). |
| `SupplierQueryService` | `backend/application/queries/supplier_query_service.py` | Envoltura genérica sobre `BaseQueryService` (no read-model real). |
| UI Proveedores | `modulos/proveedores.py` | Wrapper: abre Finanzas y hace `set_active_submodule("cxp")`. No es un maestro. |
| Eventos supplier | `backend/shared/events/event_names.py` | Solo `SUPPLIER_PAYMENT_*` y `SUPPLIER_INVOICE_REGISTERED` (lado finanzas). |
| Integración compras | `backend/infrastructure/db/repositories/compras_*` | Lee proveedor por id opaco. |
| Permisos supplier | — | **No existen** permisos `SUPPLIERS_*`. |

### Conclusión del inventario
- El "maestro" actual es **mínimo y fragmentado** (dos tablas legacy) y no cubre
  el ciclo enterprise (contactos, direcciones, cuentas bancarias verificables,
  condiciones, productos, documentos, evaluación, riesgo, bloqueos, sucursales,
  auditoría).
- Finanzas trata `supplier_id` como **UUID opaco** (sin FK en DB) → un maestro
  canónico nuevo con UUIDv7 es compatible con CxP sin romper pagos.
- La UI de "Proveedores" ya vive **dentro de Finanzas** (regla cumplida): solo
  falta reemplazar el redirect a CxP por la página real del maestro.

## 2. Decisión arquitectónica

- **Bounded context nuevo y canónico:** `backend/domain/suppliers/`,
  `backend/application/suppliers/`, repos en `repositories/` /
  `backend/infrastructure/db/`, esquema propio `supplier_schema.py`.
- **Ubicación UI:** página interna de Finanzas
  (`frontend/desktop/modules/finance/suppliers/`), accesible también desde
  Compras por navegación contextual. **No** se crea menú `PROVEEDORES`
  independiente (ya está integrado en `FINANZAS_UNIFICADAS`).
- **Identidad:** `supplier_id` UUIDv7 (`backend.shared.ids.new_uuid`) +
  `supplier_code` humano estable (`PRV-000001`). El UUID no es la identidad
  visible principal.
- **Esquema (SUP-2):** born-clean. Las tablas mínimas legacy `proveedores` /
  `suppliers` se consideran datos de desarrollo desechables (skill: no rescate).
  El nuevo esquema crea el maestro rico; los lectores legacy de compras/finanzas
  se migran al maestro en SUP-6. `supplier_payments.supplier_id` sigue operando
  con los UUID del maestro (FK opaca).

## 3. Alcance por fases (dependencias)

```
SUP-0  Auditoría (este documento)                         ← ENTREGADO
SUP-1  Dominio (entidades, VOs, estados, bloqueos, policies, eventos) + tests
SUP-2  Persistencia (supplier_schema born-clean, repos, índices)
SUP-3  Aplicación (commands, queries, DTOs, permisos, auditoría, eventos)
SUP-4  UI base (página en Finanzas: header, KPIBar, FilterBar, tabla, estados)
SUP-5  Alta y ficha (formulario, contactos, direcciones, fiscal, condiciones, banco, docs)
SUP-6  Integraciones (compras, recepción, productos, CxP, tesorería, sucursales)
SUP-7  Evaluación y riesgo (scorecard, rating, riesgo, alertas, gráficas)
SUP-8  Seguridad (permisos, segregación, enmascarado, auditoría, exportaciones)
SUP-9  Validación (unit/integración/UI/arquitectura, temas, responsive, a11y)
```

## 4. Reutilización (no duplicar)

- Identidad: `backend/shared/ids.new_uuid` (UUIDv7).
- Inputs UI: Design System SPJ (`TaxIdentifierInput`, `PhoneInput`,
  `AddressInput`, `EmailInput`, `MoneyInput`, `PercentInput`, `TimeRangeInput`,
  `SearchableComboBox`, `EntitySearchInput`, `StandardTable`, `PageHeader`,
  `KPIBar`, `HtmlChartView`, `StatusBadge`, formatters).
- CxP/Tesorería: QueryServices financieros existentes (saldos, vencidos, pagos).
- EventBus + outbox: patrón establecido en finance/HR.

Estado global: **IN_PROGRESS** — SUP-1 (dominio) en construcción.
