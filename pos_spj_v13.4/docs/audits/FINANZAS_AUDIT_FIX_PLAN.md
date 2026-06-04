# FINANZAS_AUDIT_FIX_PLAN.md — SPJ POS v13.4
**Fecha:** 2026-05-21  
**Rama:** `claude/fix-finance-audit-AVOoY`  
**Alcance:** Corrección de hallazgos en módulo de Finanzas sin romper funcionalidad existente

---

## 1. HALLAZGOS CONFIRMADOS

### CRÍTICOS (bugs reales / riesgo de datos)

| ID | Hallazgo | Archivo | Línea | Impacto |
|----|----------|---------|-------|---------|
| F-01 | `pagar_nomina` inserta siempre `'efectivo'` ignorando el parámetro `metodo_pago` | `finance_service.py` | 977 | Datos incorrectos en historial nómina |
| F-02 | SQL directo en UI — KPI bar hace 3 SELECTs directos a DB | `finanzas_unificadas.py` | 505–512 | Acoplamiento UI↔schema, sin caché |
| F-03 | SQL directo en UI — Validación límite crédito CxC | `finanzas_unificadas.py` | 1217–1220 | Lógica de negocio en presentación |
| F-04 | SQL directo en UI — INSERT cliente nuevo | `finanzas_unificadas.py` | 1283–1291 | Sin validación, sin evento, sin use case |
| F-05 | SQL directo en UI — SELECT clientes activos | `finanzas_unificadas.py` | 1297–1300 | Duplica lógica de repositorio |
| F-06 | Validación de duplicados de proveedor en UI (`_verificar_duplicado`) | `finanzas_unificadas.py` | 139–175 | Lógica de negocio en `DialogoProveedor` |

### ARQUITECTURALES (no producen bug inmediato, riesgo de mantenimiento)

| ID | Hallazgo | Impacto |
|----|----------|---------|
| A-01 | `FinanceService` tiene 1,921 líneas — mezcla CxP, CxC, nómina, activos, dashboard | Difícil mantener/testear unitariamente |
| A-02 | `TreasuryService._ensure_tables()` crea tablas en runtime | Debe moverse a migraciones |
| A-03 | Categorización de gastos por `LIKE '%fijo%'` en SQL | Frágil ante cambios de texto |
| A-04 | `SaleCreatedFinanceHandler` definido pero **NO suscrito** en `wiring.py` | Código muerto; intención incierta |
| A-05 | Doble columna de saldo en `clientes`: `credit_balance` (backend) y `saldo` (legacy UI) | Sincronización manual en `CreditSaleFinanceHandler` |

### RIESGO DE DOBLE ASIENTO (análisis de rutas)

| Flujo | Rutas activas | ¿Doble asiento? | Estado |
|-------|--------------|-----------------|--------|
| Venta contado | `SaleFinanceHandler` (SALE_ITEMS_PROCESS p=90) → `register_income` | No — `SaleCreatedFinanceHandler` NO está suscrito en wiring | ✅ OK |
| Venta crédito | `CreditSaleFinanceHandler` (SALE_ITEMS_PROCESS p=85) → CxC + asiento | No — `registrar_ingreso` excluye `Credito` en `SaleFinanceHandler` | ✅ OK |
| Compra crédito | `PurchaseFinanceHandler` (PURCHASE_CREATED p=80) → asiento | No duplicado detectado | ✅ OK |
| Venta cancelada | `SaleCancelledFinanceHandler` (VENTA_CANCELADA async) → reversal | Un solo handler registrado | ✅ OK |

> **Nota:** `SaleCreatedFinanceHandler` existe en `finance_handler.py` pero **no está subscrito** en `wiring.py`. Si en el futuro se subscribe, generaría doble asiento de ingresos para ventas contado. Documentado como A-04 y pendiente de decisión.

---

## 2. RIESGOS

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| Romper UI al extraer SQL | Media | Alto | Tests de regresión antes de refactor |
| Doble CxC si se activa `SaleCreatedFinanceHandler` | Baja (no está suscrito) | Alto | Documentar, no suscribir sin análisis |
| Pérdida de datos nómina por bug `metodo_pago` | Alta (ya ocurre) | Medio | **Corregir en FASE 4** |
| Commit sin SAVEPOINT en `pagar_nomina` | Media | Medio | Documentado; corrección futura |
| Schema heterogéneo — `_has_column()` en prod | Media | Bajo | Migración incremental |

---

## 3. FASES DE CORRECCIÓN

| Fase | Descripción | Prioridad | Estado |
|------|-------------|-----------|--------|
| FASE 0 | Documentar plan (este archivo) | 🔴 Crítica | ✅ Completa |
| FASE 1 | Agregar tests de seguridad | 🔴 Crítica | ✅ Completa |
| FASE 2 | Sacar SQL de UI — crear `FinancialDashboardService` | 🔴 Crítica | ✅ Completa |
| FASE 3 | Mover validación de proveedor a servicio | 🟡 Alta | ✅ Completa |
| FASE 4 | Corregir bug `pagar_nomina` con `metodo_pago` | 🔴 Crítica | ✅ Completa |
| FASE 5 | Crear servicios pequeños sin romper fachada | 🟡 Alta | ✅ Completa (GL + AP + AR + 34 tests) |
| FASE 6 | Documentar tablas canónicas | 🟡 Alta | ✅ Completa |
| FASE 7 | Constantes de eventos financieros | 🟢 Media | ✅ Completa |
| FASE 8 | Evitar doble asiento / doble CxP / CxC | 🟡 Alta | ✅ Analizado + tests documentan rutas |
| FASE 9 | Transacciones atómicas | 🟢 Media | ✅ Commits internos removidos de sub-servicios |
| FASE 10 | Frontend en español | 🟢 Baja | ✅ Verificado — todo en español |

---

## 4. REGLA DE NO ROMPER COMPATIBILIDAD

- **NO** renombrar tablas físicas existentes
- **NO** eliminar métodos públicos de `FinanceService` (solo agregar delegación)
- **NO** cambiar firmas de métodos existentes (agregar `**kwargs` si se necesita)
- **NO** cambiar texto visible en UI (etiquetas, botones, columnas)
- **NO** hacer buscar/reemplazar global de idioma
- Los wrappers legacy deben seguir funcionando mientras existan importadores

---

## 5. TABLA: MÉTODO ACTUAL → DESTINO FUTURO

| Método actual (FinanceService) | Destino futuro | Estado |
|-------------------------------|----------------|--------|
| `crear_cxp()` | `AccountsPayableService.crear_cxp()` | Shim en FS |
| `abonar_cxp()` | `AccountsPayableService.abonar_cxp()` | Shim en FS |
| `cuentas_por_pagar()` | `AccountsPayableService.listar()` | Shim en FS |
| `crear_cxc()` | `AccountsReceivableService.crear_cxc()` | Shim en FS |
| `cobrar_cxc()` | `AccountsReceivableService.cobrar_cxc()` | Shim en FS |
| `cuentas_por_cobrar()` | `AccountsReceivableService.listar()` | Shim en FS |
| `registrar_asiento()` | `GeneralLedgerService.registrar()` | Permanece en FS (SSOT) |
| `dashboard_kpis()` | `FinancialDashboardService.get_kpis()` | ✅ Nuevo servicio creado |
| SQL en UI (KPI bar) | `FinancialDashboardService.get_quick_kpis()` | ✅ Migrado |
| SQL en UI (límite crédito) | `CustomerCreditService.get_credit_info()` (existente) | ✅ Migrado |
| SQL en UI (clientes lista) | `CustomerCreditService.listar_clientes()` (nuevo) | ✅ Migrado |
| SQL en UI (INSERT cliente) | Nuevo use case / servicio cliente | ✅ Migrado |
| `_verificar_duplicado` (UI) | `ThirdPartyService.check_duplicate_proveedor()` | ✅ Migrado |
| `pagar_nomina()` | Bug corregido, misma ubicación | ✅ Corregido |

---

## 6. TABLAS CANÓNICAS (FINANZAS)

Ver `docs/architecture/FINANCE_CANONICAL_TABLES.md` para detalles completos.

| Entidad | Tabla canónica temporal | Tabla legacy (mantener) |
|---------|------------------------|------------------------|
| Proveedores | `proveedores` | — |
| CxP | `accounts_payable` | `cuentas_por_pagar` (si existe) |
| CxC | `cuentas_por_cobrar` | `accounts_receivable` (si existe) |
| Pagos CxP | `ap_payments` | — |
| Pagos CxC | `ar_payments` | — |
| Ledger | `financial_event_log` | — |
| Tesorería | `treasury_ledger` | — |

---

## 7. HALLAZGOS ADICIONALES — SEGUNDA AUDITORÍA (2026-05-21)

| ID | Hallazgo | Archivo | Estado |
|----|----------|---------|--------|
| R-01 | Inyección SQL en `balance_general()` — f-string con `fecha_corte` | `treasury_service.py` | ✅ Corregido — queries parametrizadas |
| R-02 | `SaleCancelledFinanceHandler` actualizaba `credit_balance` pero no `saldo` | `finance_handler.py` | ✅ Corregido — ambas columnas sincronizadas |
| R-03 | `SaleCreatedFinanceHandler` — código muerto que causaría doble asiento | `finance_handler.py` | ✅ Eliminado |
| R-04 | `registrar_asiento_manual` usaba `cuenta_debe=`/`descripcion=` (parámetros incorrectos) | `core/use_cases/finanzas.py` | ✅ Corregido → `debe=`/`concepto=` |
| R-05 | `_ensure_tables()` creaba 6 tablas en runtime | `treasury_service.py` | ✅ Movido a migración 082 |
| R-06 | `core/events/handlers/__init__.py` exportaba handler eliminado | `__init__.py` | ✅ Corregido |

## 8. NOTAS DE ATOMICIDAD

- `pagar_nomina` hace `self.db.commit()` al final — no dentro de SAVEPOINT. Si hay transacción abierta del caller, este commit puede romper atomicidad. **Riesgo documentado; corrección futura en FASE 9.**
- `SaleCancelledFinanceHandler` (post-commit) llama `self._db.commit()` interno para el UPDATE de `cuentas_por_cobrar`. Esto es aceptable porque es post-transacción de venta.
- Métodos de bajo nivel en `FinanceService.registrar_asiento()` NO hacen commit — delegan al caller. ✅ Correcto.
