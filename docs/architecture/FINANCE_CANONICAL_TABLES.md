# FINANCE_CANONICAL_TABLES.md — SPJ ERP v13.4
**Fecha:** 2026-05-21  
**Estado:** Tabla de referencia temporal durante migración (FASE 3/4)

---

## Regla de oro

> **No renombrar tablas físicas.** Esta tabla documenta cuál es la fuente de verdad canónica  
> mientras coexisten nombres legacy y nombres nuevos de ERP.

---

## Mapa de tablas canónicas

| Entidad | Tabla canónica (SSOT actual) | Tabla legacy que puede existir | Servicio responsable | Acción futura |
|---------|------------------------------|-------------------------------|---------------------|---------------|
| **Proveedores** | `proveedores` | — | `UnifiedThirdPartyService` | Mantener |
| **Clientes** | `clientes` | — | `FinancialDashboardService.crear_cliente()` | Migrar a CustomerService |
| **CxP (Cuentas por Pagar)** | `accounts_payable` | `cuentas_por_pagar` (legacy) | `FinanceService.crear_cxp()` | Mantener `accounts_payable`; deprecar `cuentas_por_pagar` |
| **CxC (Cuentas por Cobrar)** | `cuentas_por_cobrar` | `accounts_receivable` (si existe) | `CreditSaleFinanceHandler` / `FinanceService.crear_cxc()` | Consolidar en `cuentas_por_cobrar` |
| **Pagos CxP** | `ap_payments` | — | `FinanceService.abonar_cxp()` | Mantener |
| **Pagos CxC** | `ar_payments` | — | `FinanceService.cobrar_cxc()` | Mantener |
| **Ledger / Libro contable** | `financial_event_log` | — | `FinanceService.registrar_asiento()` | Mantener (SSOT absoluto) |
| **Tesorería** | `treasury_ledger` | — | `TreasuryService` | Mantener separado |
| **Nómina** | `nomina_pagos` | — | `FinanceService.pagar_nomina()` | Mantener |
| **Gastos** | `gastos` | — | `TreasuryService.registrar_gasto_opex()` | Mantener |
| **Personal** | `personal` | — | `FinanceService.get_personal()` | Mantener |
| **Activos Fijos** | `activos_fijos` | — | `FinanceService.get_assets()` | Mantener |

---

## Notas sobre `cuentas_por_cobrar` vs `accounts_receivable`

### Situación actual
- `cuentas_por_cobrar` es la tabla canónica usada por:
  - `CreditSaleFinanceHandler` → INSERT al crear CxC en ventas crédito
  - `FinanceService.crear_cxc()` → usa `accounts_receivable` (¡diferente!)
  - `TreasuryService.get_cuentas_por_cobrar()` → lee de `cuentas_por_cobrar`

- `accounts_receivable` es usada por:
  - `FinanceService.crear_cxc()` / `cobrar_cxc()`
  - Tests en `test_finance_service_methods.py`

### Riesgo identificado
Las dos rutas de creación de CxC apuntan a tablas **distintas**:
1. Venta a crédito (automática) → `cuentas_por_cobrar`
2. CxC manual desde UI → `FinanceService.crear_cxc()` → `accounts_receivable`

**Este es un riesgo de inconsistencia real.** La UI de Tesorería (tab CxC) lee de  
`TreasuryService.get_cuentas_por_cobrar()` que usa `cuentas_por_cobrar`, pero  
las CxC manuales creadas desde el mismo módulo van a `accounts_receivable`.

### Acción recomendada (FASE 6 completa)
1. `FinanceService.crear_cxc()` debe escribir en **ambas** tablas temporalmente  
   (adapter pattern) o migrar todo a `cuentas_por_cobrar`.
2. Documentado aquí para no olvidar. **No cambiar tablas sin migración**.

---

## Notas sobre `accounts_payable` vs `cuentas_por_pagar`

### Situación actual
- `accounts_payable` es la tabla canónica para CxP (usada por FinanceService)
- `cuentas_por_pagar` puede existir en instalaciones legacy (usada por TreasuryService)
- `TreasuryService.get_cuentas_por_pagar()` lee de `cuentas_por_pagar`
- `FinanceService.crear_cxp()` / `abonar_cxp()` operan en `accounts_payable`

### Riesgo
Misma situación que CxC: dos tablas paralelas para el mismo concepto.  
`TreasuryService` puede no ver CxP creadas por `FinanceService.crear_cxp()`.

---

## Columnas de saldo en `clientes`

| Columna | Capa responsable | Descripción |
|---------|-----------------|-------------|
| `credit_balance` | Backend (canónica nueva) | Deuda acumulada; actualizada por `CreditSaleFinanceHandler` |
| `saldo` | Legacy UI | Usado por validación de crédito en UI; sincronizado manualmente |

`CreditSaleFinanceHandler` actualiza **ambas** columnas para mantener sincronía durante la transición:
```python
SET credit_balance = COALESCE(credit_balance, 0) + ?,
    saldo          = COALESCE(saldo, 0) + ?
```

---

## Eventos financieros — mapa de strings

| Constante canónica (domain_events.py) | String en bus | Usado en |
|---------------------------------------|--------------|---------|
| `ACCOUNT_PAYABLE_CREATED` | `"CXP_CREADA"` | `FinanceService.crear_cxp()` |
| `ACCOUNT_PAYABLE_PAID` | `"CXP_PAGADA"` | `FinanceService.abonar_cxp()` |
| `ACCOUNT_RECEIVABLE_CREATED` | `"CXC_CREADA"` | `FinanceService.crear_cxc()` |
| `ACCOUNT_RECEIVABLE_COLLECTED` | `"CXC_COBRADA"` | `FinanceService.cobrar_cxc()` |
| `FINANCIAL_MOVEMENT_REGISTERED` | `"MOVIMIENTO_FINANCIERO"` | `TreasuryService._publish_movimiento()` |
| `JOURNAL_ENTRY_REGISTERED` | `"ASIENTO_REGISTRADO"` | (pendiente implementar en registrar_asiento) |
| `PAYROLL_PAID` | `"NOMINA_PAGADA"` | `FinanceService.pagar_nomina()` |
