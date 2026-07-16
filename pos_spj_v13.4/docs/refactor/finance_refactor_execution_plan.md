# Finance Refactor Execution Plan — Bounded Context Financiero ERP

> Estado global: **MIGRATED** (FASES 0-21 ejecutadas; ver §6 plomería operativa remanente)
> Fecha: 2026-07-16
> Skills aplicados (orden de prioridad): SPJ_REFACTOR_SKILL.md → SPJ_UI_UX_ARCHITECTURE_SKILL.md → SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

---

## 1. Inventario de módulos financieros actuales (LEGACY — a sustituir)

### 1.1 UI (monolito + shims)

| Archivo | Líneas | Problemas detectados |
|---|---|---|
| `modulos/finanzas_unificadas.py` | 3,371 | Monolito de 12 secciones; importa `FinanceReadRepository` directamente desde UI; ~40 colores hex hardcodeados (`_P_PRIMARY = "#b4c5ff"`, `_BADGE_COLORS`, etc.); adapter `_Rows` que simula cursores; instancia servicios (`FinancialDashboardService`) dentro de la vista; publica eventos desde UI (`get_bus()` en líneas 3305/3325) |
| `modulos/finanzas.py` | 15 | Shim → hereda de `ModuloFinanzasUnificadas` |
| `modulos/tesoreria.py` | 15 | Shim → hereda de `ModuloFinanzasUnificadas` |
| `modulos/proveedores.py` | — | `ModuloProveedores(ModuloFinanzasUnificadas)` — hereda del monolito financiero |
| `interfaz/main_window.py:97` | — | Navegación importa `ModuloFinanzasUnificadas as ModuloFinanzas` |
| `interfaz/menu_lateral.py:22` | — | Entrada `"finanzas_unificadas"` |

### 1.2 Servicios legacy (rutas financieras duplicadas)

| Ubicación | Líneas | Nota |
|---|---|---|
| `core/services/finance/` (20 archivos) | 6,657 | `journal_entry_service`, `general_ledger_service`, `treasury_service` (1,081), `accounts_payable_service`, `accounts_receivable_service`, `capital_service`, `erp_financial_service`, `financial_trace_service` (773), `fixed_asset_service`, `reconciliation_service`, `idempotency_service`, `fiscal_engine`, etc. **Todos operan con `float`** (116 usos de `float(`), 0 usos de `Decimal` |
| `core/services/enterprise/finance_service.py` | 1,589 | Servicio ERP "canónico" v13.5 — segunda ruta de asientos (`registrar_asiento`) |
| `core/services/finance_service.py` | 8 | Shim de re-export |
| `application/services/accounts_receivable_service.py` | — | **Ruta CxC duplicada** vs `core/services/finance/accounts_receivable_service.py` |
| `application/services/customer_credit_service.py` | — | Crédito cliente acoplado a CxC legacy |
| `backend/infrastructure/db/repositories/finance_read_repository.py` | 236 | Usado **directamente por la UI** |

### 1.3 Handlers de eventos legacy

- `core/events/handlers/finance_handler.py` (305) — `SaleFinanceHandler`, `CreditSaleFinanceHandler` con `float(payload["total"])`
- `core/events/handlers/financial_trace_handler.py` (181) — traza a `financial_trace_log`
- `core/events/handlers/delivery_finance_handler.py`, `purchase_handler.py`
- `core/events/wiring.py` (1,435) — wiring monolítico; suscribe nómina (`NOMINA_PAGADA`/`PAYROLL_PAID`), traza financiera, CxC

### 1.4 Tablas financieras legacy (multi-generación, contradictorias)

| Migración | Tablas |
|---|---|
| `m000_base_schema.py` | `accounts_payable`, `accounts_receivable`, `cuentas_por_cobrar`, `activos`, `assets`, `asset_maintenance`, `activos_depreciacion`, `production_cost_ledger`, `growth_ledger`, `loyalty_budget_caps` |
| `035_finance_erp.py` | `accounts_payable`, `accounts_receivable` (redefinición) |
| `052_financial_event_log.py` | `financial_event_log` |
| `059_plan_cuentas.py` | `plan_cuentas` |
| `061_fix_finanzas_schema.py` | parches |
| `066_erp_financial_model.py` | `terceros`, `cuentas_financieras`, `catalogo_cuentas_contables`, `documentos_financieros`, `pagos_cobros`, `pagos_cobros_aplicaciones`, `movimientos_financieros`, `ledger_financiero`, `auditoria_eventos`, `cortes_caja_erp`, `conciliaciones_financieras` |
| `082_treasury_tables.py` | `treasury_capital`, `treasury_ledger`, `treasury_gastos_fijos`, **`pagos_cobros` (segunda definición)**, `pagos_cobros_aplicaciones` (dup) |
| `083_financial_traceability_tables.py` | `financial_documents`, `treasury_movements`, `journal_entries`, `fixed_assets`, `asset_depreciation_entries`, `maintenance_records`, `operating_supplies`, `financial_trace_log`, `reconciliation_records` |
| `084_capital_movements.py` | `capital_movements` |

**Diagnóstico:** existen al menos **4 generaciones** de modelo financiero conviviendo
(m000/035 → 059/061 → 066 → 082/083/084), con tablas duplicadas
(`accounts_receivable` vs `cuentas_por_cobrar`; `pagos_cobros` definida 2 veces;
`ledger_financiero` vs `journal_entries` vs `financial_event_log`; `activos` vs
`assets` vs `fixed_assets`; plan de cuentas en `plan_cuentas` y
`catalogo_cuentas_contables`). Importes en columnas `REAL` (float). Ninguna tabla
de asientos tiene líneas debe/haber normalizadas (`journal_lines` no existe).

### 1.5 Integración actual de Fidelidad

- Eventos existentes: `LOYALTY_POINTS_EARNED`, `LOYALTY_POINTS_REDEEMED`, `LOYALTY_CARD_ASSIGNED` (`backend/shared/events/event_names.py`)
- Rutas financieras directas de fidelidad: `core/services/finance/treasury_service.py` y `financial_trace_service.py` referencian loyalty; `loyalty_budget_caps` en m000; `057/092_loyalty_ledger*.py` (ledger operativo)
- No existen: obligaciones contables por puntos, perfiles contables, eventos de expiración/reverso, ni conciliación fidelidad↔contabilidad

### 1.6 Violaciones detectadas

| Violación | Evidencia |
|---|---|
| SQL/repos en UI | `finanzas_unificadas.py` importa `FinanceReadRepository`; adapter `_Rows` simula cursores |
| Colores hardcodeados en UI | ~40 tokens `_P_*` y `_BADGE_COLORS` en `finanzas_unificadas.py` |
| UI publica eventos | `get_bus().publish` desde la vista (líneas 3305, 3325) |
| Floats monetarios | 116 `float(` en `core/services/finance/`; columnas `REAL`; 0 `Decimal` |
| Rutas duplicadas CxC | `application/services/accounts_receivable_service.py` + `core/services/finance/accounts_receivable_service.py` + tablas `accounts_receivable`/`cuentas_por_cobrar` |
| Rutas duplicadas de asiento | `enterprise/finance_service.registrar_asiento` + `finance/journal_entry_service` + `financial_event_log` + `ledger_financiero` |
| Rutas duplicadas tesorería | `treasury_service` (082) + `treasury_movement_service` (083) + `movimientos_financieros` (066) |
| Activos triplicados | `activos` + `assets` + `fixed_assets` |
| Handlers con cuentas hardcodeadas | `CreditSaleFinanceHandler`: "debe=130.1 / haber=401.0" en código |
| Sin doble partida real | `journal_entries` (083) no tiene tabla de líneas; asientos de una pierna |

### 1.7 Infraestructura reutilizable (NO legacy — se conserva)

- `backend/shared/ids.py` — `new_uuid()` UUIDv7 monotónico ✅
- `backend/shared/events/` — `EventName`, `DomainEvent`, `InMemoryEventBus`, dispatcher ✅
- `backend/infrastructure/db/` — `database.py`, `dialect.py`, `transaction.py`, `unit_of_work.py` (`DbApiUnitOfWork`, `ConnectionUnitOfWork`) ✅
- `frontend/desktop/components/` — componentes canónicos existentes ✅
- `migrations/engine.py` — mecanismo canónico de creación de esquema ✅

---

## 2. Arquitectura destino (resumen)

```
backend/domain/finance/            entities, value_objects (Money), policies, services, repository_ports, enums, exceptions
backend/application/
  commands/  dto/  queries/        *_commands.py financieros, DTOs, QueryServices de solo lectura
  use_cases/finance/               un use case por operación canónica
  event_handlers/finance/          handlers idempotentes por evento operativo
backend/infrastructure/db/
  schema/finance_schema.py         esquema born-clean UUIDv7 (única definición)
  repositories/finance/            repositorios concretos
frontend/desktop/modules/finance/  finance_view + presenter + pages/ + dialogs/
```

Principios: doble partida (Σdebe=Σhaber), asientos POSTED inmutables, corrección
solo por reverso, periodos OPEN/SOFT_CLOSED/CLOSED, idempotencia por
`operation_id` + `UNIQUE(source_module, source_document_id, posting_purpose)`,
Money(Decimal) end-to-end, montos como cadenas decimales en eventos, perfiles
contables configurables (nada de cuentas hardcodeadas en handlers),
`CommercialObligation` para fidelidad/cupones/vales/tarjetas de regalo.

## 3. Plan por fases (estado)

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Auditoría + este plan | ✅ COMPLETE |
| 1 | Dominio contable (`Money`, entities, policies, ports, tests doble partida) | ✅ COMPLETE |
| 2 | Esquema limpio UUIDv7 (`finance_schema.py`, sin migrar datos) | ✅ COMPLETE |
| 3 | Repositorios + Unit of Work + atomicidad documento/asiento/obligación/outbox | ✅ COMPLETE |
| 4 | Plan de cuentas, diarios, periodos, cierres | ✅ COMPLETE |
| 5 | Posting engine + perfiles + reversos + outbox + idempotencia | ✅ COMPLETE |
| 6 | Integración Ventas (contado, crédito, descuentos, COGS, devoluciones, medios mixtos) | ✅ COMPLETE |
| 7 | CxC (cobros, aplicaciones, saldos a favor, antigüedad) | ✅ COMPLETE |
| 8 | Compras y CxP (obligación→programación→autorización→ejecución) | ✅ COMPLETE |
| 9 | Tesorería + Caja | ✅ COMPLETE |
| 10 | Conciliación bancaria | ✅ COMPLETE |
| 11 | Presupuestos y control de gasto | ✅ COMPLETE |
| 12 | Capital y activos (CAPEX, depreciación, disposición) | ✅ COMPLETE |
| 13 | Nómina (evento canónico RRHH, un asiento por pago) | ✅ COMPLETE |
| 14 | Inventario, producción y merma | ✅ COMPLETE |
| 15 | Fidelidad (emisión/canje/expiración/reverso + conciliación) | ✅ COMPLETE |
| 16 | Cupones, vales, tarjetas de regalo, saldos almacenados | ✅ COMPLETE |
| 17 | Estados financieros (mayor, balanza, balance, resultados, flujo, capital) | ✅ COMPLETE |
| 18 | Query Services para BI (solo lectura) | ✅ COMPLETE |
| 19 | UI/UX enterprise (`frontend/desktop/modules/finance/`) | ✅ COMPLETE |
| 20 | Eliminación de legacy | ✅ COMPLETE |
| 21 | Validación final + auditorías | ✅ COMPLETE |

## 4. Lista de eliminación (FASE 20)

```
modulos/finanzas_unificadas.py
modulos/finanzas.py                     (→ wrapper delgado hacia frontend/desktop/modules/finance)
modulos/tesoreria.py                    (→ wrapper delgado)
modulos/proveedores.py                  (→ dejar de heredar del monolito financiero)
core/services/finance/ (20 archivos)
core/services/enterprise/finance_service.py
core/services/finance_service.py
application/services/accounts_receivable_service.py
backend/infrastructure/db/repositories/finance_read_repository.py (uso directo por UI)
core/events/handlers/finance_handler.py
core/events/handlers/financial_trace_handler.py
tablas legacy: ver §1.4 (la DB de desarrollo se regenera born-clean; sin migraciones de rescate)
tests legacy de tests/finance/ acoplados a servicios eliminados
```

## 5. Riesgos

1. **Acoplamiento transversal:** ventas/compras/caja/nómina/delivery llaman a
   `finance_service` legacy de forma síncrona dentro de SAVEPOINT; el corte a
   eventos canónicos debe hacerse módulo por módulo sin dejar doble ruta.
2. **`modulos/proveedores.py` hereda del monolito financiero** — requiere separación
   antes de eliminar `finanzas_unificadas.py`.
3. **Wiring monolítico (1,435 líneas)** mezcla prioridades legacy; los handlers nuevos
   se registran vía `backend/shared/events` y el wiring legacy se poda al final.
4. **Base de desarrollo contaminada:** se descarta y regenera (regla de desarrollo,
   sin migraciones de rescate).


## 6. Estado post-FASE 20 — plomería operativa remanente

La ruta contable es ÚNICA: todo asiento pasa por el posting engine del bounded
context. Los adaptadores de `core/events/handlers/finance_handler.py` traducen
los eventos del bus legacy (ventas, cancelaciones, nómina) al contrato canónico.

Permanecen como plomería OPERATIVA (no contable) pendiente del refactor de sus
módulos dueños (Caja/Compras/Producción/Clientes/Delivery):

| Componente | Rol actual | Migra con |
|---|---|---|
| `core/services/enterprise/finance_service.py` | log operativo `financial_event_log` consumido por caja/compras/delivery/loyalty | refactor Caja/Compras |
| `core/services/finance/treasury_service.py` (+`treasury_movement_service`, `general_ledger_service`, `accounts_*_service`) | tesorería operativa de Caja/Compras | refactor Caja |
| `core/services/finance/production_cost_service.py` | costeo operativo de producción | refactor Producción |
| `application/services/accounts_receivable_service.py` + `customer_credit_service.py` | CxC operativa + credit_balance (módulo Clientes); ya SIN asiento propio | refactor Clientes |
| Tablas: `financial_event_log`, `cuentas_por_cobrar`, `accounts_*`, `treasury_*`, `pagos_cobros`, `production_cost_ledger` | estado operativo | cada módulo dueño |

Eliminado en FASE 20: `modulos/finanzas_unificadas.py` (3,371 líneas),
`finance_read_repository.py`, `financial_trace_*` (servicio+handler+wiring),
`erp_financial_service`, `journal_entry_service` (legacy), `capital_service`,
`accounting_engine`, `fiscal_engine`, `third_party_service`,
`fixed_asset_service`, `maintenance_finance_service`,
`operating_supplies_service`, `reconciliation_service` (legacy),
`idempotency_service`, `financial_document_service`, 23 tablas huérfanas
(migración 117) y 22 archivos de tests legacy.
