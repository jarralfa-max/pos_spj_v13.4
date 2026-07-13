# Migration Log — pos_spj v13.4

Registro de decisiones sobre migraciones. Toda fusión, renombre o conflicto debe
documentarse aquí antes del commit.

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
