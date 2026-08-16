# CASH-00 - Auditoria de realidad del bounded context Caja

Fecha: 2026-08-16  
HEAD auditado: `a2742e12c62b00c661f84e3081dbdfca95ed5c09`  
Auditoria historica preservada: `docs/refactor/caja_auditoria_real.md`

## Veredicto FASE 0

Estado: PARCIAL.

Caja ya tiene un bounded context canonico amplio (`backend/domain/application/infrastructure + frontend/desktop/modules/cash_register`) con tests verdes, composition root canonico y schema born-clean. Sin embargo, la auditoria repo-wide todavia encuentra consumidores legacy de efectivo en Ventas/FinanceService/sync/BI/tests historicos que escriben o leen `movimientos_caja`, `turnos_caja`, `cierres_caja` o `turno_actual`.

No declarar CASH-00 como completa hasta que la matriz legacy quede resuelta o formalmente aceptada como fuera de runtime canonico.

## Baseline ejecutado

```text
python -m unittest discover tests\integration\cash_register -v
Resultado: OK, 86 tests

python -m unittest tests.architecture.test_cash_legacy_removed tests.architecture.test_caja_canonical_route tests.architecture.test_cash_register_composition_root tests.architecture.test_cash_app_container_born_clean_wiring -v
Resultado: OK, 7 tests
```

Nota de worktree: existen cambios locales previos en `backend/infrastructure/desktop/cash_register_factory.py` y `tests/integration/cash_register/test_cash_register_factory_active_context.py` correspondientes a la recuperacion persistente del turno activo. Esta auditoria no los revierte.

## Inventario actual por capas

| Area | Pieza | Clasificacion | Evidencia | Observacion |
| --- | --- | --- | --- | --- |
| Module loader | Ruta `caja` via `backend.infrastructure.desktop.cash_register_factory` | REAL | tests architecture legacy/composition OK | No se encontro `modulos.caja` como ruta runtime productiva. |
| Composition root | `cash_register_factory.py` | REAL | factory inyecta presenter, query services, use cases y handlers | Se detecta `active_shift_provider`, pero ahora resuelve desde DB; queda como callback tecnico a vigilar. |
| Frontend canonico | `frontend/desktop/modules/cash_register/*` | REAL/PARTIAL | paginas reales para resumen, turnos, movimientos, arqueo, X/Z, diferencias, entregas, refunds, hardware, sync, notificaciones | UX mejorada, pero no se declara completa hasta cerrar todos los placeholders/deuda visual y validacion manual. |
| Presenter | `CashRegisterPresenter` | REAL/PARTIAL | recibe dependencias explicitas, no AppContainer | Mantiene `active_shift_provider` como mecanismo de consulta; debe evolucionar hacia un resolver explicito si se formaliza FASE 2. |
| Dominio | `backend/domain/cash_register/*` | REAL | entidades, enums, eventos, policies, money/UUID | Cubierto por tests de dominio/integracion. |
| Application | `backend/application/cash_register/*` | REAL | use cases para turnos, ledger, safe drop, conteo, cortes, diferencias, handovers, refunds, sync, notifications | Reglas principales en application/domain; no en PyQt. |
| Repositorios canonicos | `backend/infrastructure/db/repositories/cash_register/*` | REAL | UoW + repos canonicos; tests de atomicidad OK | Repositorios no hacen commit/rollback; UoW es owner. |
| Schema canonico | `migrations/standalone/175_*`, `176_*` | REAL | tests born-clean OK | `cash_*` no depende de `turnos_caja/movimientos_caja`. |
| Permisos | `backend/application/cash_register/permissions.py` | REAL | `CAJA.accion`; role matrix y catalog tests existentes | Guardrails indican no `CASH_*` runtime permissions en Caja canonica. |
| UI capabilities | `capability_resolver.py` + routes | REAL/PARTIAL | rutas usan permisos view/capabilities | Debe seguir revisandose accion por accion contra backend. |
| Sales integration canonica | `backend/application/cash_register/sales_integration.py` | REAL | integration tests cash commercial instruments | Ventas legacy aun tiene rutas directas a `movimientos_caja`. |
| Refund integration canonica | `refund_integration.py` | REAL | tests refund factory wiring OK | Contrato Caja ejecuta compensacion monetaria; Ventas conserva autorizacion comercial. |
| Finance/Treasury events | `backend/application/event_handlers/finance/*` | PARTIAL | routers consumen eventos `CASH_*` | Aun existen lectores legacy de `movimientos_caja` en treasury/BI/finance. |
| Printing | `printing.py`, `printing_repository.py`, renderers | REAL | tests print repository OK | Flujo renderer/queue/audit existe. |
| Offline-first | `offline_sync.py` | REAL | tests offline sync OK | Sync global legacy aun lista `movimientos_caja`. |
| Hardware | `hardware_use_cases.py`, gateways/drivers | REAL/PARTIAL | tests hardware operations OK | Driver real puede requerir validacion manual con dispositivo. |

## Hallazgos legacy o duplicados actuales

| Hallazgo | Clasificacion | Evidencia | Riesgo |
| --- | --- | --- | --- |
| `modulos/caja.py` | MIGRATED/REMOVED | `rg --files ... modulos\\caja.py` no retorno archivo; guardrails OK | Bajo en runtime canonico. |
| `ModuloCaja` runtime | MIGRATED/REMOVED | tests `test_cash_legacy_removed` y `test_caja_canonical_route` OK | Bajo. |
| `backend/application/services/cash_register_application_service.py` | LEGACY/PARTIAL | Orquesta `FinanceService` sobre `turnos_caja/movimientos_caja` | Mantiene arquitectura anterior para tests/compatibilidad; no debe usarse como camino nuevo de Caja canonica. |
| `core/services/enterprise/finance_service.py` | LEGACY/PARTIAL | `get_estado_turno`, `abrir_turno`, `generar_corte_z`, writes `movimientos_caja`, `turnos_caja`, `cierres_caja` | Alto: segunda fuente de verdad si consumidores runtime lo usan. |
| `core/services/sales_service.py` | LEGACY | INSERT directo en `movimientos_caja` | Alto: Ventas puede duplicar efecto economico fuera del ledger canonico. |
| `core/services/sales_reversal_service.py` | LEGACY | movimientos compensatorios en `movimientos_caja` | Alto: reversos fuera de Caja canonica. |
| `repositories/ventas.py` | LEGACY | actualiza `movimientos_caja` para cash drawer reporting | Alto: escritura paralela. |
| `integrations/pos_adapter.py` | LEGACY | INSERT en `movimientos_caja` | Alto si sigue en runtime. |
| `core/services/finance/treasury_service.py` | LEGACY READER | lee `movimientos_caja` para efectivo de sucursal | Medio/Alto: Tesoreria no debe leer tabla legacy como verdad operacional. |
| `backend/application/queries/bi_cash_query_service.py` | LEGACY READER | lee `movimientos_caja` y `cierres_caja` | Medio: BI puede mostrar numeros no canonicos. |
| `sync/sync_engine.py`, `sync/conflict_resolver.py` | LEGACY/PARTIAL | incluyen `movimientos_caja`/`caja_operations` | Medio: sync global puede seguir tratando tablas legacy. |
| `migrations/m000_base_schema.py` | HISTORICO | define `movimientos_caja`, `turnos_caja`, `cierres_caja`, `turno_actual` | Historico permitido, pero no debe ser fuente del bounded context nuevo. |
| `migrations/standalone/024/029/080` | HISTORICO | parchean `movimientos_caja/cierres_caja` | Conservar como historico; no usar como diseño runtime nuevo. |
| Tests legacy root/integration | HISTORICO/PARTIAL | multiples tests crean `movimientos_caja`, `turnos_caja`, `turno_actual` | Deben clasificarse antes de eliminarlos; algunos protegen compatibilidad vieja. |

## Matriz de capabilities

| Capability | UI | Query | Command/UseCase | Domain | Repository/DB | Permission | Integration | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Acceso modulo | routes/workspace | n/a | factory/presenter | n/a | n/a | `CAJA.ver` | module loader | architecture/unit | REAL |
| Resolver sesion/turno actual | presenter/workspace | active context in factory | factory callbacks | CashShift states | `cash_shifts` | session active + branch | restart-safe from DB | integration active context | PARTIAL (formalizar resolver dedicado) |
| Cajas/cajones/terminales | devices page | `device_query_service` | device use cases | CashRegister/CashDrawer/PosTerminal | `cash_registers/cash_drawers/pos_terminals` | `CAJA.caja/cajon/terminal/hardware.*` | hardware gateway | unit/integration/architecture | REAL/PARTIAL |
| Apertura/suspension/reanudacion/pre-cierre | shifts page | `shift_query_service` | shift use cases | CashShift | `cash_shifts`, ledger opening | `CAJA.turno.*` | outbox/events | integration lifecycle | REAL |
| Ledger/movimientos/reversos | movements page | `ledger_query_service` | ledger/movement use cases | CashLedgerEntry | `cash_ledger_entries` | `CAJA.movimiento.*` | outbox/events | integration ledger | REAL |
| Safe drop | movements/handover UI | ledger/handover queries | RegisterSafeDrop + handover use cases | CashHandover/CashLedgerEntry | ledger + handovers | movimiento/entrega perms | notifications/outbox | integration safe drop | REAL |
| Conteo ciego | blind count page | blind count query | blind count use cases | BlindCashCount | counts/count lines | `CAJA.conteo.*` | events/outbox | integration blind count | REAL/PARTIAL UX |
| Corte X | X page | X query | GenerateXCut/print | XCut | cash_cuts/print jobs | `CAJA.corte_x.*` | printing/audit | integration X | REAL |
| Corte Z | Z page | Z query | GenerateZCut/print/notify | ZCut/Difference | cash_cuts/differences/outbox | `CAJA.corte_z.*` | finance/notifications | integration Z | REAL |
| Diferencias | differences page | difference query | explain/review/resolve | CashDifference | cash_differences | `CAJA.diferencia.*` | alerts/WhatsApp | integration difference | REAL |
| Entrega valores | handovers page | handover query | prepare/deliver/receive/dispute | CashHandover | cash_handovers | `CAJA.entrega.*` | treasury boundary events | integration handover | REAL |
| Reembolsos | refunds page | read via presenter | refund integration | CashRefundExecution | refund + ledger | `CAJA.reembolso.*` | sales/finance event | integration refunds/e2e | REAL/PARTIAL |
| Pagos/settlement mixto | no pagina dedicada final | sales integration reads | settlement integration | PaymentRecord/Allocation | payment_records/payment_allocations | `CAJA.pago.*` | Sales -> Caja | integration commercial instruments/e2e | PARTIAL UI |
| Configuracion | settings/config page | config query | ConfigureCashRegister | configuration policies | cash_settings/catalogs | `CAJA.configuracion.*` | notifications limits | integration config | REAL/PARTIAL UX |
| Notificaciones/WhatsApp | notifications page | notification query | prepare/dispatch | alert config | notification tables | `CAJA.notificacion/whatsapp.*` | senders | integration notifications | REAL/PARTIAL |
| Offline/sync | sync page | sync query | sync use cases | outbox envelopes | cash_sync/outbox | `CAJA.sync.*` | transport | integration sync | REAL/PARTIAL transport |
| BI/resumen | overview page | overview query | read-only | n/a | read models from cash tables | `CAJA.ver` | BI consumer | integration overview | REAL/PARTIAL UX |
| Impresion | pages + print use case | print queue repo | PrintCashDocument | print doc VO | print jobs/audit | `CAJA.imprimir/reimprimir` | gateway/renderer | unit/integration | REAL |

## Consumidores externos por revisar/migrar

- Ventas legacy: `modulos/ventas.py`, `core/services/sales_service.py`, `repositories/ventas.py`, `sales_reversal_service.py`.
- POS adapter legacy: `integrations/pos_adapter.py`.
- Finanzas/Tesoreria legacy readers: `core/services/enterprise/finance_service.py`, `core/services/finance/treasury_service.py`, `backend/application/queries/bi_cash_query_service.py`.
- Sync global: `sync/sync_engine.py`, `sync/conflict_resolver.py`.
- Health/auto-close: `core/health/health_server.py`, `core/services/caja_auto_close.py`, `core/app_container.py` comentarios/rutas sobre `turnos_caja`.

## Riesgos priorizados

1. Escrituras legacy a `movimientos_caja` pueden duplicar o divergir del ledger canonico.
2. Lecturas BI/Tesoreria desde `movimientos_caja/cierres_caja` pueden reportar cifras diferentes a `cash_ledger_entries/cash_cuts/cash_handovers`.
3. `CashRegisterPresenter` todavia acepta `active_shift_provider`; aunque el factory ya resuelve desde DB, conviene formalizar `CashOperationalContextService` para cumplir FASE 2 sin ambiguedad.
4. Tests legacy siguen protegiendo rutas anteriores; antes de borrarlos hay que clasificar si son caracterizacion historica o deuda activa.
5. Migraciones historicas conservan tablas legacy por historia del producto; la validacion born-clean de Caja canonica pasa, pero el schema global aun contiene deuda legacy.

## Plan de ejecucion actualizado

1. FASE 1/2: formalizar `CashOperationalContextService` o equivalente y migrar `active_shift_provider` a resolver explicito inyectado.
2. Migrar Ventas/adapter/reversos para que todo efecto de efectivo pase por `backend.application.cash_register.sales_integration` o use cases canonicos.
3. Migrar BI/Tesoreria a eventos/read models canonicos de Caja; prohibir nuevas lecturas a `movimientos_caja`.
4. Mantener guardrails `modulos.caja = 0`, `ModuloCaja = 0`, `CASH_* permissions runtime = 0`.
5. Clasificar tests legacy root: conservar como caracterizacion temporal o retirar cuando el consumidor runtime haya migrado.
6. Re-ejecutar baseline ampliado: Cash integration, e2e cash/caja, architecture cash/caja, sales-cash, finance-cash.

## Evidencia de busquedas

```text
rg --files ... modulos\\caja.py/repositories\\caja.py/cash_register_application_service.py/cierre_caja_service.py
Resultado: sin archivos runtime `modulos/caja.py` ni `repositories/caja.py`; existe servicio legacy `backend/application/services/cash_register_application_service.py`.

rg modulos.caja/ModuloCaja/movimientos_caja/turnos_caja/cierres_caja/turno_actual/active_shift_provider
Resultado: no hay ruta runtime `modulos.caja`; si hay multiples lectores/escritores legacy de tablas de caja antigua y `active_shift_provider` en presenter/factory/tests.
```
