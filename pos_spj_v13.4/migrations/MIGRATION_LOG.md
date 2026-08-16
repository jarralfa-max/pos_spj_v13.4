# Migration Log — pos_spj v13.4

Registro de decisiones sobre migraciones. Toda fusión, renombre o conflicto debe
documentarse aquí antes del commit.

---

## 196_customer_credit_profile_backfill — 2026-08-16

**Motivo:** CRM-27 (cut-over completo Customer Master, parte 1) — el gate
real de crédito en checkout (`CustomerCreditService.validate_credit`)
leía `clientes.allows_credit`/`credit_limit` directamente; el workflow
moderno `customer_credit` (CRM-8, migración 188) existía pero no tenía
ningún efecto en POS.

**Qué hace:** bridgea todo `clientes` legacy con crédito activo hacia
`customers` (CRM-21) y crea un `customer_credit_profiles` AUTHORIZED
espejo. Idempotente, nunca pisa un perfil ya existente. Ver
`docs/refactor/CRM-27_finance_credit_cutover.md` para el detalle completo.

---

## 193_customers_legacy_customer_bridge — fix de orden — 2026-08-14

**Motivo:** CRM-25 — al aplicar esta migración por primera vez contra una
base de datos de desarrollo REAL (no un bootstrap fresco en memoria, que es
lo único que la ejercitaba hasta ahora), falló con
`sqlite3.OperationalError: no such column: legacy_customer_id`.

**Causa raíz:** `run(conn)` llamaba `create_customers_crm_schema(conn)`
ANTES de agregar la columna vía `_add_column`. En una base con `customers`
ya creada por la migración 181 (es decir, cualquier base real migrada
secuencialmente, no una vacía), el `CREATE TABLE IF NOT EXISTS` de esa
función es un no-op — pero su `CREATE UNIQUE INDEX IF NOT EXISTS
idx_customers_legacy_customer_id ON customers(legacy_customer_id)` es
incondicional y se ejecuta igual, fallando porque la columna todavía no
existe. Nunca se detectó antes porque toda la suite de tests de CRM-13
en adelante usa `full_crm_conn`/bootstraps en memoria, donde la tabla
`customers` se crea POR PRIMERA VEZ ya con la columna incluida.

**Cambio:** se invirtió el orden en `migrations/standalone/
193_customers_legacy_customer_bridge.py::run()` — `_add_column` primero,
`create_customers_crm_schema(conn)` después. Sin cambio de comportamiento
en un bootstrap fresco (la función seguía creando la columna en el primer
`CREATE TABLE`); solo corrige el caso de una base preexistente.

**Verificación:** aplicada exitosamente contra
`data/spj_pos_database.db` (backup previo en el scratchpad de la sesión);
1 cliente legacy existente puenteado correctamente vía
`tools/crm/backfill_legacy_customers.py`.

---

## 193_customers_legacy_identity_bridge — 2026-08-13

**Motivo:** CRM-21 — "Migración de consumidores" (POS, Ventas, WhatsApp,
Delivery, Fidelidad, Finanzas). CRM-13 built a full read-side integration
layer for the Customer Master (`backend/application/customers/queries/*`,
`backend/application/customer_credit/queries/*`,
`sales_event_handlers.py`) but left it deliberately inert: the legacy
`clientes` table (all real production data) and the new `customers` table
(CRM-3, essentially unused in production) are two separate tables with
independently-minted UUIDv7 ids and no bridge between them — named
explicitly as deferred to "CRM-21/22" in three places in the CRM-13 code.

**Cambio:** agrega `customers.legacy_customer_id TEXT` (nullable) +
`idx_customers_legacy_id` (índice único parcial, `WHERE legacy_customer_id
IS NOT NULL`, para no colisionar en NULL entre clientes nativos del nuevo
bounded context). Same idempotent `_add_column` pattern as migration 192.
DDL also added to the born-clean path in
`backend/infrastructure/db/schema/customers_crm_schema.py` so a fresh DB
gets the column from `create_customers_crm_schema()` directly.

**No migra `clientes` en sí.** El puente es de solo lectura/resolución:
`backend/application/customers/use_cases/legacy_identity_bridge_use_cases.py`
añade `ResolveLegacyCustomerUseCase` (resuelve o crea perezosamente una fila
`customers` bridge para un `clientes.id` dado) y
`BackfillLegacyCustomersUseCase` (backfill por lotes, vía
`tools/crm/backfill_legacy_customers.py`). Los seis módulos consumidores
(POS/Ventas, WhatsApp, Delivery, Fidelidad, Finanzas) siguen escribiendo en
`clientes` exactamente igual que antes — reescribir esas rutas de escritura
al nuevo `customers` es trabajo futuro (CRM-22+), explícitamente fuera de
alcance de esta fase por el riesgo de mover datos financieros reales sin una
migración de producción dedicada (CLAUDE.md Prioridad 0).

Investigación confirmó que solo dos consumidores de CRM-13 necesitaban este
puente (`sales_event_handlers.py` vía `RecordCustomerSaleActivityUseCase` y
`CustomerCommercialEligibilityQuery`, ambos leen la tabla `customers`
nueva por id) — las otras tres queries de integración
(`CustomerOrdersSummaryQuery`/`LoyaltyCustomerSummaryQuery`/
`CustomerAccountsReceivableSummaryQuery`) ya funcionan correctamente contra
datos reales al recibir directamente el `cliente_id` legacy, sin traducción
de identidad. Ver `docs/refactor/CRM-21_migracion_consumidores.md`.

---

## 187_meat_processing_bounded_context_schema — 2026-08-12

**Motivo:** PROC-3 — esquema born-clean del bounded context Procesamiento
Cárnico/Meat Processing (núcleo productivo del prompt maestro §1: `ProcessingOrder`,
`ProcessingBatch`, `ProcessExecution`, `MaterialConsumption`, `ProcessOutput`,
`ProcessWeighing`, `YieldReconciliation`), consumido por
`backend/infrastructure/db/repositories/meat_processing/` vía
`MeatProcessingUnitOfWork`. DDL vive en
`backend/infrastructure/db/schema/meat_processing_schema.py` (patrón CRM/Customers:
la migración solo invoca `create_meat_processing_schema(conn)`).
**Tablas:** `processing_orders`, `processing_batches`,
`processing_batch_source_lots`, `process_executions`, `material_consumptions`,
`process_outputs`, `process_weighings`, `yield_reconciliations`,
`meat_processing_authorization_log`, `meat_processing_audit_log`,
`meat_processing_outbox`, `meat_processing_processed_events` (12 tablas nuevas).
**Constraints:** todo `id` es `TEXT PRIMARY KEY` UUIDv7 (REGLA CERO); todo
`operation_id` es `UNIQUE` y `CHECK(operation_id <> id)`; toda columna
cantidad/peso/porcentaje es `TEXT` decimal con `CHECK(CAST(x AS NUMERIC) >= 0)`
(sin `REAL`); `status`/`process_type`/`output_type`/etc. usan
`CHECK (col IN (...))` generado directamente desde
`backend.domain.meat_processing.enums` (no puede haber drift esquema↔dominio);
`process_weighings` fuerza `manual_override=0 OR authorized_by_user_id IS NOT NULL`
(§21) y `stable=1 OR manual_override=1`.
**Impacto:** Solo aditivo — no toca las tablas legacy `producciones`/
`produccion_detalle` (ver `docs/refactor/PROC-0_legacy_audit.md`), que conservan
sus lectores vivos hasta PROC-25. Sin FKs cross-context (product_id/branch_id/
warehouse_id se validan a nivel de aplicación, no de esquema, para no acoplar el
orden de migraciones a Productos/Sucursales/Inventario).

---

## 184_inventory_cold_chain_resolution — 2026-08-10

**Motivo:** INV-9 — resolución operacional de excursiones de cadena de frío
(quién resolvió, cuándo y por qué), consumida por `ResolveTemperatureExcursionUseCase`.
**Tabla:** `inventory_temperature_excursions` — agrega `resolved_by`, `resolved_at`,
`resolution_note` (todas nullable, TEXT).
**Impacto:** Sólo aditivo; `ALTER TABLE ... ADD COLUMN` idempotente (mismo patrón que 180).

---

## 060_depreciacion_acumulada — 2026-04-13

**Motivo:** Fase 3 — acumulado mensual de depreciación por activo y periodo.
**Tabla:** `depreciacion_acumulada` (activo_id, periodo YYYY-MM, monto_mes, acumulado, cuenta_id).
**Constraint:** UNIQUE(activo_id, periodo) — idempotente por diseño.
**Impacto:** Solo aditivo; vincula `activos` → `depreciacion_acumulada` → `plan_cuentas`.

---

## 059_plan_cuentas — 2026-04-13

**Motivo:** Fase 3 — catálogo contable mínimo NIF/SAT para plan de cuentas formal.
**Tabla:** `plan_cuentas` (codigo_sat UNIQUE, nombre, tipo, nivel, padre_id).
**Catálogo:** 41 cuentas 1xx–6xx (Activo, Pasivo, Capital, Ingresos, Costos, Gastos).
**Impacto:** Solo aditivo; base para asientos doble entrada en `finance_service`.

---

## 058_scan_event_log — 2026-04-12

**Motivo:** Fase 2 — auditoría de eventos de escaneo (Plan Maestro).
**Tabla:** `scan_event_log` (raw_code, tipo, contexto, accion, payload, cliente_id, producto_id).
**Impacto:** Solo lectura/escritura de auditoría; sin cambios destructivos.

---

## 057_loyalty_ledger_unificado — 2026-04-12

**Motivo:** Fase 2 — ledger unificado de fidelización (acumulación+canje+reversa).
**Tabla:** `loyalty_ledger` (cliente_id, tipo, puntos, monto_equiv, saldo_post, referencia).
**Tablas existentes preservadas:** `growth_ledger`, `loyalty_pasivo_log`, `historico_puntos`.
**Impacto:** Solo aditivo; no modifica tablas existentes.

---

## 056_print_job_log — 2026-04-12

**Motivo:** Fase 1 Plan Maestro — bitácora de impresión obligatoria.
**Tabla creada:** `print_job_log` (job_id, job_type, plantilla, impresora, folio,
estado, reintentos, total, error_msg, created_at, finished_at).
**Impacto:** Auditoría de cada trabajo de impresión; sin cambios destructivos.
**Registrado en:** `migrations/engine.py` posición 056.

---

## Estado inicial auditado — 2026-04-08

### Migraciones canónicas (en engine.py)

| Número | Archivo canónico | Observación |
|--------|-----------------|-------------|
| 016 | 016_concurrency_events.py | OK |
| 018 | 018_sync_industrial_extension.py | OK |
| 019 | 019_margin_protection.py | OK |
| 020 | 020_system_integrity.py | OK |
| 021 | 021_db_hardening.py | OK |
| 022 | 022_industrial_hardening.py | OK |
| 023 | 023_enterprise_upgrade.py | OK |
| 024 | 024_enterprise_blocks_5_8.py | OK |
| 025 | 025_sync_batch_log.py | OK |
| 026 | 026_final_structural_hardening.py | OK |
| 027 | 027_inventory_hardening.py | OK |
| 028 | 028_sales_transaction_hardening.py | OK |
| 029 | 029_reversals_hardening.py | OK |
| 030 | **030_recetas_industriales.py** | Canónico — ver conflicto abajo |
| 031 | **031_inventory_engine.py** | Canónico — ver conflicto abajo |
| 032 | **032_bi_tables.py** | Canónico — ver conflicto abajo |
| 033 | 033_demand_forecast.py | OK |
| 034 | 034_bi_tables.py | OK |
| 035 | 035_finance_erp.py | OK |
| 036 | 036_whatsapp_rasa.py | OK |
| 037 | 037_product_images.py | OK |
| 038 | 038_transfer_suggestions.py | OK |
| 039 | 039_branch_products.py | OK |
| 040 | 040_qr_reception.py | OK |
| 041 | 041_notification_inbox.py | OK |
| 042 | 042_whatsapp_multicanal.py | OK |
| 043 | 043_price_history.py | OK |
| 044 | 044_cotizaciones.py | OK |
| 045 | 045_performance_indexes.py | OK |
| 046 | 046_comisiones_happy_hour.py | OK |
| 047 | 047_v13_schema.py | OK |
| 048 | **048_v131_hardening.py** | Canónico — ver conflicto abajo |
| 049 | 049_v134_intelligent_erp.py | OK |
| 050 | 050_wa_integration.py | OK |
| 051 | 051_fix_kpi_snapshots.py | OK |

---

## Conflictos resueltos

### Conflicto 030
- **Canónico**: `030_recetas_industriales.py` (97 líneas, crea tabla `recetas`)
- **Huérfano**: `030_recipe_tables.py` (5 líneas, solo contiene comentario de fusión)
- **Decisión**: `030_recipe_tables.py` ya fue vaciado y contiene solo el comentario
  `# 030_recipe_tables.py — FUSIONADO en 030_recetas_industriales.py`.
  No requiere acción adicional. El engine.py usa el canónico.
- **Fecha**: Pre-existente al 2026-04-08

### Conflicto 031
- **Canónico**: `031_inventory_engine.py` (612 líneas, crea tablas de inventario)
- **Huérfano**: `031_inventory_industrial.py` (3 líneas, solo comentario)
- **Decisión**: Igual que 030. Ya resuelto antes de esta auditoría.
- **Fecha**: Pre-existente al 2026-04-08

### Conflicto 032 ⚠️
- **Canónico**: `032_bi_tables.py` (476 líneas, crea tablas BI + producción)
- **Huérfano activo**: `032_meat_production.py` (73 líneas, `run()` real que crea
  `meat_production_runs` y `meat_production_yields`)
- **Problema**: El huérfano tiene `run()` real pero NO está en engine.py, por lo que
  sus tablas pueden no existir en la DB de producción.
- **Decisión 2026-04-08**: Crear `053_meat_production_tables.py` que aplica las tablas
  faltantes de forma idempotente. Se marca `032_meat_production.py` como fusionado.
  Ver migración 053.

### Conflicto 048 ⚠️
- **Canónico**: `048_v131_hardening.py` (97 líneas, columnas sync + `sync_state`)
- **Huérfano activo**: `048_sync_improvements.py` (66 líneas, `run()` real que agrega
  columnas `operation_id`, `uuid` a `event_log` y `sync_outbox`)
- **Problema**: Igual que 032 — el huérfano nunca se ejecutó vía engine.py.
- **Decisión 2026-04-08**: Crear `054_sync_improvements_orphan.py` con ALTER TABLE
  idempotentes. Ver migración 054.

---

## Migraciones nuevas (v13.4 audit)

### 052 — financial_event_log (2026-04-08)
- **Archivo**: `052_financial_event_log.py`
- **Motivo**: Audit trail de operaciones financieras requerido por spec v13.4.
  La tabla `treasury_ledger` existente no tiene campos `cuenta_debe`/`cuenta_haber`
  necesarios para asientos contables de doble entrada.
- **Tablas creadas**: `financial_event_log` + 2 índices

### 053 — meat_production_tables (2026-04-08)
- **Archivo**: `053_meat_production_tables.py`
- **Motivo**: Resolución del conflicto 032. Tablas `meat_production_runs` y
  `meat_production_yields` del huérfano `032_meat_production.py` aplicadas
  de forma idempotente.

### 054 — sync_improvements_orphan (2026-04-08)
- **Archivo**: `054_sync_improvements_orphan.py`
- **Motivo**: Resolución del conflicto 048. Columnas del huérfano
  `048_sync_improvements.py` aplicadas de forma idempotente via ALTER TABLE.

---

## v13.4 wiring + bootstrap fix — 2026-04-08

### Cambios en servicios (solo aditivos)

- **`core/db/connection.py`**: Agregada función `verificar_tablas(conn)` que
  levanta `RuntimeError` si alguna de las tablas críticas
  (`usuarios`, `productos`, `clientes`, `ventas`, `configuraciones`, `inventario`)
  no existe. Usada por `main.py` como check fail-fast post-migraciones.

- **`main.py`**: `inicializar_sistema()` ahora llama `verificar_tablas()` justo
  después de `migrator.up()`. Si las tablas faltan se muestra un diálogo y se
  aborta el arranque en lugar de continuar con DB vacía.

- **`core/services/forecast_engine.py`**: Agregado `generar_forecast_diario()`
  como alias de `run()`. Resuelve el crash del `SchedulerService` que llamaba
  este método inexistente.

- **`core/services/inventory_service.py`**: Agregados alias en español
  `descontar_stock()`, `incrementar_stock()`, `ajustar_merma()` que delegan en
  `deduct_stock()` / `add_stock()` respectivamente.

- **`core/services/enterprise/finance_service.py`**: Agregados
  `registrar_ingreso()`, `registrar_egreso()`, `registrar_perdida()` como
  wrappers de `registrar_asiento()` con cuentas contables predeterminadas.

- **`core/events/wiring.py`**: Agregadas dos nuevas funciones de wiring:
  - `_wire_venta_financiero`: `VENTA_COMPLETADA` → `finance_service.registrar_ingreso`
    (prioridad 50) para generar asiento contable en cada venta.
  - `_wire_merma_inventario`: `MERMA_CREATED` → `inventory_service.ajustar_merma`
    (prioridad 80) para descontar stock físico ante mermas vía evento.

---

## 080 — Caja turno_id FK + índices de rendimiento (2026-05-19)

**Migración**: `080_caja_turno_id_link.py`

**Contexto**: Fase 3/4 del refactor del módulo de caja (clean architecture).
`CajaApplicationService.generar_corte_z()` ahora persiste `turno_id` en
`cierres_caja` para permitir trazabilidad directa entre un corte Z y su turno.

**Cambios de esquema**:
- `cierres_caja`: columna `turno_id INTEGER` (nullable, retrocompatible)
- Índice `idx_cierres_turno` sobre `cierres_caja(turno_id)`
- Índice `idx_mov_caja_turno` sobre `movimientos_caja(turno_id)`
- Índice `idx_mov_caja_fecha` sobre `movimientos_caja(sucursal_id, fecha)`

**Riesgo**: Bajo. Solo agrega columna nullable e índices.

---

## FASE 5 Auditoría Finanzas — Extracción de sub-servicios (2026-05-21)

**Rama**: `claude/fix-finance-audit-AVOoY`

**Contexto**: Auditoría profunda del módulo Finanzas. `FinanceService` (1,921 líneas)
se descompone en tres sub-servicios especializados. FinanceService conserva todos los
métodos públicos como wrappers de compatibilidad hacia atrás (facade pattern).

**Nuevos archivos**:

- `core/services/finance/general_ledger_service.py` — Motor de libro mayor.
  `registrar_asiento()` NO hace commit (el caller decide cuándo confirmar).
  Métodos: `registrar_asiento`, `obtener_ledger`, `generar_poliza_periodo`, `exportar_poliza_periodo`.

- `core/services/finance/accounts_payable_service.py` — CxP canónico.
  Opera sobre tabla `accounts_payable`. `crear_cxp` y `abonar_cxp` hacen commit propio
  (operaciones autónomas). Métodos: `listar`, `summary`, `crear_cxp`, `abonar_cxp`, `historial_pagos`.

- `core/services/finance/accounts_receivable_service.py` — CxC canónico.
  Opera sobre tabla `accounts_receivable`. `crear_cxc` y `cobrar_cxc` hacen commit propio.
  Métodos: `listar`, `summary`, `crear_cxc`, `cobrar_cxc`.

**Cambios en servicios existentes**:

- `core/services/enterprise/finance_service.py`:
  - Bug fix FASE 4: `pagar_nomina` usaba `'efectivo'` hardcodeado → corregido a `metodo_pago`
  - `__init__` inicializa `self._gl` (GeneralLedger), `self._aps` (AP), `self._ars` (AR)
  - `registrar_asiento` delega a `self._gl.registrar_asiento()` con fallback SQL
  - `crear_cxp / abonar_cxp / cuentas_por_pagar` delegan a `self._aps` (marcados DEPRECATED)
  - `crear_cxc / cobrar_cxc / cuentas_por_cobrar` delegan a `self._ars` (marcados DEPRECATED)
  - `obtener_ledger / generar_poliza_periodo / exportar_poliza_periodo` delegan a `self._gl`
  - `registrar_movimiento_manual`: removido `self.db.commit()` interno (era llamado dentro SAVEPOINT)

- `core/services/finance/third_party_service.py`:
  - Agregado `check_duplicate_proveedor(nombre, rfc, telefono, exclude_id)` para validación
    centralizada (antes estaba en `DialogoProveedor` en la UI).

- `core/events/domain_events.py`:
  - Agregadas 7 constantes de eventos financieros con aliases en inglés sobre strings legacy.

- `core/services/finance/financial_dashboard_service.py` (nuevo):
  - `FinancialDashboardService`: elimina SQL directo de `finanzas_unificadas.py`.
  - Métodos: `get_quick_kpis`, `get_credit_info`, `listar_clientes`, `crear_cliente`.

- `modulos/finanzas_unificadas.py`:
  - 4 bloques de SQL directo en UI → reemplazados con llamadas a `FinancialDashboardService`.
  - `DialogoProveedor._guardar()` usa `ThirdPartyService.check_duplicate_proveedor()`.

**Nuevos tests** (60+ tests en rama):
- `tests/test_finance_audit_fixes.py` — 26 tests (bug fix nómina, dashboard service, sin doble CxP/CxC)
- `tests/test_finance_sub_services.py` — 34 tests (GL, AP, AR, delegación de fachada, FASE 8)

**Riesgo**: Bajo. Wrappers legacy preservados. Sin cambio de schema. Sin cambio de UI visible.

---

## Segunda auditoría Finanzas — hallazgos R-01 a R-06 (2026-05-21)

**Rama**: `claude/fix-finance-audit-AVOoY`

**Correcciones**:

- **R-01 — SQL injection en `TreasuryService.balance_general()`**
  `dt_filter = f"AND DATE(fecha) <= '{fc}'"` reemplazado por queries parametrizadas:
  condición condicional construida sobre columnas SQL fijas (`WHERE tipo='ingreso' AND DATE(fecha) <= ?`)
  con `dp = [fc] if fc else []`. Nunca se interpola input del usuario.

- **R-02 — Desync credit_balance/saldo en cancelaciones de crédito**
  `SaleCancelledFinanceHandler` actualizaba `credit_balance` pero olvidaba actualizar `saldo`.
  Ahora actualiza ambas columnas (`credit_balance` y `saldo`) en el mismo UPDATE, manteniendo
  la invariante de sincronización definida en `CreditSaleFinanceHandler`.

- **R-03 — Dead code `SaleCreatedFinanceHandler` eliminado**
  Clase nunca suscrita en `wiring.py`. Si se hubiese activado habría causado doble asiento
  de ingresos junto a `SaleFinanceHandler` (priority=90). Removida per CLAUDE.md: eliminar
  código muerto detectado en auditoría. Referencia: A-04 en FINANZAS_AUDIT_FIX_PLAN.md.

- **R-04 — Parámetros incorrectos en `GestionarFinanzasUC.registrar_asiento_manual()`**
  Llamada a `finance_service.registrar_asiento()` usaba `cuenta_debe=`, `cuenta_haber=`, `descripcion=`
  (API legacy que ya no existe). Corregido a `debe=`, `haber=`, `concepto=`.

- **R-05 — A-02: `TreasuryService._ensure_tables()` movida a migración**
  Las 6 tablas (treasury_capital, treasury_ledger, treasury_gastos_fijos, gastos_futuros,
  pagos_cobros, pagos_cobros_aplicaciones) ahora se crean via `migrations/standalone/082_treasury_tables.py`.
  `_ensure_tables()` es ahora un no-op por compatibilidad con callers legacy.

- **R-06 — `core/events/handlers/__init__.py` actualizados**
  Removida exportación de `SaleCreatedFinanceHandler` que causaba ImportError al importar el módulo.

**Nuevos tests** (23 tests en `tests/test_finance_remaining_fixes.py`):
- TestBalanceGeneralSQLInjection (5 tests) — verifica query parametrizada y rechazo de injection
- TestSaleCancelledHandlerSaldoSync (5 tests) — verifica sincronía credit_balance/saldo
- TestSaleCreatedHandlerRemoved (3 tests) — verifica eliminación de código muerto
- TestFinanzasUCParametros (3 tests) — verifica parámetros correctos en llamadas a registrar_asiento
- TestMigracion082TreasuryTables (7 tests) — verifica creación e idempotencia de tablas

**Total suite finanzas**: 117 tests pasando.

---

## 2026-07-12 — Bugfix/Refactor auditoría funcional (rama claude/pos-spj-refactor-bugfix)

Cambios al schema base (`m000_base_schema.py`) — sin migraciones de rescate,
la DB de desarrollo debe resetearse (born-clean UUIDv7):

- **S-01 — `loyalty_snapshots` reconstruida a forma checkpoint**: columnas
  `cliente_id UNIQUE`, `puntos_actuales`, `nivel`, `visitas`, `importe_total`,
  `ultimo_evento_id TEXT` (UUID), `fecha_snapshot`. Corrige
  `no such column: ls.ultimo_evento_id` del scheduler. La forma anterior
  (visitas_dia/importe_dia…) no tenía lectores.
- **S-02 — `historico_puntos` gana `saldo_actual REAL` y `usuario TEXT`**:
  sus escritores (sale_loyalty_policy, sales_reversal) ya insertaban esas
  columnas; ahora además acuñan `id` con `new_uuid()`.
- **S-03 — `usuarios` gana `intentos_fallidos`, `bloqueado_hasta`,
  `locked_reason`, `updated_at`** en el CREATE base (antes solo por
  ensure_column parcial). Soporta el flujo administrativo de desbloqueo.
- **S-04 — `usuario_permisos` y `usuario_sucursal_permisos` creadas**:
  overrides RBAC por usuario/sucursal con `usuario_id`/`sucursal_id` UUID TEXT.
  Antes no existían y los overrides se ignoraban en silencio.
- **S-05 — Índice único `idx_cxc_venta_unica` en
  `cuentas_por_cobrar(venta_id)`**: garantiza idempotencia de CxC por venta.

Cambios de servicios (fuera de schema) documentados en el PR/reporte:
compras ya no escriben `movimientos_caja` (asiento contra
`capital_operativo`); Corte Z compara solo efectivo esperado vs contado;
`ConfigRepository` sin `int(UUID)`; `SessionContext` con identidad str;
lotes/movimientos_lote con `id` UUIDv7 (sin columna `uuid` ni randomblob);
`new_uuid()` monótono in-process (checkpoints UUIDv7).

### Adendum (misma rama) — saldo de deuda de identidad

- **S-06 — Tabla `anticipos` creada en m000**: antes la creaba
  `api/routers/anticipos.py` con `INTEGER PRIMARY KEY AUTOINCREMENT`
  (doble violación: DDL fuera de migrations + autoincrement). Ahora nace
  UUIDv7 en el schema base y el router solo inserta.
- **Deuda lastrowid saldada**: api/routers (cotizaciones/pedidos/anticipos),
  integrations/pos_adapter, integrations/cfdi — todos acuñan `id` con
  `new_uuid()`. Helper muerto `_lastrowid` eliminado de
  infrastructure/persistence/base.py. Allowlists reducidas a solo
  menciones en docstrings.
- **Contratos API a UUID string**: modelos Pydantic de cotizaciones y
  pedidos transportan `cliente_id`/`producto_id`/`sucursal_id` como str
  (sin defaults `sucursal_id=1`).

### Hotfix post-validación manual (misma rama)

- **114_security_lock_and_canonical_kpi_schema.py** (registrada en engine):
  alinea bases de desarrollo EXISTENTES con el schema nuevo — el engine
  salta m000 en DBs ya migradas (`_already_run`), por lo que
  `locked_reason`, `usuario_permisos`, `anticipos`, la forma checkpoint de
  `loyalty_snapshots` y el índice único de CxC no llegaban a DBs vivas
  ("no such column: locked_reason" al desbloquear). Idempotente; deduplica
  CxC por venta_id conservando la fila más antigua antes de crear el índice.
- **balance_general (TreasuryService)**: "Caja y bancos" ahora suma el
  efectivo operativo de `movimientos_caja` (ventas/ingresos − retiros) y
  "Cuentas por cobrar" suma la CxC canónica `cuentas_por_cobrar` — antes
  leía solo `treasury_ledger`/`accounts_receivable` (vacías) y los KPIs de
  Finanzas quedaban en cero con datos reales.
- **_prov_repo / _history_qs**: convertidos de @property a atributos planos
  asignados en __init__ (la property sin setter chocaba con asignaciones de
  hotfixes locales: "property '_prov_repo' has no setter").

### Lote 4 — Tesorería unificada, identidad de roles, integración financiera

- **S-07 — Roles del sistema born-clean UUIDv7 (m000)**: `_seed_system_roles`
  siembra `roles` + `rol_permisos` con UUIDv7 canónico (SYSTEM_ROLE_UUIDS).
  Se eliminaron de 047 los seeds con id entero 1..6 (identidad legacy) y el
  usuario demo pasó a UUIDv7 + sucursal de instalación. Migración 116 remienda
  DBs existentes (roles enteros → UUIDv7, propagando rol_permisos/usuarios_roles).
  Corrige "role_id must be a canonical lowercase UUIDv7".
- **S-08 — proveedores gana limite_credito/condiciones_pago (m000)**: soporte
  para la política de crédito de proveedor en Compras.
- **Tesorería unificada**: TreasuryService expone register_inflow/outflow
  delegando en un TreasuryMovementService propio (fix "register_outflow
  inexistente" en CapitalService/OperatingSupplies/Maintenance/FinancialTrace).
- **Corte Z → capital**: CashCutCapitalHandler consolida el efectivo del turno
  en treasury_movements (idempotente) al cerrar caja.
- **KPIs financieros**: count_overdue_payables/receivables ahora suman la unión
  canónica (financial_documents + CxP/CxC del POS) — la CxC del POS siempre
  cuenta en KPIs.
- **Historial de puntos del cliente**: fuente canónica loyalty_ledger
  (acumulación/canje por venta), no historico_puntos vacío.

## 2026-07-16 — Migración 117: bounded context financiero born-clean (UUIDv7)

- **Nueva migración `117_finance_bounded_context_schema.py`**: crea el esquema
  canónico de doble partida (24 tablas: accounts, journals, journal_entries +
  journal_lines, fiscal_periods, financial_documents, receivables/collections,
  payables/supplier_payments, treasury_accounts, bank_statements,
  reconciliations, budgets, cost/profit_centers, fixed_assets,
  posting_profiles, commercial_obligations, finance_processed_events,
  finance_outbox). Todo `TEXT PRIMARY KEY` UUIDv7; importes como cadenas
  decimales (`Decimal`, sin `REAL`); idempotencia estructural por
  `UNIQUE(operation_id)` y `UNIQUE(source_module, source_document_id,
  posting_purpose)`.
- **Drop de tablas legacy huérfanas** (sin rescate de datos — regla de
  desarrollo): plan_cuentas, ledger_financiero, documentos_financieros,
  movimientos_financieros, financial_trace_log, reconciliation_records,
  capital_movements, cortes_caja_erp, terceros, cuentas_financieras,
  catalogo_cuentas_contables, pagos_cobros_aplicaciones, cuentas_por_pagar,
  loyalty_budget_caps, asset_depreciation_entries, maintenance_records,
  operating_supplies, conciliaciones_financieras + las versiones legacy de
  journal_entries/journal_lines/financial_documents/fixed_assets (se recrean
  limpias).
- **Conservadas** (escritores operativos vivos, migran con su módulo dueño):
  financial_event_log, cuentas_por_cobrar, accounts_payable/receivable,
  treasury_capital/ledger/gastos_fijos, pagos_cobros, treasury_movements,
  production_cost_ledger, growth_ledger, activos_depreciacion.
- El DDL vive en `backend/infrastructure/db/schema/finance_schema.py`; la
  migración es el único punto de ejecución.

## Compras / Procurement bounded context (PUR-4 → PUR-13)

- **Nueva migración `120_procurement_bounded_context_schema.py`**: crea el
  esquema canónico born-clean de Compras (23 tablas: user/role/branch
  purchase_limits, direct_purchases + direct_purchase_lines +
  direct_purchase_authorizations, purchase_requisitions + lines,
  requests_for_quotation, supplier_quotes + lines, purchase_orders + lines +
  purchase_order_versions, goods_receipts + lines, receipt_discrepancies,
  supplier_invoices + supplier_invoice_matches, purchase_authorization_log,
  procurement_audit_log, procurement_outbox, procurement_processed_events).
  Todo `TEXT PRIMARY KEY` UUIDv7; importes/cantidades como cadenas decimales
  (sin `REAL`); idempotencia estructural por `UNIQUE(operation_id)`,
  `UNIQUE(document_number)` y `UNIQUE(supplier_id, invoice_number)`.
- **Sin colisión con legacy**: los nombres canónicos (direct_purchases,
  purchase_orders, goods_receipts, purchase_requisitions, supplier_invoices…)
  NO chocan con las tablas legacy en español (compras / ordenes_compra /
  recepciones / purchase_requests), que conservan sus lectores vivos hasta que
  migren en PUR-11.
- El DDL vive en `backend/infrastructure/db/schema/procurement_schema.py`; la
  migración es el único punto de ejecución (allowlist en el guardrail
  clean-birth).
- **Separación POS↔Compras (§87)**: el POS detecta necesidades (emite eventos de
  reabasto) y NUNCA ejecuta compras; guardrail
  `tests/architecture/test_pos_does_not_execute_purchases.py`.
- **Integraciones (PUR-11)**: `backend/application/procurement/integrations/`
  publica eventos canónicos (INVENTORY_ADJUSTMENT_REGISTERED, PAYABLE_CREATED,
  SUPPLIER_PAYMENT_SCHEDULED, SUPPLIER_PERFORMANCE_RECORDED) y consume
  necesidades (STOCK_REPLENISHMENT_REQUIRED / PURCHASE_NEED_DETECTED /
  CUSTOMER_ORDER_REQUIRES_PURCHASE) creando solicitudes idempotentes. El pago
  inmediato jamás sale de la caja operativa del POS.

## Compras / Logística — permisos canónicos `MODULO.accion` (migración 177)

- **Problema**: `PurchasePermissions` (`backend/application/procurement/permissions.py`)
  usaba códigos planos (`PURCHASES_REQUISITION_CREATE`) y `LogisticsPermissions`
  (`backend/application/logistics/authorization.py`) usaba
  `logistics.shipment.view` — ninguno con el formato `MODULO.accion` que usa el
  resto del sistema (Ventas, Caja, Mermas, Finanzas) vía
  `core/security/permission_catalog.py::CANONICAL_MODULE_PERMISSIONS` y
  `SessionContext.tiene_permiso()`. Como `rol_permisos`/`usuario_permisos`
  guardan `(modulo, accion)` y jamás sembraron filas con esa forma legacy,
  **todo permiso granular de Compras/Logística fallaba cerrado para cualquier
  rol no-admin** — el bypass `es_admin` era la única vía funcional.
- **Cambio**: se renombraron los *valores* de ambas clases (los nombres de
  atributo Python no cambiaron, así que ningún call site necesitó edición) a
  `COMPRAS.solicitud.crear`, `COMPRAS.orden.aprobar`, `COMPRAS.recepcion.completar`,
  `COMPRAS.factura.conciliar`, `LOGISTICA.embarque.ver`,
  `LOGISTICA.contenedor.sellar`, etc. (77 códigos de Compras, 11 de Logística,
  incluye nuevo `LogisticsPermissions.CONTAINER_SCAN` que antes era un literal
  suelto `"logistics.container.scan"` en `mobile_workflow.py`, sin constante).
  `CANONICAL_MODULE_PERMISSIONS["COMPRAS"]` se amplió con las ~77 acciones
  granulares (antes solo `ver/crear/recibir`) y se agregó
  `CANONICAL_MODULE_PERMISSIONS["LOGISTICA"]`, así Configuración → Seguridad
  puede otorgarlas (`ConfigRepository.permission_matrix()` lee directo del
  catálogo).
- **Migración 177** (`177_compras_logistica_canonical_permissions.py`): NO
  otorga ningún permiso nuevo — no hay filas legacy que preservar (confirmado:
  ningún seed insertó jamás `modulo='PURCHASES'`/`'LOGISTICS'`). Solo normaliza
  defensivamente `modulo` en `rol_permisos`/`usuario_permisos`/
  `usuario_sucursal_permisos` por si algún ajuste manual usó los nombres
  legacy. Un administrador debe otorgar las nuevas acciones granulares
  explícitamente vía Configuración.
- **Refresh de sesión en vivo**: Compras (como todo módulo) se construye en
  `MainWindow._construir_todas_las_pantallas()` ANTES del login, con
  `capabilities()` vacío. Se agregó `PurchasingModuleShell.refresh_permissions()`
  (reconstruye sidebar/rutas/botones desde `capabilities()` sin recrear el
  widget) y se conectó al bucle genérico ya existente en
  `MainWindow._propagar_usuario()` (el mismo que llama
  `set_usuario_actual`/`set_sucursal` en cada widget cargado), que ya se
  re-invoca tanto tras login como tras guardar permisos en Configuración
  (`refresh_module_access()`). `DirectPurchaseCreatePage`/`DirectPurchaseCreateView`
  ganaron su propio `refresh_permissions()` porque son singletons reutilizados
  entre reconstrucciones del shell (no se recrean como las demás páginas).

## Compras — Fase 2 (contratos): sesión, UUID visibles y bloqueo de proveedor

- **UUID mostrado como texto principal (§4C del prompt de remediación)**:
  `EnterprisePurchasingPresenter.session_summary()` mostraba
  `"Sucursal: <uuid>"` (leía `default_branch()`, el id) y la tabla de
  Solicitudes mostraba `branch_id` crudo en la columna "Sucursal". Corregido:
  `session_summary()` ahora usa `session.sucursal_nombre`/`active_warehouse_name`
  reales (con mensaje controlado "Sucursal sin nombre configurado" si faltan,
  nunca el id); `RequisitionReadService.list()` agregó
  `LEFT JOIN sucursales` — mismo patrón ya usado para nombres de proveedor.
  El id sigue siendo la única fuente de verdad para persistencia/auditoría
  (`default_branch()` sin cambios); solo la presentación cambió.
- **Migración `178_proveedores_bloqueo_financiero.py`**: `proveedores` no
  tenía ninguna columna para bloqueo financiero o habilitación de compra —
  `SupplierDirectoryQueryService.get_eligibility()` devolvía
  `purchasing_enabled=True`/`financially_blocked=False` fijos, así que un
  proveedor bloqueado por Finanzas igual pasaba la validación de elegibilidad.
  La migración agrega `bloqueado_financiero`, `motivo_bloqueo` y
  `compras_habilitadas` (idempotente, `DEFAULT 0`/`NULL`/`DEFAULT 1` — ningún
  proveedor existente cambia de estado). `get_eligibility()` ahora lee las
  columnas reales; si una base no ha corrido la migración (schemas de prueba
  mínimos, instalaciones no migradas), degrada al comportamiento anterior en
  vez de fallar. Pendiente de diseño: quién puede bloquear/desbloquear un
  proveedor y desde qué módulo (no se construyó UI para esto todavía).

---

## Compras — Fase 2 (contratos): DTOs del read-model enterprise — 2026-08-05

- **Sin migración de esquema; solo tipos y wiring de aplicación/UI.**
- `backend/application/procurement/dto/enterprise_dtos.py` (nuevo): dataclasses
  `frozen` para las filas y detalles que ya devolvían `dict`/`sqlite3.Row` sin
  contrato — `RequisitionRowDTO`/`RequisitionDetailDTO`,
  `OrderRowDTO`/`OrderDetailDTO`, `InvoiceRowDTO`/`InvoiceDetailDTO`,
  `ReceiptRowDTO`/`ReceiptDetailDTO`, `PurchaseHistoryRowDTO` — mismo patrón
  que `DirectPurchaseRowDTO`/`DirectPurchaseDetailDTO` (Fase 1). Las
  colecciones secundarias de un detalle (`related_documents`, `timeline`,
  `matches`/`comparison` de facturas, `invoices` de una recepción) se dejaron
  como `list[dict]` a propósito — son proyecciones heterogéneas tipo
  bitácora, no la entidad documental en sí; tipar cada una habría sido
  alcance no pedido sin beneficio de contrato real.
- `enterprise_read_services.py` y `purchase_history_read_service.py` — `.list()`
  y `.detail()` ahora construyen y devuelven estos DTOs en vez de `dict`.
- **Bug real encontrado y corregido de paso (no cosmético):**
  `OrderDetailPanel` mostraba `Proveedor: <uuid>` (leía `supplier_id` crudo,
  nunca se unía contra `proveedores`) y `RequisitionDetailPanel` mostraba
  `Solicitante: <uuid>` (`requested_by_user_id` crudo, nunca contra
  `usuarios`). Corregido con el mismo patrón tolerante ya usado para
  proveedor en otras vistas (`_supplier_name()`/`_requester_name()`: lookup
  aparte con `_query_one`, nunca falla el detalle completo si la tabla de
  nombres no existe en un fixture de prueba — degrada a "Proveedor no
  disponible"/"Usuario no disponible", nunca revienta ni inventa un nombre).
- **Bug real encontrado y corregido de paso (crash):**
  `InvoicesPage._selection_changed()` (`enterprise_pages.py`) llamaba
  `self._presenter.invoice_detail(invoice_id)`, método que no existía en
  `EnterprisePurchasingPresenter` — `AttributeError` garantizado al
  seleccionar cualquier factura en la pantalla de Facturas. Se agregó
  `invoice_detail()` (mismo patrón que `order_detail()`, delega a
  `InvoiceReadService.detail()`).
- Consumidores actualizados de acceso por `dict`/`.get()` a atributos de
  dataclass: `document_detail.py` (`RequisitionDetailPanel`,
  `OrderDetailPanel`), `enterprise_pages.py` (`InvoicesPage`),
  `enterprise_dialogs.py` (`ReceiveOrderDialog`).
- Tests actualizados: `test_phase2_canonical_domain.py`,
  `test_enterprise_flow.py` (acceso por atributo donde el tipo cambió;
  `related_documents`/`timeline`/`comparison` internos siguen siendo `dict`,
  sin cambio). `test_enterprise_ui.py` no requirió cambios — solo consume
  `TableViewModel`, no las filas crudas.
- **Verificación:** `pytest tests/unit/procurement tests/integration/procurement`
  `tests/unit/logistics tests/integration/logistics` → 229/229; `pytest
  tests/architecture -k "procurement or purchasing or purchase"` → 43/47
  (los 4 fallos son preexistentes y no relacionados: directorio no
  rastreado `application/purchases`, `EntitySearchInput` ausente en
  `direct_purchase_dialogs.py`, y un bug de encoding en un test bajo
  Windows — ninguno tocado por este cambio); `compileall` limpio.
- **Pendiente del checklist de Fase 2:** "Crear puertos" (arquitectura de
  puertos § 22 del prompt maestro: `ProcurementProductCatalogPort`,
  `SupplierProcurementProfilePort`, `InventoryReceiptPort`,
  `ProcurementFinancePort`, `BranchWarehouseContextPort` — integración con
  Productos/Inventario/Finanzas, no construida todavía) y una auditoría
  fresca de "Corregir firmas" más allá de la que este cambio cubrió de paso.

---

## Compras — Fase 2 (puertos) — 2026-08-06

- **Bug real: una factura conciliada nunca generaba CxP en producción.**
  `MatchSupplierInvoiceUseCase`/`ReleaseInvoiceVarianceUseCase` emitían
  correctamente `ACCOUNT_PAYABLE_CREATE_REQUESTED` → `PAYABLE_CREATED`, y
  `CreatePayableUseCase` existía y tenía tests — pero nada lo suscribía en
  `core/events/wiring.py`. Nuevo `ProcurementPayableBridgeHandler`
  (`backend/application/event_handlers/finance/procurement_payable_bridge.py`)
  suscrito con prioridad 50 (contabilidad/ledger). Se agregó
  `document_number`/`branch_id`/`currency_code` al evento (faltaban para
  poder invocar `CreatePayableUseCase`). Pendiente documentado: el handler
  solo crea la obligación (Payable), no el asiento contable debe/haber —
  no hay enrutamiento de cuenta por `purchase_nature` implementado.
- **`ports.py` + `adapters/product_catalog_adapter.py`**: `ProcurementProductCatalogPort`
  (búsqueda + resolución contra el catálogo canónico `products`, nunca
  `productos`) y `BranchWarehouseContextPort` (tipado sobre
  `WarehouseDirectoryQueryService`, ya existente). Reemplaza el campo de
  texto libre "Código o ID de producto" por `EntitySearchInput` en compra
  directa, solicitudes, órdenes y facturas — cierra el gap de "captura
  manual de ID" señalado en el prompt maestro.
- **Bugs reales encontrados de paso al conectar el picker**: `EnterprisePurchasingPresenter`
  no tenía `supplier_options`, `requisition_detail`, `invoice_document_options`
  ni `invoice_document_profile` — la UI ya los llamaba (crear RFQ, crear
  orden desde solicitud, ver detalle, capturar factura) y siempre fallaba
  con `AttributeError` antes de llegar a la lógica de esos flujos. Al
  agregarlos se destapó una segunda capa: `OrderFormDialog` y
  `DirectPurchaseCreatePage.start_from_requisition` esperaban un `dict`
  donde ahora llega un `RequisitionDetailDTO` (Fase 2 anterior) — corregido
  a acceso por atributo. `CartLineVM` tampoco acepta `purchase_nature`
  (nunca lo aceptó); se quitó ese kwarg inválido.

---

## Compras — Fase 3 (acotada): proveedores y costos — 2026-08-07

Alcance acordado con el usuario: solo los 4 puntos sin migración de
esquema (Unidades y Condiciones de pago en Órdenes quedan pendientes —
`purchase_orders`/`purchase_order_lines` no tienen esas columnas hoy).

- **Bloqueo financiero visible en el picker de proveedores**:
  `SupplierPickerQueryService.search()` ahora expone
  `bloqueado_financiero`/`compras_habilitadas` (migración 178) y los
  presenters muestran "Bloqueado financieramente"/"Compras deshabilitadas"
  como subtítulo — antes el usuario solo se enteraba al fallar el envío.
  **Bug real encontrado al implementarlo**: el primer intento envolvió
  `self._query(...)` en un `try/except OperationalError`, pero `_query()`
  ya atrapa esa excepción internamente y devuelve `[]` — el except nunca
  se ejecutaba y una base sin la migración 178 devolvía **cero
  proveedores** en vez de degradar. Corregido llamando `execute()`
  directo (mismo patrón que `SupplierDirectoryQueryService`).
- **Costo de referencia visible al capturar línea**: `AddCartLineDialog`
  ahora muestra `presenter.price_variance(product_id, costo)` (ya existía
  y tenía tests, pero ninguna pantalla lo invocaba) al seleccionar
  producto o escribir el costo.
- **Conversión de unidades en Órdenes**: `_LinesEditor` gana
  `with_conversion` (solo `OrderFormDialog` — `purchase_order_lines.conversion_factor`
  ya existe y `CreatePurchaseOrderUseCase` ya la lee; Solicitudes y
  Facturas no tienen esa columna, no se agregó ahí).
- **Verificación**: 227 (procurement) + 3 (bloqueo proveedor) + 2 (nuevos,
  UI) tests en verde; regresión cubierta con test explícito para el bug
  del `try/except` muerto.

---

## Compras — Fase 4: flujo documental — Cotizaciones y Adjudicación — 2026-08-07

Auditoría previa contra el checklist "Solicitudes → RFQ → Cotizaciones →
Adjudicación → Órdenes → Compra directa → Documentos relacionados" encontró
que **Cotizaciones y Adjudicación no tenían ninguna pantalla**:
`CaptureSupplierQuoteUseCase`/`AwardSupplierQuoteUseCase` estaban completos
y probados en el backend desde antes, con permisos
`COMPRAS.cotizacion.capturar/comparar/adjudicar` ya en el catálogo, pero
nunca conectados a nada — un comprador podía crear y enviar una RFQ y ahí
se acababa el flujo en la app de escritorio.

- **Nuevo read-model** (`backend/application/procurement/queries/quotation_read_services.py`,
  `.../dto/quotation_dtos.py`): `RfqReadService.list/detail/comparison()`,
  proyecciones SQL puras (nunca reutiliza el `ProcurementUnitOfWork` de
  escritura). `comparison()` rankea por precio unitario dentro de cada
  producto y marca `is_best`; es una ayuda de presentación, no la fuente de
  verdad de qué se adjudica — eso lo sigue decidiendo
  `AwardSupplierQuoteUseCase`/el dominio.
- **`QuotationsPage`** (`frontend/desktop/modules/purchasing/pages/enterprise_pages.py`):
  lista de RFQ (invitados/cotizados/adjudicada) con panel de detalle
  (`RfqDetailPanel` en `document_detail.py`) mostrando invitaciones y
  resumen de cotizaciones por proveedor.
- **`QuoteCaptureDialog`**: captura lo que respondió un proveedor —
  restringido a los proveedores realmente invitados a esa RFQ (nunca
  búsqueda libre), plazo de entrega y líneas (reutiliza `_LinesEditor`).
- **`AwardDialog`**: tabla de comparación producto×proveedor con ★ para el
  mejor precio; un clic por producto elige la línea ganadora — permite
  adjudicación dividida (proveedores distintos por producto), tal como lo
  soporta el dominio (`PurchaseAward`/`PurchaseAwardLine`), no solo "todo
  a un proveedor".
- **Capacidades nuevas**: `quotation_view`/`quote_capture`/`quote_compare`/
  `quote_award` en `PurchasingCapabilities` + `capability_resolver.py`;
  ruta `PurchasingRoutes.QUOTATIONS` en `navigation.py`, gateada por
  `quotation_view` (verdadero si el usuario puede crear RFQ, capturar,
  comparar o adjudicar — no hay un permiso "ver" dedicado en el catálogo
  para RFQ, así que se compone de las acciones).
- **Efecto colateral esperado, ya corregido**: el rol "comprador" en
  `test_purchasing_role_matrix.py` gana la ruta `quotations` (tiene
  `RFQ_CREATE`) — se actualizó el set esperado. El guardarraíl de
  arquitectura `test_shell_exposes_only_implemented_permission_gated_routes`
  tenía "Cotizaciones" en su lista de *labels que no deben existir todavía*
  — se movió a la lista de labels implementados; "Adjudicaciones" se dejó
  en la lista de pendientes porque no es una pantalla propia (es una acción
  dentro de Cotizaciones).
- **Checklist "Documentos relacionados"**: sigue parcial — el panel de
  detalle de Solicitud/Orden ya muestra una lista de documentos
  relacionados, pero no es clicable/navegable. No se tocó en esta vuelta
  (alcance acordado fue solo Cotizaciones/Adjudicación).
- **Verificación**: suite completa de procurement + logistics (256 tests) y
  arquitectura de purchasing (8 tests) en verde; `compileall` limpio sobre
  `backend/`, `frontend/desktop/modules/purchasing/` y los tests tocados.
  Nuevos tests: `tests/integration/procurement/test_quotation_read_services.py`
  (5), más 4 en `test_enterprise_ui.py` cubriendo el flujo RFQ→captura→
  comparación→adjudicación de punta a punta a través del presenter, la
  página headless, y el `AwardDialog`.

---

## Fase 5 (Inventario y finanzas) — auditoría + CxP sin asiento contable — 2026-08-07

Auditoría contra "Recepciones → Movimientos → Facturas → Conciliación →
Cuentas por pagar → Pagos → Estados de integración": **Recepciones,
Movimientos, Facturas, Conciliación y Pagos ya estaban completos** — en
particular, Movimientos ya tiene un handler real
(`CanonicalPurchaseStockEntryHandler`) que entra a inventario con costo
promedio ponderado, y "Cuentas por pagar"/"Pagos" ya tenían pantalla
completa (`AccountsPayablePage`, `PaymentsPage`) con el ciclo Programar →
Autorizar → Ejecutar segregado. Un solo hallazgo real:

- **Bug de integridad financiera: `CreatePayableUseCase` reconocía el pasivo
  (CxP) sin ningún asiento contable.** El único asiento balanceado del ciclo
  de pago ocurría hasta *ejecutar* el pago (Debe CxP / Haber Tesorería) — el
  reconocimiento del pasivo en sí (al conciliar la factura) no generaba
  Debe Inventario/Gasto/Activo, violando la regla #11 de CLAUDE.md. El
  propio código ya documentaba el hueco (`procurement_payable_bridge.py`
  decía explícitamente: "routing it correctly requires the line's
  purchase_nature... which this event does not carry").
- **Causa raíz**: `SupplierInvoiceLine` no tenía `purchase_nature` (a
  diferencia de `PurchaseOrderLine`/`RequisitionLine`/`DirectPurchaseLine`,
  que sí lo tienen) — se perdía en el primer eslabón de la cadena.
- **Fix, en 5 capas**:
  1. `SupplierInvoiceLine.purchase_nature` (default `INVENTORY`, mismo
     patrón que el resto del dominio); `CaptureSupplierInvoiceUseCase` lo
     acepta por línea.
  2. `MatchSupplierInvoiceUseCase`/`ReleaseInvoiceVarianceUseCase` agregan
     subtotales pre-impuesto por naturaleza (`nature_subtotals`) al emitir
     `ACCOUNT_PAYABLE_CREATE_REQUESTED`.
  3. `downstream_translators.on_payable_created` reenvía `nature_subtotals`
     + `tax_total` en `PAYABLE_CREATED` (antes se perdían ahí).
  4. `ProcurementPayableBridgeHandler` postea el asiento de reconocimiento
     (Debe Inventario/Gasto/Activo por naturaleza + Debe IVA acreditable /
     Haber CxP) vía `PostingEngine`, usando `PostingPurpose.SUPPLIER_INVOICE`
     (ya existía en el enum, nunca se usaba). Payloads sin `nature_subtotals`
     (legacy) solo crean el `Payable`, nunca inventan una cuenta.
  5. `finance_bootstrap.py`: el perfil contable `PURCHASE` no tenía
     `expense_account_id` ni `asset_account_id` configurados — se agregaron
     (6130 "Gastos operativos", 1201 "Activo fijo"; `SERVICE` se enruta a
     `expense_account_id`, no tiene cuenta propia).
- **Regresión real encontrada al verificar**: el test existente
  `test_payable_created_reaches_finance_and_creates_real_payable` seguía
  pasando con el fix roto (perfil `PURCHASE` no sembrado → `FinanceDomainError`
  silenciada por el retry-on-failure del outbox dispatcher, que no
  propaga la excepción). Se corrigió sembrando `bootstrap_finance()` en el
  test y agregando `assert summary["failed"] == 0` — sin eso, un fallo de
  posteo queda enmascarado indefinidamente.
- **Entorno**: el `.venv` del proyecto apareció vacío a mitad de esta vuelta
  (solo `pip`) — se reinstalaron `pytest`, `PyQt5`, `cryptography`, `fastapi`,
  `fpdf2`, `matplotlib`, `pillow`, `pydantic`, `requests`, `pyOpenSSL`
  (inferidos de los imports reales del repo; no hay `requirements.txt`).
- **Verificación**: 397 tests de procurement + finance en verde; nuevo test
  de asiento mixto (`test_payable_recognition_entry_routes_by_purchase_nature_and_splits_tax`)
  prueba que una factura con líneas INVENTORY + EXPENSE debita dos cuentas
  distintas, no todo a Inventario.
- **Pendiente explícito**: "Estados de integración" del checklist se dio
  por cubierto con esta auditoría (las integraciones evento-driven
  Compras→Inventario/CxP/Tesorería ya estaban bien cableadas) — no se
  construyó ninguna pantalla nueva de monitoreo.

---

## Fase 6 (UI/UX enterprise): Finanzas y RRHH migran a SideNav/Worklist — 2026-08-08

Auditoría contra "Shell, Sidebar, Worklists, Master-detail, Command bars,
Tablas, Dashboard, Estados visuales, Accesibilidad táctil" — a diferencia de
Fase 4/5, el hueco no era funcional dentro de un módulo sino de
**consistencia del sistema de diseño entre módulos**: Compras/Inventario/
Productos ya usaban los componentes compartidos; Finanzas y RRHH
reimplementaban su propio sidebar (`QListWidget` crudo) y su propio
scaffold de listado (`FinancePage`/`HRPage`, sin paginación ni estados
vacío/error). "Command bars" no existe en ningún lado (no se construyó —
fuera del alcance elegido) y "Accesibilidad táctil" solo existe en el
teclado numérico, no en los botones base (tampoco tocado esta vuelta).

El usuario eligió el alcance grande: migrar Finanzas y RRHH al mismo
patrón, no solo documentar.

- **Nuevo `frontend/desktop/components/worklist_page.py::WorklistPage`** —
  extracción de `_ListPageBase` (que solo vivía dentro de
  `purchasing/pages/enterprise_pages.py`) a un componente genuinamente
  compartido. Soporta dos estilos de hook para no forzar una reescritura de
  las 26 páginas de Finanzas/RRHH:
  - override `_fetch()` (paginado/filtrado — patrón de Compras): el
    `_load()` por defecto lo invoca y llena la tabla.
  - override `_load()` directo (páginas simples — patrón de Finanzas/RRHH):
    llaman `self.set_table(model)` ellas mismas; la base igual decide el
    estado vacío después.
  `searchable`/`paginated` son ahora flags opcionales (default `True`,
  igual que Compras); Finanzas/RRHH los ponen en `False` porque sus
  métodos de presenter no aceptan `query`/`offset` todavía.
- **Compatibilidad de atributos**: las 26 páginas de Finanzas/RRHH ya
  usaban `self.table` (sin guion bajo) y `self._layout` directamente —
  `WorklistPage` expone ambos (alias de `self._table`) para no tener que
  tocar el cuerpo de ninguna página individual. `set_kpis()` sigue usando
  `modulos.ui_components.create_kpi_bar` (no se tocó — fuera de alcance).
  `notify(ok, message)` ahora es el aviso inline de Compras (nunca bloquea
  la pantalla), no `QMessageBox` — es el único cambio de UX visible en las
  26 páginas, y ninguna necesitó edición para adoptarlo (heredado del base).
- **Purchasing**: `_ListPageBase` en `enterprise_pages.py` pasó a ser una
  subclase de una línea (`icon = Icons.PURCHASES`) de `WorklistPage` — cero
  cambio de comportamiento, verificado con la suite completa de Compras.
- **`FinanceView`/`HRView`**: `QListWidget` crudo → `SideNav` (mismo
  patrón de `add_group()`/`add_section()` que usa
  `PurchasingModuleShell`). `FinancePage`/`HRPage` pasaron a ser
  subclases de dos líneas de `WorklistPage` (`searchable = paginated =
  False`). Bug menor de paso: `SideNav.add_group()` estaba definido dos
  veces de forma idéntica en `side_nav.py` — se eliminó el duplicado.
- **Sin capability gating**: se confirmó (no se tocó) que ni Finanzas ni
  RRHH filtran su sidebar por permisos — a diferencia de
  `PurchasingModuleShell`, que sí lo hace vía `visible_routes(capabilities)`.
  Explícitamente fuera del alcance de esta vuelta (es un cambio de
  autorización, no de sistema de diseño).
- **Verificación**: no existía ningún test de UI para Finanzas ni RRHH
  antes de esta vuelta. Se agregaron
  `tests/integration/finance/test_finance_ui_shell.py` y
  `tests/integration/hr/test_hr_ui_shell.py` — construyen la vista real
  contra una base de datos vacía recién sembrada (`bootstrap_finance`/
  `create_hr_schema`) y navegan **cada una** de las 19 + 9 páginas,
  confirmando que cargan sin excepción (ejercita el nuevo camino
  `ViewState.EMPTY` que ninguna tenía antes). Las 27 páginas cargaron a la
  primera, sin necesitar ajustes adicionales — confirma que el diseño de
  compatibilidad de atributos fue correcto.
- **Regresión real encontrada y corregida**: `test_purchasing_desktop_shell.py`
  buscaba los literales `"QSplitter"`/`"itemSelectionChanged"` directamente
  en el texto fuente de `enterprise_pages.py` — dejaron de estar ahí al
  moverse a `worklist_page.py`. Se actualizó el test para leer también el
  nuevo archivo compartido.
- **31 fallas pre-existentes descubiertas, no de esta vuelta**: esta fue la
  primera corrida de `tests/architecture/` completo (sin filtro) en toda la
  sesión — destapó fallas en módulos nunca tocados (Productos, Mermas,
  orquestador de refactor, migraciones de PK, menú lateral, etc.).
  Confirmado con `git status` que ninguno de los archivos involucrados en
  esas 31 fallas está entre los 11 archivos modificados esta vuelta — no
  se investigaron ni corrigieron (fuera de alcance).
- **2026-08-08 — LOSS-23, corte born-clean de Mermas**: eliminadas las rutas
  `waste`/`modulos.merma`, las tablas `mermas`, `inventory_waste_event` y
  `ajustes_inventario`, y las migraciones 097/129 que las recreaban. BI y
  reportes se repuntaron a `loss_cases`, `loss_lines` y
  `loss_classifications`. No hay rescate ni lectura dual; la base de desarrollo
  debe regenerarse. Detalle en `docs/refactor/LOSS_23_LEGACY_REMOVAL_REPORT.md`.
- **2026-08-08 — INV-1, catálogo canónico de permisos de Inventario
  (migración 179)**: `CANONICAL_MODULE_PERMISSIONS["INVENTARIO"]` pasó de un
  stub de 3 acciones (`ver`, `ajustar`, `transferir`) a ~70 acciones
  granulares (`almacen.*`, `ubicacion.*`, `movimiento.*`, `lote.*`,
  `reserva.*`, `conteo.*`, `ajuste.*`, `cuarentena.*`, `calidad.*`, `peso.*`,
  `bascula.*`, `recepcion.*`, `reposicion.*`, `temperatura.*`,
  `configuracion.*`, etc.), igualando el patrón ya usado por `COMPRAS`.
  `InventoryPermissions` (`backend/application/inventory/permissions.py`)
  cambió sus ~70 valores de `INVENTORY_*` (inglés) a `INVENTARIO.accion`
  (español canónico) manteniendo los mismos nombres de constante — cero
  cambios en los call sites que ya usaban `InventoryPermissions.X`.
  `InventorySessionPermissionChecker` perdió su puente
  `legacy_codes_for()` (que concedía cualquier mutación granular a quien
  tuviera el permiso legacy grueso `inventario.editar`, y cualquier lectura a
  `inventario.ver`) — ahora exige el código canónico exacto directamente en
  la sesión, igual que `ProcurementSessionPermissionChecker`. La migración
  179 es defensiva/documental como la 177: normaliza `modulo='INVENTORY'` →
  `'INVENTARIO'` si existiera, y **no** expande automáticamente
  `inventario.editar`/`ajustar`/`transferir` a las acciones granulares
  nuevas (escalamiento de privilegios prohibido) — un administrador debe
  otorgarlas explícitamente vía Configuración → Seguridad. Se retiraron
  también las 8 constantes `TRANSFER_*` no usadas por ningún caso de uso
  (el workflow de transferencias vive en el bounded context Transferencias,
  ver `docs/refactor/TRF-0_transfers_audit_and_plan.md`); la única gestionada
  por Inventario ahora es `IN_TRANSIT_VIEW` (`INVENTARIO.transito.ver`,
  sólo lectura). Se agregó `frontend/desktop/modules/inventory/capability_resolver.py`
  (`InventoryCapabilities`, mismo patrón que Compras) y se cableó
  `visible_entries()` (existía pero nadie la invocaba) en
  `page_registry.build_page_specs()`/`modulos/inventario_enterprise.py` para
  que la navegación lateral realmente oculte secciones sin permiso.
