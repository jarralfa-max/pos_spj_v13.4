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

## Remediación D1 — Unificación de caja (paso 1: bloqueo de la ruta canónica)

**Hallazgo (corrige el marco del audit).** La caja NO es "3 servicios en paralelo"
sino una arquitectura EN CAPAS cuya ruta de producción ya es canónica:

```
UI (modulos/caja.py)
  → open_cash_shift_uc / register_cash_movement_uc / generate_z_cut_uc  (use cases)
  → CashRegisterApplicationService   (única emisora de eventos CASH_*)
  → finance_service.{abrir_turno, registrar_movimiento_manual, generar_corte_z}
```

- La UI usa `caja_service` (`CajaApplicationService`) SÓLO para lecturas (KPIs,
  historial, arqueo, estado de turno, movimientos). Sus métodos de **mutación**
  (`abrir_turno`/`registrar_movimiento_manual`/`generar_corte_z`) son un duplicado
  histórico que hoy no está en la ruta de producción (los ejercita `test_caja.py`).
- `finance_service` (ruta canónica) NO emite eventos de caja; `CashRegister` es la
  única emisora `CASH_*`. El bridge `CAJA_* → CASH_*` (Remediación A) sólo republica
  eventos legacy `CAJA_*`, que en la ruta canónica no se emiten → sin doble emisión.

**Duplicación real pendiente:** tres implementaciones de corte Z —
`finance_service.generar_corte_z` (canónica/UI), `CajaApplicationService.generar_corte_z`
(duplicado, muerto en prod) y `CierreCajaService.corte_z` (auto-cierre del scheduler,
`app_container.py:1030`, con impresión + notificaciones propias).

**Paso 1 (este commit) — bloqueo anti-regresión, sin tocar cálculo financiero:**
- `tests/architecture/test_caja_canonical_route.py`: (1) la UI no invoca mutaciones
  de caja directamente sobre el servicio; (2) enruta por los use cases canónicos;
  (3) `CashRegisterApplicationService` emite `CASH_*` y delega la lógica de turno en
  `finance_service`. Fija la ruta correcta para que no regrese a la legacy.

**Pasos siguientes de D1 (con cobertura financiera dedicada, aún no hechos):**
1. Enrutar el auto-cierre del scheduler (`CierreCajaService.corte_z`) por
   `GenerateZCutUseCase`/`finance_service.generar_corte_z`, preservando impresión y
   notificaciones — una sola implementación financiera de corte Z.
2. Deprecar las mutaciones duplicadas de `CajaApplicationService` (migrar
   `test_caja.py` a la ruta canónica) dejándolo como servicio de sólo-lectura.
3. Retirar la publicación de `CAJA_MOVIMIENTO` desde `repositories/caja.py` (los
   repos no publican eventos; lo hace la capa de aplicación).

### D1 paso 2 — Hallazgo: el corte Z canónico está INCOMPLETO (bloquea el re-ruteo)

Al preparar el re-ruteo del auto-cierre del scheduler se descubrió que las dos
rutas de corte Z operan sobre **modelos de datos distintos** y la canónica tiene
un **gap funcional**:

| | Scheduler (`CierreCajaService.corte_z`) | Canónica UI (`finance_service.generar_corte_z`) |
|---|---|---|
| Turno | `turno_actual` (flag `abierto`) | `turnos_caja` (`estado`) |
| Registro de corte | escribe `cierres_caja` | **NO** escribe `cierres_caja` |
| Asiento de diferencia | sí (si recibe finance_service) | **NO** postea asiento |
| Eventos | ninguno | `CASH_Z_CUT_GENERATED` + `CASH_DIFFERENCE` |

- El historial de la UI (`CajaApplicationService.get_historial_cortes`) lee
  `cierres_caja`; los cortes hechos por la ruta canónica NO aparecen ahí.
- Ningún handler de `CASH_Z_CUT_GENERATED`/`CASH_DIFFERENCE_DETECTED` postea el
  asiento de diferencia (el `CashEventAuditHandler` sólo escribe `audit_logs`).

⇒ **Re-rutear el scheduler a la ruta canónica hoy PERDERÍA** el registro en
`cierres_caja` y el asiento de diferencia (violación de Prioridad 0). El paso 2
se reordena:

- **2a (este commit):** red de seguridad — `tests/test_caja_corte_z_characterization.py`
  fija el comportamiento actual de ambas rutas (6 tests). Sin cambios de runtime.
- **2b (siguiente):** completar la ruta canónica para que sea superset — escribir
  el registro `cierres_caja` y postear el asiento de diferencia (idempotente),
  con tests. Sólo entonces:
- **2c:** re-rutear el auto-cierre del scheduler y deprecar `CierreCajaService`.
- **2d:** unificar los dos trackers de turno (`turno_actual` vs `turnos_caja`)
  vía migración de datos.

### D1 paso 2b — ✅ Ruta canónica de corte Z completada (superset)

`finance_service.generar_corte_z` (ruta canónica, usada por la UI vía CashRegister)
ahora, además de cerrar `turnos_caja`:
- Registra el corte en `cierres_caja` (el historial de la UI lo lee) con el desglose
  por forma de pago, anulaciones y diferencia. Idempotente por `turno_id`.
- Postea el asiento de diferencia (`110-caja` / `999-diferencias-caja`, evento
  `CORTE_Z`) best-effort — mismas cuentas que la ruta legacy; el registro de
  historial persiste aunque el ledger falle.
- Devuelve `cierre_id` en el dict de resultado.

Cierra el gap financiero: los cortes Z de la UI ya dejan registro en historial y
asiento de diferencia. Cubierto por `tests/test_caja_corte_z_characterization.py`
(8 tests, schema completo). Sin regresión (unit 26F/252P, integration 107F/128P).

Habilita **2c** (re-rutear el auto-cierre del scheduler a la ruta canónica y
deprecar `CierreCajaService`) y **2d** (unificar `turno_actual`/`turnos_caja`).

### D1 paso 2c — ✅ Auto-cierre del scheduler por la ruta canónica (+ bugfix)

Hallazgo: el auto-cierre de medianoche consultaba `turno_actual` (tracker legacy
cuyo único escritor —`CierreCajaService.abrir_turno`— no se llama en producción),
así que en la práctica NO cerraba turnos reales (viven en `turnos_caja`, abiertos
por la UI vía OpenCashShiftUseCase). Era un no-op: un bug latente.

- Nuevo helper `core/services/caja_auto_close.py::auto_close_open_shifts(db, uc)`:
  cierra cada turno abierto de `turnos_caja` vía la ruta canónica
  (GenerateZCutUseCase → finance_service.generar_corte_z), cierre a ciegas
  (efectivo=0). Devuelve los turno_id cerrados; no lanza. Testeable (extrae la
  lógica del god-object AppContainer, D5).
- `AppContainer._auto_cierre_turno` ahora delega en el helper; ya no usa
  `CierreCajaService` ni `turno_actual`.
- `CierreCajaService` marcado DEPRECADO (se retira en 2d al unificar trackers).

Tests: `tests/test_caja_corte_z_characterization.py` (+3, total 11) — el auto-cierre
cierra el turno canónico y registra `cierres_caja`; no-op sin turnos abiertos; seguro
con uc None. Sin regresión (architecture 35F/221P, unit 26F/252P).

Queda **2d**: unificar los trackers `turno_actual` / `turnos_caja` (migración de
datos) y retirar `CierreCajaService` + los lectores de `turno_actual`
(finanzas_unificadas, caja.py, health_server).

### D1 paso 2d — ✅ Retiro del tracker legacy `turno_actual` de producción

Aclaración del mapa: los presuntos lectores de `turno_actual` (finanzas_unificadas,
finance_read_repository, caja_application_service) en realidad referencian
`cierres_caja`, no `turno_actual`; y `modulos/caja.py::self.turno_actual` es un
atributo de instancia (el turno_id activo), no la tabla. El ÚNICO lector real de la
tabla en producción era el health-check.

- No hay datos que migrar: en producción nadie escribe `turno_actual` (su único
  escritor, `CierreCajaService.abrir_turno`, no se llama).
- `core/health/health_server.py::_health_ready` ahora consulta `turnos_caja`
  (estado='abierto') en vez de `turno_actual`. Corrige un bug latente: el readiness
  reportaba 503 permanentemente (leía una tabla siempre vacía).
- Guardrail `tests/architecture/test_caja_canonical_route.py`: ningún código de
  producción hace SQL contra `turno_actual` salvo `CierreCajaService` (deprecado,
  allowlisted). Bloquea el regreso del tracker legacy.

`turno_actual` queda huérfana y `CierreCajaService` deprecado (sin callers de
producción). Su remoción física (DROP de la tabla + borrado de la clase + migración
de `tests/test_core_services.py`, `test_financial_core_enforcement.py`,
`test_caja.py` a la ruta canónica) queda como limpieza posterior de bajo riesgo.

**D1 cerrado en lo esencial**: la caja tiene una única ruta de turno/corte Z
canónica (turnos_caja + finance_service.generar_corte_z, superset), el scheduler la
usa, y los trackers/servicios legacy están deprecados y bloqueados por guardrails.

---

## Remediación E — KPIs y dashboards event-driven

Contrato: los KPIs se refrescan por EVENTOS, no por timers. El guardrail lo
enforcea y se corrigieron los canales huérfanos que encontró.

Guardrail (T9)
- `tests/architecture/test_kpis_subscribe_real_events.py`: AST sobre modulos/,
  ui/, interfaz/ — cada evento `subscribe(...)` debe tener un emisor `publish`/
  `_publish`/`_publish_safe`/`emit` en el código. Resuelve literales, constantes
  de event_bus/domain_events, `EventName.X.value`, y el patrón `for evt in (…)`.
  Allowlist para emisión dinámica (PRODUCTO_* vía dict-dispatch en catalog_events).

Canales huérfanos corregidos (B6/B10)
- RECETA_CREADA / RECETA_ACTUALIZADA: la UI de producción los escuchaba pero
  nadie los emitía. `RecipeService.create_recipe/update_recipe/deactivate_recipe`
  ahora los publican (best-effort) desde el punto canónico de escritura.
  Cubierto por `tests/test_recipe_events.py`.
- DELIVERY_UPDATE: canal muerto (sin emisor). Retirada la suscripción en
  `modulos/delivery.py`; la recarga ya ocurre por PEDIDO_NUEVO/PEDIDO_ACTUALIZADO/
  VENTA_COMPLETADA. Migrar a DeliveryEvents canónicos es follow-up de delivery.

Timers → fallback
- `finanzas_unificadas._wire_kpi_auto_refresh`: el timer de KPIs baja de 15 s a
  60 s (red de seguridad); el refresh en caliente lo dan los eventos. Test de
  wiring actualizado (estaba rojo por drift de nombres de método).

Nota: reportes_bi_v2 (B6 original) ya se corrigió en Remediación B; el guardrail
lo bloquea. B10 (CXP/CXC): las constantes ACCOUNT_PAYABLE/RECEIVABLE_CREATED son
aliases con el mismo valor string ("CXP_CREADA"/"CXC_CREADA") que la UI escucha —
suscripciones vivas, no huérfanas.

Sin regresión: architecture 35F/223P (+1 guardrail); unit 26F/252P; test de
finanzas KPI wiring 2F→verde.

---

## Remediación F — SQL en UI: ratchet decreciente (paso 1)

`test_no_sql_in_frontend` sólo impedía aumentos. Se cierra el ratchet:

- `SQL_IN_UI_ALLOWLIST` APRETADO a la realidad: **371 → 187** SQL en UI. Las
  extracciones de fases previas + Remediación D (diálogos captura-only) ya habían
  removido ~184 sentencias que el allowlist nunca reflejó. Módulos que llegaron a
  0 y se retiraron del allowlist: finanzas_unificadas (20→0), productos (29→0),
  inventario_local (7→0), transferencias (5→0); grandes bajas: compras_pro
  (58→7), delivery (37→2), clientes (16→1), activos (19→11), ventas (17→5).
- `tests/architecture/test_sql_in_ui_ratchet.py` (T13): exige IGUALDAD exacta
  actual==allowed. Agregar SQL en UI falla; remover SQL obliga a bajar el
  contador; un archivo de UI con SQL fuera del allowlist falla. El objetivo
  terminal de cada contador es 0.

Sin regresión: architecture 35F/224P (+1 ratchet).

Pendiente F (reducciones por módulo, orden de riesgo): growth_engine (33 — es un
servicio de dominio mal ubicado en modulos/, D7 → mover a capa de servicios),
recepcion_qr_widget (29), rrhh (20) / rrhh_turnos (18), loyalty_card_designer
(12), activos (11), resto.

## Remediación F (paso 2) — growth_engine fuera de la capa UI (D7)

`GrowthEngine` era un servicio de dominio puro (sin Qt) mal ubicado en `modulos/`
(D7). Movido a `core/services/growth_engine.py`:

- Sale de la capa UI: −33 SQL y −12 commits del scope UI (SQL-in-UI **187 → 154**).
  Retirado de SQL_IN_UI_ALLOWLIST y COMMIT_ROLLBACK_IN_UI_ALLOWLIST.
- Su DDL runtime (5 CREATE/ALTER) sigue trazado en SCHEMA_CHANGES_OUTSIDE_MIGRATIONS
  con la ruta actualizada (deuda G, aparte).
- Imports actualizados: `modulos/modulo_growth_engine.py` (el wrapper QWidget
  permanece en UI), `core/app_container.py`, test de integración.
- Docstring corregido (decía "Entrada: AppContainer" — no recibe el container).

Sin regresión: architecture 35F/224P; unit 26F/252P; el test de integración de
growth (2F preexistentes por `no such table: growth_ledger`) sin cambios.

## Remediación F (paso 3) — spj_product_search: SQL → ProductoRepository (2→0)

ProductSearchWidget (escáner) ejecutaba 2 consultas de productos directas. Movidas
a ProductoRepository.buscar_exacto_para_scanner / buscar_para_scanner (mismas
consultas y columnas exactas — id, nombre, codigo, codigo_barras, precio,
precio_compra, existencia, unidad). El widget delega; SQL en UI del archivo: 2→0
(retirado del allowlist). SQL-in-UI total 154→152.

Sin regresión: architecture 35F/224P; búsqueda por barcode/código/fuzzy verificada
end-to-end contra el schema base.

## Remediación F (paso 4) — recepcion_qr_widget: escrituras → RecepcionQRService (+2 bugfixes)

Extraída la transacción de recepción y las escrituras de trazabilidad del widget a
`core/services/recepcion_qr_service.py` (SQL en UI 29→14; commits 4→1). La red de
seguridad `tests/test_recepcion_qr_service.py` caracteriza los efectos en BD y
destapó DOS bugs que rompían la recepción por QR:

1. `movimientos_inventario` no tiene columna `uuid` en el esquema born-clean (usa
   `id`) → el INSERT reventaba y la transacción entera hacía rollback: la recepción
   NUNCA se completaba. Corregido a `id` con UUIDv7.
2. Doble conteo de stock: el widget hacía un UPSERT manual de `inventario_actual`
   ADEMÁS del INSERT de movimiento, que dispara el trigger canónico
   `trg_recalc_inventario_actual` (migración 031) → +cantidad dos veces. Ahora el
   stock lo lleva SOLO el trigger; el servicio calcula el costo promedio ponderado
   (con el estado previo) y sincroniza `productos.existencia`.

Verificado end-to-end: 5@40 + 10@50 → 15 uds, costo 46.67, existencia sincronizada,
movimiento de auditoría, trazabilidad 'recibido'. Sin regresión (architecture 35F;
unit 26F/252P; integration 107F/128P). Las 14 lecturas restantes del widget quedan
para un paso siguiente (query service).
