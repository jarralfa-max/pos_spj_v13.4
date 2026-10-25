# Finance Refactor Execution Plan — Bounded Context Financiero ERP

> Estado global: **MIGRATED** (2026-10-22; pendiente con decisión: tránsito de transferencias, §R2.5) — Ronda 2 (FIN-ERP, 2026-10-21): re-auditoría contra el
> «Prompt maestro — refactor enterprise del módulo Finanzas» (37 apartados, FASES 0-20).
> Ronda 1 (2026-07-16, FASES 0-21) y la auditoría FIN-AUD (2026-10-10) siguen abajo como historia.
> Skills aplicados (orden de prioridad): SPJ_REFACTOR_SKILL.md → SPJ_UI_UX_ARCHITECTURE_SKILL.md → SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

---

## Ronda 2 — FIN-ERP (2026-10-21)

### R2.0 Punto de partida medido

- El bounded context ya existe: `backend/domain/finance/` (49 archivos), casos de uso,
  handlers, 16 repositorios, esquema `finance_schema.py`, UI `frontend/desktop/modules/finance/`
  (19 páginas, 14 diálogos). `modulos/` ya no existe en el árbol: no queda monolito que borrar.
- Línea base: 246 pruebas de Finanzas pasan (`tests/unit/finance`, `tests/integration/finance`,
  6 guardias de arquitectura de Finanzas).
- Esta ronda NO reconstruye lo que funciona; cierra lo que el prompt exige y el código no tiene.

### R2.1 Decisiones tomadas por defecto (revisables)

| Tema | Decisión | Motivo |
|---|---|---|
| Vocabulario de permisos | Se mantiene `FINANZAS.<accion>` (estándar del repo: catálogo único, matriz por rol). Cada permiso `finance.*` del prompt §28 tiene su equivalente `FINANZAS.*` (tabla en R2.4). | Dos vocabularios para el mismo módulo serían dos fuentes de verdad. |
| Nombres de eventos operativos | Se conservan los que ya emiten los productores cuando son el mismo hecho: `SALE_CANCELLED` (= SALE_REVERSED), `SUPPLIER_INVOICE_REGISTERED` (= SUPPLIER_DOCUMENT_REGISTERED), `INVENTORY_ADJUSTMENT_REGISTERED` (= INVENTORY_ADJUSTED), `TRANSFER_DISPATCHED` (= TRANSFER_SHIPPED), `PROCESSING_COST_ALLOCATED` (= PRODUCTION_COMPLETED). Se agregan los eventos que Finanzas PRODUCE y faltaban. | El prompt admite «el evento canónico definido en la implementación final»; renombrar productores de otros módulos no aporta y rompe sus contratos. |
| Esquema | Una sola definición born-clean en `finance_schema.py`, sin migración que convierta tablas existentes. Una base de desarrollo con esquema financiero anterior se **rechaza al arrancar** con instrucción de regenerarla (no se adapta). | Prompt §1: «La base local debe poder eliminarse y regenerarse», «no crear migraciones de transformación». |
| Impuestos | Arquitectura configurable (código, tasa con vigencia, regla, perfil contable). Ventas hoy no calcula impuesto (`apply_tax` sin llamadores; precios con impuesto incluido): **no se fuerza un desglose de IVA a Ventas** — la carne es tasa 0 % y decidir la tasa por producto es del negocio. | Prompt §22: «no afirmar cumplimiento fiscal completo». |
| Crédito de clientes | Límites y condiciones siguen en el contexto `customer_credit` (CRM); Finanzas los consulta, no los duplica. | Una sola fuente de verdad. |

### R2.2 Matriz de brechas (apartado del prompt → estado medido)

| § | Exigencia | Estado medido | Acción |
|---|---|---|---|
| 3 | UUIDv7 en toda identidad | Cumple (sin `INTEGER PK`, `lastrowid`, `int(id)` en Finanzas) | Guardia de esquema por PRAGMA |
| 4/8.1 | Plan de cuentas jerárquico | Plano: ninguna cuenta agrupadora, `parent_account_id` siempre vacío | Agrupadoras no contabilizables + padres; reglas: no borrar con movimientos, no cambiar naturaleza usada |
| 8.3 | Asiento manual borrador → validado → publicado; líneas con dimensiones | **No existe asiento manual**: sólo reverso. `JournalEntryDialog` es código muerto. Líneas sin proyecto/cliente/proveedor/empleado/producto/tipo de cambio/base | Casos de uso crear/validar/publicar/cancelar + segregación + diálogo; dimensiones en `journal_lines` |
| 9 | Reapertura con usuario; checklist de cierre | `reopened_by` no se guarda; checklist parcial (sin cajas abiertas, nómina, depreciación, borradores) | Columna + checklist completo con estado por punto |
| 11 | Cobro aplicado a uno o varios documentos; anticipos; saldo a favor; castigo; disputa; promesa; vencido | Un cobro = una CxC; sin anticipo, castigo, disputa, promesa ni estado vencido | `collection_applications`, anticipos (2140), castigo autorizado, disputa, promesas, barrido de vencidos |
| 12 | CxP: prioridad, condiciones, disputa, bloqueo por diferencia de recepción (3 vías), anticipos, pronto pago, retenciones | Ninguno | Columnas + bloqueo + casos de uso |
| 13 | Tesorería: depósitos, retiros, cargos, intereses, saldo insuficiente, número enmascarado | Sólo transferencia; número de cuenta completo; transferencia no valida saldo | Casos de uso + `InsufficientTreasuryFundsError` + enmascarado |
| 14 | Diferencias de caja con `cash_over_account_id` / `cash_short_account_id` | El sobrante usa el rol `breakage_income_account_id` (nombre de otra cosa) | Roles propios |
| 15 | Estados de línea, sugerencias con tolerancia, CSV/XLSX, duplicado de estado, ignorar, ajuste autorizado | Sólo `reconciled` 0/1; captura de texto; sin detección de duplicado | Todo lo listado |
| 16 | Presupuesto: ACTIVE/CANCELLED, versiones, dimensiones, AVAILABLE/WARNING/BLOCKING, pagado; flujo de gasto configurable | Comprometido/devengado sí; sin pagado, sin modo de control, sin flujo de aprobación | Modo de control, pagado, aprobación por reglas, liquidación |
| 17 | Préstamos, retiros de socios, CAPEX; activo con código/categoría/fechas/proveedor; SUSPENDED/SOLD/WRITTEN_OFF; corridas de depreciación | Aportación, capitalización, depreciación y baja sí; resto no | Casos de uso + `depreciation_runs` |
| 18 | Merma y transferencias contabilizadas; tránsito | **Merma nunca llega al mayor** (`LOSS_FINANCE_RECOGNITION_REQUESTED` sin consumidor; `WasteRegisteredHandler` sin suscriptor). Transferencias sin efecto contable | Cablear Mermas; tránsito origen→1160→destino |
| 22 | TaxCode/TaxRate/TaxRule/TaxPostingProfile | No existe | Arquitectura configurable (ver R2.1) |
| 23 | Proyectos, departamentos; consolidado con eliminación interna | Sólo centros de costo/utilidad | Dimensiones + eliminación de cuentas puente |
| 24 | Moneda/tipo de cambio; diferencia de redondeo a cuenta configurada | Moneda única; mezclar se rechaza | Tablas `currencies`/`exchange_rates`, importes base por línea, cuenta de redondeo |
| 25 | Auditoría con antes/después, motivo, sucursal | **No existe bitácora financiera** | `finance_audit_log` escrito por cada comando |
| 27 | Eventos financieros del prompt | Faltan RECEIVABLE_OVERDUE, PAYABLE_SETTLED/OVERDUE, BANK_RECONCILIATION_COMPLETED, EXPENSE_*, FIXED_ASSET_DISPOSED | Agregar y publicar |
| 28 | Permisos del prompt; doble autorización configurable | 24 códigos; faltan cuenta, asiento crear/validar/publicar, crédito, castigo, importación, lectura por área, auditoría, configuración; sin umbral de doble autorización | Catálogo completo + umbrales en configuración |
| 29/30 | Dashboard con 12 KPI + alertas + 10 gráficas ECharts | 6 KPI, sin alertas, **ninguna gráfica** | QueryService + ChartData DTO + `HtmlChartView` |
| 31 | Auxiliares, comparativo, consolidado, exportación | Balanza/balance/resultados/flujo sí; sin auxiliar, comparativo ni exportación | Agregar |
| 32 | Proyección de efectivo separada de la contabilidad | No existe | Modelo de planeación propio |
| 33 | Rentabilidad por sucursal/producto/categoría/cliente/canal | Sólo resultados por sucursal | Hechos de rentabilidad por línea de venta, cuadrados contra el mayor |
| 34 | Errores específicos | Nombres genéricos | Catálogo de errores del prompt |
| 29 | Sin `float` en importes | `money_display` usa `float` | Formato con `Decimal` |

### R2.3 Plan de ejecución (orden del prompt; una fase no avanza con pruebas rojas)

Se registra el avance de cada fase en R2.5.

### R2.4 Permisos `finance.*` del prompt → `FINANZAS.*`

Catálogo único en `backend/application/finance/permissions.py`; el servicio de
comandos exige el código en cada comando y la UI deshabilita (con tooltip que
nombra el permiso) lo que la sesión no tiene. Equivalencia por función:

| Función del prompt (§28) | Código | Segregación / nota |
|---|---|---|
| Acceso al módulo / tablero | `FINANZAS.ver`, `FINANZAS.tablero.ver` | — |
| Exportar | `FINANZAS.exportar` | Cada exportación queda en `finance_audit_log` |
| Plan de cuentas ver / administrar | `FINANZAS.cuenta.ver`, `FINANZAS.cuenta.administrar` | Cuenta con movimientos no cambia de tipo |
| Asiento ver / crear / validar / contabilizar / revertir | `FINANZAS.asiento.ver`, `.crear`, `.validar`, `.contabilizar`, `.revertir` | Quien captura no contabiliza (configurable `journal_review_required`) |
| Periodo ver / cerrar / reabrir / autorizar excepción | `FINANZAS.periodo.ver`, `.cerrar`, `.reabrir`, `.autorizar_excepcion` | Reapertura con motivo y usuario |
| Ajuste en periodo pre-cerrado | `FINANZAS.ajuste.periodo_cerrado` | Sólo SOFT_CLOSED; CLOSED nunca |
| CxC ver / administrar; cobro registrar / aplicar | `FINANZAS.cxc.ver`, `.cxc.administrar`, `.cobro.registrar`, `.cobro.aplicar` | Aplicar a documentos exige su permiso aparte |
| Crédito (disputa, promesa) / castigo | `FINANZAS.credito.administrar`, `FINANZAS.castigo.autorizar` | Castigo con motivo y asiento |
| CxP ver / administrar / desbloquear | `FINANZAS.cxp.ver`, `.cxp.administrar`, `.cxp.desbloquear` | Desbloquear ≠ bloquear |
| Pago programar / autorizar / ejecutar | `FINANZAS.pago.programar`, `.pago.autorizar`, `.pago.ejecutar` | Programa ≠ autoriza ≠ ejecuta (doble control configurable); 2ª autorización sobre umbral configurable |
| Tesorería ver / transferir / movimiento / administrar; capital | `FINANZAS.tesoreria.ver`, `.transferir`, `.movimiento`, `.administrar`, `FINANZAS.capital.registrar` | Saldo suficiente salvo sobregiro pactado |
| Estado de cuenta importar; conciliación operar / ajustar / aceptar diferencia / revertir | `FINANZAS.estado_cuenta.importar`, `FINANZAS.conciliacion.operar`, `.ajustar`, `.aceptar_diferencia`, `.revertir` | Quien importa no ajusta (configurable) |
| Presupuesto ver / crear / aprobar / autorizar exceso | `FINANZAS.presupuesto.ver`, `.crear`, `.aprobar`, `.autorizar_exceso` | — |
| Gasto solicitar / aprobar / devengar | `FINANZAS.gasto.solicitar`, `.aprobar`, `.devengar` | Reglas de aprobación configurables (n aprobadores) |
| Activos ver / administrar / depreciar | `FINANZAS.activo.ver`, `.administrar`, `.depreciar` | — |
| Estados financieros / auditoría | `FINANZAS.estados.ver`, `FINANZAS.auditoria.ver` | — |
| Configuración | `FINANZAS.configuracion.administrar` | Cada cambio con motivo, versionado (perfiles) y auditado |

### R2.5 Avance por fase

- FASE 0 — ✅ auditoría y esta matriz (2026-10-21).
- FASES 1-5 (dominio) — ✅ entidades, value objects, políticas y servicios de dominio de §4-§24 (cuentas jerárquicas, asiento con dimensiones/moneda base/redondeo, periodos, CxC con aplicaciones, CxP con etapas, tesorería, conciliación, presupuesto con niveles de control, gasto, activos, capital, impuestos, monedas, parámetros) + catálogo de excepciones §34. Pruebas: `tests/unit/finance/` (80).
- FASES 6-9 (esquema, repositorios, casos de uso) — ✅ esquema born-clean único (51 tablas) con contrato verificado al arrancar (migración 345); un caso de uso por archivo; bitácora `finance_audit_log` antes/después en cada comando; eventos canónicos por `finance_outbox`.
- FASE 10 (permisos) — ✅ tabla R2.4.
- FASES 11-17 (consultas, estados, tablero, gráficas) — ✅ un query service por área; estados desde asientos contabilizados; tablero 12 KPI + 8 alertas + 10 `ChartDataDTO`; rentabilidad por 7 dimensiones; proyección de flujo separada de lo real.
- FASE 18 (UI) — ✅ 2026-10-22: presenter reescrito (sin conexión; sólo query services + `FinanceCommandService`), 31 páginas en el árbol de §29.1, formularios declarativos (`FieldsDialog`), asiento manual, cobro con aplicación a varias facturas, conciliación lado a lado con importación CSV/XLSX, permisos visuales, exportación auditada, montos con `Decimal`. Pruebas: `tests/integration/finance/test_finance_ui_workspace.py`.
- FASE 6/15 (integraciones) — ✅ 2026-10-22: merma valuada (`LOSS_FINANCE_RECOGNITION_REQUESTED`) entregada por el nuevo despachador de `loss_outbox` y asentada por `LossRecognitionHandler` (Dr merma / Cr inventario); hechos de rentabilidad desde venta (por renglón, cuadran con el mayor), devolución y cancelación; catálogo sembrado al arrancar (`wire_finance`) y ciclo de fondo (merma pendiente, vencimientos, `finance_outbox`). Pruebas: `test_finance_integrations_round2.py`.
- **Pendiente con decisión del usuario — transferencias en tránsito (§18):** ni `TRANSFER_DISPATCHED` ni Inventario publican el costo de lo despachado. Finanzas no inventa valuación (regla de no-fallback), así que el tránsito (origen → 1160 → destino) queda sin asentar hasta que Transferencias/Inventario publiquen el valor de cada despacho y recepción. El perfil `INVENTORY` ya trae `inventory_in_transit_account_id` y `transfer_difference_account_id`.

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
