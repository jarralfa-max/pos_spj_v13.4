# FINANCIAL_TRACEABILITY_END_TO_END.md — SPJ ERP v13.4
**Fecha:** 2026-05-21  
**Estado:** Arquitectura de referencia (FASE 3/4 → en implementación)  
**Alcance:** Trazabilidad financiera completa desde evento de origen hasta conciliación

---

## 1. Introducción — Por qué importa la trazabilidad end-to-end

El sistema SPJ ERP procesa múltiples flujos financieros simultáneos: ventas de mostrador, ventas a crédito, pagos vía MercadoPago, compras de inventario, nómina, activos fijos, gastos operativos, mermas y comisiones de delivery. Sin trazabilidad completa, surgen riesgos críticos:

**Riesgos identificados en auditoría (FASE 1):**
- Doble posteo contable: un mismo evento dispara dos handlers que escriben en `financial_event_log` (detectado y corregido en `_wire_flujos_criticos`).
- Inconsistencia entre tablas paralelas: `cuentas_por_cobrar` vs `accounts_receivable`; `cuentas_por_pagar` vs `accounts_payable`.
- Ausencia de `operation_id` único: imposible detectar reintentos o reingresos duplicados.
- Falta de enlace entre el evento de origen (`source_module`, `source_id`) y el asiento contable resultante.
- Sin bitácora técnica de qué operaciones se intentaron y cuáles fallaron.

**Objetivo de la arquitectura de trazabilidad:**
1. Cada operación financiera tiene un `operation_id` único derivado del evento de origen.
2. Cada `operation_id` aparece exactamente una vez en cada tabla canónica (UNIQUE constraint).
3. Existe una cadena completa auditable: `source_event → financial_document → treasury_movement → journal_entry → financial_trace_log → reconciliation_records`.
4. La capa nueva convive con las tablas legacy sin reemplazarlas, protegiendo la estabilidad operativa durante la migración.

---

## 2. Tablas canónicas de referencia

### 2.1 Tablas legacy (conservadas — NO se renombran)

| Tabla | Descripción | Servicio responsable (legacy) | Estado en migración |
|-------|-------------|-------------------------------|---------------------|
| `financial_event_log` | Libro mayor contable legacy (doble entrada) | `FinanceService.registrar_asiento()` / `GeneralLedgerService` | SSOT para contabilidad actual; `journal_entries` la complementa |
| `treasury_ledger` | Movimientos de caja registrados | `TreasuryService` | SSOT para tesorería actual; `treasury_movements` la complementa |
| `accounts_payable` | Cuentas por pagar (canónico CxP nuevo) | `FinanceService.crear_cxp()` | CxP canónica desde v13.5 |
| `accounts_receivable` | CxC creadas manualmente por `FinanceService` | `FinanceService.crear_cxc()` | ⚠️ Conflicto con `cuentas_por_cobrar` — ver Sección 7 |
| `cuentas_por_cobrar` | CxC creadas automáticamente por ventas a crédito | `CreditSaleFinanceHandler` | ⚠️ Conflicto con `accounts_receivable` — ver Sección 7 |
| `cuentas_por_pagar` | CxP legacy en instalaciones antiguas | `TreasuryService.get_cuentas_por_pagar()` | Deprecar; migrar a `accounts_payable` |
| `ap_payments` | Pagos de CxP | `FinanceService.abonar_cxp()` | Mantener |
| `ar_payments` | Cobros de CxC | `FinanceService.cobrar_cxc()` | Mantener |
| `activos` | Registro de activos fijos (UI legacy) | `FinanceService.registrar_asset()` | Conceptualmente reemplazado por `fixed_assets`; tabla física conservada |
| `gastos` | Registro de gastos operativos | `TreasuryService.registrar_gasto_opex()` | Mantener |
| `nomina_pagos` | Historial de nómina | `FinanceService.pagar_nomina()` | Mantener |
| `movimientos_caja` | Entradas de caja por turno | `FinanceService.register_income()` | Mantener |
| `treasury_capital` | Inyecciones y retiros de capital | `TreasuryService.inyectar_capital()` | Mantener |
| `depreciacion_acumulada` | Depreciación acumulada mensual por activo | Motor de depreciación FASE 3 | Mantener; enlazada a `asset_depreciation_entries` |
| `plan_cuentas` | Catálogo contable NIF/SAT (41 cuentas 1xx–6xx) | — | Referencia estática |

### 2.2 Tablas canónicas nuevas (migration 083_financial_traceability_tables.py)

Estas tablas **no reemplazan** a las legacy. Son una **capa superior** que agrega idempotencia, trazabilidad y enlace entre capas. Todas usan `operation_id TEXT UNIQUE NOT NULL`.

| Tabla | Propósito | Relación con legacy |
|-------|-----------|---------------------|
| `financial_documents` | Documentos financieros unificados (CxC, CxP, nómina, activo) | Encima de `accounts_payable` / `cuentas_por_cobrar` |
| `treasury_movements` | Movimientos de dinero real confirmados | Encima de `treasury_ledger` |
| `journal_entries` | Asientos contables idempotentes (doble entrada) | Encima de `financial_event_log` |
| `fixed_assets` | Activos fijos con trazabilidad completa | Paralelo a `activos`; `activos` NO se renombra |
| `asset_depreciation_entries` | Depreciaciones por período (idempotente por `asset_id-YYYY-MM`) | Paralelo a `depreciacion_acumulada` |
| `maintenance_records` | Mantenimientos con enlace a documentos y asientos | Nuevo (sin equivalente legacy) |
| `operating_supplies` | Insumos operativos (rollos térmicos, etiquetas, limpieza) | Nuevo — registrados como gasto OPEX |
| `financial_trace_log` | Bitácora técnica de cada operación de trazabilidad | Nuevo — auditoría de trazabilidad |
| `reconciliation_records` | Detección de discrepancias entre capas | Nuevo |

---

## 3. Flujo de trazabilidad end-to-end

El siguiente diagrama muestra la cadena completa que debe existir para TODA operación financiera.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE TRAZABILIDAD SPJ ERP                        │
└─────────────────────────────────────────────────────────────────────────────┘

  [1] SOURCE EVENT
       │
       │  Evento de dominio publicado al EventBus
       │  Ejemplos: SALE_ITEMS_PROCESS, PURCHASE_CREATED, MERMA_REGISTRADA
       │  Contiene: source_module, source_id, source_folio, operation_id
       │
       ▼
  [2] FINANCIAL DOCUMENT (tabla: financial_documents)
       │
       │  Tipo: receivable | payable | payroll | maintenance | asset
       │  Representa el DERECHO o OBLIGACIÓN financiera
       │  Ejemplos: CxC de venta crédito, CxP de compra inventario
       │  operation_id = "{source_module}-{source_id}-{event_type}"
       │  UNIQUE constraint → garantiza idempotencia
       │
       ▼
  [3] TREASURY MOVEMENT (tabla: treasury_movements)
       │
       │  Representa el DINERO REAL que se mueve
       │  direction: in (ingreso) | out (egreso)
       │  Solo se crea cuando hay movimiento de caja confirmado
       │  Apunta a financial_document_id (FK lógico)
       │  operation_id = "{source_module}-{source_id}-{movement_type}"
       │  UNIQUE constraint → imposible duplicar movimiento de dinero
       │
       ▼
  [4] JOURNAL ENTRY (tabla: journal_entries)
       │
       │  Asiento contable de doble entrada (debe = haber)
       │  debit_account  → código en plan_cuentas
       │  credit_account → código en plan_cuentas
       │  Escrito también en financial_event_log (legacy, simultáneamente)
       │  operation_id = "{source_module}-{source_id}-{je_suffix}"
       │  UNIQUE constraint → imposible duplicar asiento contable
       │
       ▼
  [5] FINANCIAL TRACE LOG (tabla: financial_trace_log)
       │
       │  Bitácora técnica de CADA escritura financiera
       │  trace_status: started | completed | failed | skipped
       │  Permite detectar operaciones incompletas o fallidas
       │  Referencia al mismo operation_id en múltiples pasos
       │
       ▼
  [6] RECONCILIATION RECORD (tabla: reconciliation_records)
       │
       │  check_type: sale_vs_treasury | cxc_journal | cxp_journal | etc.
       │  Compara expected_amount vs actual_amount
       │  status: ok | discrepancy | resolved | ignored
       │  Se ejecuta en proceso batch (pendiente implementar)
       │
       ▼
  [7] AUDIT / REPORTING
       │
       │  financial_event_log  — libro mayor contable
       │  treasury_ledger      — posición de caja
       │  reconciliation_records — discrepancias detectadas
       │  financial_trace_log  — errores de integración
       └─ plan_cuentas         — estructura de cuentas NIF/SAT
```

### 3.1 Formato canónico de operation_id

```
{source_module}-{source_id}-{event_type}
```

Ejemplos concretos:

| Operación | operation_id |
|-----------|-------------|
| Venta contado #1042 | `ventas-1042-cash_income` |
| CxC de venta crédito #1043 | `ventas-1043-receivable` |
| Asiento GL venta crédito #1043 | `ventas-1043-je_cxc` |
| Compra inventario #88 al contado | `compras-88-cash_outflow` |
| CxP compra crédito #89 | `compras-89-payable` |
| Pago CxP de compra #89 | `compras-89-payable_payment` |
| Nómina periodo 2026-05 empleado #3 | `nomina-3-2026-05-payroll` |
| Depreciación activo #5 período 2026-05 | `5-2026-05` (en `asset_depreciation_entries`) |
| Merma producto #12 | `merma-{merma_id}-loss_entry` |
| Delivery orden #77 comisión | `delivery-77-commission` |
| Insumo rollo térmico compra #91 | `compras-91-opex_thermal_rolls` |
| Activo fijo equipo compra #95 | `compras-95-asset_capitalized` |

---

## 4. Reglas por módulo

La tabla siguiente especifica el flujo exacto para cada módulo operativo. Columnas:

- **Módulo** — área de negocio
- **Trigger event** — evento de dominio que inicia el flujo (string en EventBus)
- **financial_document** — tipo de documento que se crea (o "N/A")
- **treasury_movement** — tipo de movimiento de dinero
- **journal_entry: debe → haber** — cuentas del asiento contable
- **Servicio responsable** — clase Python que ejecuta la operación
- **Estado** — implementado / parcial / pendiente

### 4.1 Ventas Contado

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `SALE_ITEMS_PROCESS` |
| **Condición** | `payment_method NOT IN {"Credito", "Mercado Pago"}` |
| **financial_document** | No aplica (ingreso inmediato, sin documento de cobro pendiente) |
| **treasury_movement** | `inflow`, direction=`in`, `payment_method=Efectivo/Tarjeta` |
| **journal_entry** | Debe: `1101 Caja` (o `1102 Bancos`) → Haber: `4101 Ventas al Contado` |
| **Handler** | `SaleFinanceHandler` (priority=90 en `SALE_ITEMS_PROCESS`) |
| **Servicio** | `FinanceService.register_income()` → `movimientos_caja` (legacy) |
| **Inventory** | `SaleInventoryHandler` (priority=100, antes del asiento) |
| **Estado** | Implementado (Phase 1). `journal_entries` nueva: pendiente |

**Regla de negocio:** El ingreso se registra dentro del SAVEPOINT de la venta. Si falla, toda la venta hace rollback. No commit independiente.

### 4.2 Ventas Crédito

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `SALE_ITEMS_PROCESS` |
| **Condición** | `payment_method == "Credito"` |
| **financial_document** | `receivable` — INSERT en `financial_documents` + INSERT en `cuentas_por_cobrar` |
| **treasury_movement** | No aplica (dinero no se recibe todavía) |
| **journal_entry** | Debe: `1103 Cuentas por Cobrar Clientes` → Haber: `4102 Ventas a Crédito` |
| **Handler** | `CreditSaleFinanceHandler` (priority=85 en `SALE_ITEMS_PROCESS`) |
| **balance cliente** | `clientes.credit_balance` y `clientes.saldo` se incrementan |
| **Estado** | Implementado (Phase 6). `financial_documents` nueva: pendiente |

**Regla de negocio:** La CxC se crea atómica con la venta dentro del mismo SAVEPOINT (priority=85). Si falla, toda la venta hace rollback. El cobro posterior usa `FinanceService.cobrar_cxc()` → `ar_payments`.

**Riesgo activo (ver Sección 7):** CxC automática va a `cuentas_por_cobrar`; CxC manual desde UI va a `accounts_receivable`. Son tablas distintas.

### 4.3 MercadoPago

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `SALE_ITEMS_PROCESS` (creación del link de pago) |
| **Condición** | `payment_method == "Mercado Pago"` |
| **financial_document** | `receivable` con `status=pending_payment` |
| **treasury_movement** | No aplica en la creación del link |
| **treasury_movement (confirmación)** | `inflow` direction=`in` — solo cuando llega webhook de confirmación |
| **journal_entry (confirmación)** | Debe: `1102 Bancos` → Haber: `4101 Ventas al Contado` menos `6108 Comisiones` |
| **Comisión MercadoPago** | 3.6% del monto confirmado → gasto `6108 Comisiones` |
| **Handler creación** | `SaleFinanceHandler` — excluye MP explícitamente (no registra ingreso hasta webhook) |
| **Handler webhook** | Pendiente implementar en FASE 6 (`MercadoPagoWebhookHandler`) |
| **Servicio** | `MercadoPagoService` (en `services/mercado_pago_service.py`) |
| **Estado** | Parcial — creación OK, webhook de confirmación pendiente |

**Regla de negocio:** El ingreso de MercadoPago NO se contabiliza al crear el link de pago. Solo se registra como ingreso real cuando llega la confirmación por webhook. Hasta entonces el documento queda en `status=pending_payment`.

### 4.4 Compras Contado

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `PURCHASE_ITEMS_PROCESS` (inventario) + `PURCHASE_CREATED` (finanzas) |
| **financial_document** | No aplica (pago inmediato, sin obligación pendiente) |
| **treasury_movement** | `outflow`, direction=`out`, `payment_method=Efectivo/Transferencia` |
| **journal_entry** | Debe: `5101 Costo de Mercancías` → Haber: `1101 Caja` |
| **Inventory handler** | `PurchaseInventoryHandler` (priority=100 en `PURCHASE_ITEMS_PROCESS`) |
| **Finance handler** | `PurchaseFinanceHandler` (priority=80 en `PURCHASE_CREATED`) |
| **Estado** | Implementado (Phase 4). `treasury_movements` nueva: pendiente |

### 4.5 Compras Crédito

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `PURCHASE_ITEMS_PROCESS` + `PURCHASE_CREATED` |
| **Condición** | `condicion_pago == "credito"` o `tipo_pago == "credito"` |
| **financial_document** | `payable` — INSERT en `financial_documents` + INSERT en `accounts_payable` |
| **treasury_movement** | No aplica (pago diferido) |
| **journal_entry** | Debe: `5101 Costo de Mercancías` → Haber: `2101 Cuentas por Pagar Proveedores` |
| **Pago posterior** | `FinanceService.abonar_cxp()` → `ap_payments` → asiento: Debe `2101` → Haber `1101 Caja` |
| **Estado** | Implementado. `financial_documents` nueva: pendiente |

### 4.6 Gastos Operativos (Renta, Luz, Agua, Gas, Seguros)

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Manual (registro en UI módulo Tesorería) |
| **financial_document** | `payable` si es gasto diferido; N/A si pago inmediato |
| **treasury_movement** | `outflow`, direction=`out` |
| **journal_entry** | Debe: `6101/6102 Gastos Operativos` → Haber: `1101 Caja` o `2101 CxP` |
| **Servicio** | `TreasuryService.registrar_gasto_opex()` → `gastos` (legacy) |
| **Estado** | Implementado en legacy. Nuevas tablas: pendiente |

### 4.7 Insumos Operativos (incluye Rollos Térmicos)

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Manual (registro en UI) o via compra no inventariable |
| **Tabla destino** | `operating_supplies` (nueva) con `supply_type=thermal_rolls|labels|cleaning|stationery|bags|packaging|other` |
| **financial_document** | `payable` si a crédito; N/A si pago inmediato |
| **treasury_movement** | `outflow` direction=`out` |
| **journal_entry** | Debe: `6109 Gastos de Papelería y Empaque` → Haber: `1101 Caja` o `2101 CxP` |
| **Estado** | Tabla creada en m083. Servicio: pendiente (FASE 4) |

**Política de Rollos Térmicos (decisión de diseño):**  
Los rollos térmicos se registran como **gasto operativo en el momento de la compra** (cuenta 6109). No existe costo por ticket impreso en esta fase. El inventario de rollos NO se gestiona en el módulo de inventariables. Esta política aplica a todos los insumos operativos de consumo rápido (etiquetas, bolsas, productos de limpieza, papelería). Revisar en FASE 6 si se requiere control de consumo por ticket para sucursales con alto volumen de impresión.

### 4.8 Activos Fijos

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Manual (módulo Activos) o via compra capitalizable |
| **Condición de capitalización** | Monto > $5,000 MXN AND vida útil esperada > 12 meses |
| **Por debajo del umbral** | Se expensa como `6109 Gastos de Papelería y Empaque` o `6106 Mantenimiento` |
| **Tabla destino** | `fixed_assets` (nueva) y `activos` (legacy; NO se renombra) |
| **financial_document** | `asset` — INSERT en `financial_documents` con `document_type=asset` |
| **treasury_movement** | `outflow` direction=`out` (o `payable` si a crédito) |
| **journal_entry** | Debe: `1301 Equipo y Maquinaria` → Haber: `1101 Caja` o `2101 CxP` |
| **Servicio** | `FinanceService.registrar_asset()` → `activos` (legacy). `fixed_assets` nuevo: pendiente |
| **Estado** | Legacy implementado. `fixed_assets` + `financial_documents`: pendiente |

**Política de capitalización:**
```
if monto > 5_000 MXN and vida_util_meses > 12:
    → capitalizar en fixed_assets + asiento Debe 1301 Haber 1101/2101
else:
    → expensear como gasto operativo (6106 o 6109)
```

Nota: El umbral de $5,000 MXN es configurable. En instalaciones futuras puede almacenarse en `config` o `module_config`.

### 4.9 Depreciación

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Proceso batch mensual (automático o manual) |
| **Método** | Línea recta: `depreciacion_mensual = acquisition_cost / useful_life_months` |
| **Tabla destino** | `asset_depreciation_entries` con `operation_id = "{asset_id}-{YYYY-MM}"` |
| **journal_entry** | Debe: `6105 Depreciación de Activos` → Haber: `1302 Depreciación Acumulada Equipo` |
| **Idempotencia** | `operation_id UNIQUE` garantiza que cada activo-período solo tiene un asiento |
| **Estado** | `depreciacion_acumulada` legacy implementada. `asset_depreciation_entries`: pendiente |

### 4.10 Mantenimiento

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Manual (registro en UI) |
| **Tabla destino** | `maintenance_records` (nueva). Coexiste con `activos` legacy |
| **Capitalizable** | `maintenance_records.capitalizable = 1` si mejora la vida útil del activo |
| **Gasto normal** | Debe: `6106 Mantenimiento y Reparación` → Haber: `1101 Caja` o `2101 CxP` |
| **Capitalizable** | Debe: `1301 Equipo y Maquinaria` → Haber: `1101 Caja` o `2101 CxP` |
| **Servicio** | `FinanceService.registrar_mantenimiento()`. `maintenance_records`: pendiente |
| **Estado** | Legacy implementado. Nuevas tablas: pendiente |

**Regla de negocio:** Un mantenimiento es capitalizable si el desembolso prolonga la vida útil del activo más allá de su vida útil original, o si el monto supera el umbral de capitalización ($5,000 MXN). En ese caso, se ajusta `fixed_assets.useful_life_months` y se crea un nuevo asiento de activo fijo.

### 4.11 Nómina

| Atributo | Valor |
|----------|-------|
| **Trigger event** | Manual (UI Nómina) → publica `PAYROLL_PAID` |
| **financial_document** | `payroll` — document representando la nómina del período |
| **treasury_movement** | `outflow` direction=`out` (pago de salarios) |
| **journal_entry** | Debe: `6103 Nómina y Salarios` + `6104 Cuotas IMSS Patronales` → Haber: `1101 Caja` o `2102 IMSS por Pagar` + `2103 ISR por Pagar` |
| **Servicio** | `FinanceService.pagar_nomina()` → `nomina_pagos` (legacy) |
| **Notificación** | `PAYROLL_DUE` → WhatsApp (priority=10, soft-fail) |
| **Estado** | Legacy implementado. `financial_documents` nueva: pendiente |

**Regla de negocio:** El asiento de nómina debe balancear: salario bruto en debe = neto pagado + retenciones (IMSS, ISR) en haber. `FinanceService.pagar_nomina()` llama a `registrar_asiento()` internamente.

### 4.12 Delivery

| Atributo | Valor |
|----------|-------|
| **Trigger events** | `DELIVERY_ORDER_RESERVED`, `DELIVERY_ITEM_WEIGHT_ADJUSTED`, `DELIVERY_TOTAL_UPDATED`, `DELIVERY_COMPLETED` |
| **Comisión** | Porcentaje configurado por módulo (ej. 8-15%). Registro como `6108 Comisiones` |
| **Liquidación conductor** | `DriverSettlementHandler` → `delivery_driver_settlements` |
| **journal_entry comisión** | Debe: `6108 Comisiones` → Haber: `2101 CxP` (o `1101 Caja` si pago inmediato) |
| **treasury_movement** | `outflow` cuando se liquida el conductor |
| **Estado** | Handlers de lifecycle implementados (Phase v13.30). Comisión `journal_entries` nueva: pendiente |

### 4.13 Mermas

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `MERMA_REGISTRADA` (publicado por módulo `merma.py`) |
| **financial_document** | No aplica (pérdida interna, sin movimiento de dinero) |
| **treasury_movement** | No aplica |
| **journal_entry** | Debe: `5102 Merma de Inventario` → Haber: `1201 Inventario de Mercancías` |
| **Inventory handler** | `_wire_merma_inventario` (priority=80) — ajuste de stock |
| **Finance handler** | `_wire_merma_financiero` (priority=50) — asiento contable |
| **Estado** | Implementado. Migración a `journal_entries` nueva: pendiente |

**Regla de negocio:** La merma reduce el valor del inventario. El asiento mueve el costo desde el activo inventario hacia una cuenta de pérdida. No hay movimiento de dinero real.

### 4.14 Fidelidad (Puntos / Estrellas)

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `VENTA_COMPLETADA` → `_loyalty_venta` handler (priority=50) |
| **financial_document** | Pasivo — `2104 Pasivo Fidelización` se incrementa al emitir estrellas |
| **treasury_movement** | No aplica (no hay movimiento de caja por emisión) |
| **journal_entry emisión** | Debe: `4101 Ventas al Contado` (descuento) → Haber: `2104 Pasivo Fidelización` |
| **journal_entry canje** | Debe: `2104 Pasivo Fidelización` → Haber: `4101 Ventas al Contado` (reducción ingreso) |
| **Tablas** | `loyalty_ledger` (SSOT), `growth_ledger`, `loyalty_pasivo_log` (legacy) |
| **Servicio** | `LoyaltyService.process_loyalty_for_sale()` |
| **Estado** | Emisión implementada. `journal_entries` nueva para pasivo fidelización: pendiente |

### 4.15 Cancelaciones

| Atributo | Valor |
|----------|-------|
| **Trigger event** | `VENTA_CANCELADA` |
| **Handler** | `SaleCancelledFinanceHandler` (priority=50, post-commit) |
| **financial_document** | Reversa del documento original (status → `cancelled`) |
| **treasury_movement** | `outflow` si ya se había cobrado (devolución al cliente) |
| **journal_entry reversión** | Debe: `4101 Ventas al Contado` → Haber: `1101 Caja` (reversa del ingreso) |
| **CxC reversión** | Si era crédito: reversa en `cuentas_por_cobrar` + decremento `clientes.credit_balance` |
| **Estado** | Implementado (`SaleCancelledFinanceHandler`). Reversa en `financial_documents`: pendiente |

---

## 5. Reglas de idempotencia

### 5.1 Principio

Toda operación financiera en el sistema nuevo es **idempotente**: si el mismo evento se procesa dos veces (reintento, fallo de red, reinicio), el resultado final es el mismo que si se procesara una sola vez.

### 5.2 Mecanismo técnico

**UNIQUE constraint en `operation_id`:**
```sql
-- financial_documents
operation_id TEXT UNIQUE NOT NULL

-- treasury_movements  
operation_id TEXT UNIQUE NOT NULL

-- journal_entries
operation_id TEXT UNIQUE NOT NULL

-- fixed_assets
operation_id TEXT UNIQUE NOT NULL

-- asset_depreciation_entries
operation_id TEXT UNIQUE NOT NULL  -- formato: "{asset_id}-{YYYY-MM}"

-- maintenance_records
operation_id TEXT UNIQUE NOT NULL

-- operating_supplies
operation_id TEXT UNIQUE NOT NULL
```

### 5.3 Patrón de escritura idempotente

```python
# Patrón estándar para servicios nuevos:
try:
    conn.execute(
        "INSERT INTO financial_documents (operation_id, ...) VALUES (?, ...)",
        (operation_id, ...)
    )
except sqlite3.IntegrityError:
    # operation_id ya existe → operación ya fue procesada → no hacer nada
    logger.info("Operación ya procesada: %s", operation_id)
    return existing_row_id
```

### 5.4 Construcción del operation_id

**Formato canónico:**
```
{source_module}-{source_id}-{event_type_suffix}
```

**Reglas:**
1. `source_module`: string corto del módulo (`ventas`, `compras`, `nomina`, `merma`, `activos`, `delivery`).
2. `source_id`: PK del registro origen en la tabla del módulo.
3. `event_type_suffix`: identifica el tipo de documento/movimiento/asiento para ese evento.

**Ejemplo de construcción en Python:**
```python
operation_id = f"ventas-{sale_id}-receivable"
operation_id = f"compras-{purchase_id}-cash_outflow"
operation_id = f"nomina-{employee_id}-{period}-payroll"
operation_id = f"{asset_id}-{period}"  # para depreciaciones
```

### 5.5 Tablas legacy — sin idempotencia garantizada

Las tablas legacy (`financial_event_log`, `treasury_ledger`, `movimientos_caja`) NO tienen `operation_id` UNIQUE. Pueden recibir entradas duplicadas si un handler se dispara más de una vez. Este es el riesgo principal documentado en la auditoría y el motivo para la capa nueva.

**Mitigación temporal:** Los handlers actuales están en SAVEPOINT atómico. Si el handler lanza excepción, el SAVEPOINT hace rollback de toda la transacción (incluyendo la operación que originó el evento). Esto reduce (no elimina) el riesgo de duplicados.

---

## 6. Mapa evento → servicio

| Evento (EventBus string) | Prioridad | Handler / Servicio | Operación financiera | Estado |
|--------------------------|-----------|---------------------|----------------------|--------|
| `SALE_ITEMS_PROCESS` | 100 | `SaleInventoryHandler` | Descuento de stock | OK |
| `SALE_ITEMS_PROCESS` | 90 | `SaleFinanceHandler` | `register_income()` → `movimientos_caja` | OK |
| `SALE_ITEMS_PROCESS` | 85 | `CreditSaleFinanceHandler` | CxC + asiento GL | OK |
| `VENTA_COMPLETADA` | 100 | `_sync_venta` (sync handler) | Sync a otros módulos | OK |
| `VENTA_COMPLETADA` | 50 | `LoyaltyService.process_loyalty_for_sale()` | Emisión de estrellas | OK |
| `VENTA_COMPLETADA` | 30 | Audit handler | Log de auditoría | OK |
| `VENTA_COMPLETADA` | 20 | Treasury venta handler | `treasury_ledger` | OK |
| `VENTA_CANCELADA` | 50 | `SaleCancelledFinanceHandler` | Reversa GL y CxC | OK |
| `PURCHASE_ITEMS_PROCESS` | 100 | `PurchaseInventoryHandler` | Incremento de stock | OK |
| `PURCHASE_CREATED` | 80 | `PurchaseFinanceHandler` | Asiento costo inventario | OK |
| `MERMA_REGISTRADA` | 80 | `_wire_merma_inventario` | Ajuste de stock | OK |
| `MERMA_REGISTRADA` | 50 | `_wire_merma_financiero` | Asiento merma GL | OK |
| `DELIVERY_ORDER_RESERVED` | 100 | `DeliveryReserveStockHandler` | Reserva de inventario | OK |
| `DELIVERY_RESERVATION_RELEASED` | 100 | `DeliveryReservationReleaseHandler` | Libera reserva | OK |
| `DELIVERY_ITEM_WEIGHT_ADJUSTED` | 100 | `DeliveryWeightAdjustmentHandler` | Ajuste peso | OK |
| `DELIVERY_ITEM_WEIGHT_ADJUSTED` | 10 | `DeliveryWhatsAppNotificationHandler` | Notificación WA | OK |
| `DELIVERY_TOTAL_UPDATED` | 50 | `DeliveryPaymentUpdateHandler` | Actualiza monto pago | OK |
| `DELIVERY_COMPLETED` | — | `DriverSettlementHandler` | Liquidación conductor | OK |
| `PAYROLL_DUE` | 10 | `_notify_payroll_due` | Notificación WA (soft-fail) | OK |
| `MOVIMIENTO_FINANCIERO` | 30 | Audit handler | Log auditoria mov. financiero | OK |
| `MP_PAYMENT_CONFIRMED` | — | `MercadoPagoWebhookHandler` (pendiente) | Ingreso confirmado MP | Pendiente |
| `ASSET_REGISTERED` | — | `AssetFinanceHandler` (pendiente) | Capitalización + GL | Pendiente |
| `DEPRECIATION_RUN` | — | `DepreciationHandler` (pendiente) | Asiento depreciación mensual | Pendiente |

---

## 7. Registro de riesgos legacy

### 7.1 Riesgos activos (no resueltos)

| ID | Descripción | Módulo afectado | Severidad | Acción requerida |
|----|-------------|-----------------|-----------|-----------------|
| **R-01** | Dos tablas para CxC: `cuentas_por_cobrar` (automática, venta crédito) vs `accounts_receivable` (manual, FinanceService) | Cuentas por Cobrar | Alta | `FinanceService.crear_cxc()` debe escribir en ambas tablas (adapter pattern) o migrar todo a `cuentas_por_cobrar`. Documentado en `FINANCE_CANONICAL_TABLES.md`. |
| **R-02** | Dos tablas para CxP: `accounts_payable` (canónica) vs `cuentas_por_pagar` (legacy instalaciones antiguas) | Cuentas por Pagar | Alta | `TreasuryService.get_cuentas_por_pagar()` lee de `cuentas_por_pagar`, pero `FinanceService.crear_cxp()` escribe en `accounts_payable`. Pueden divergir. |
| **R-03** | `clientes.credit_balance` y `clientes.saldo` se actualizan por separado | Clientes / Crédito | Media | `CreditSaleFinanceHandler` actualiza ambas. Verificar que no haya rutas que actualicen solo una. |
| **R-04** | `financial_event_log` sin `operation_id` UNIQUE | Libro Mayor | Alta | Riesgo de doble posteo en reintentos. Mitigado por SAVEPOINT pero no eliminado. `journal_entries` nueva resuelve esto. |
| **R-05** | `treasury_ledger` sin `operation_id` UNIQUE | Tesorería | Alta | Idem R-04. `treasury_movements` nueva resuelve esto. |
| **R-06** | Activos físicos en `activos` (legacy) sin enlace a `fixed_assets` ni a `journal_entries` | Activos Fijos | Media | Durante la migración coexisten dos registros para el mismo activo. Requiere proceso de reconciliación al activar `fixed_assets`. |
| **R-07** | MercadoPago: confirmación de pago no implementada | Ventas MP | Alta | Si el webhook no llega, el ingreso nunca se contabiliza aunque el cliente haya pagado. Riesgo financiero real. |
| **R-08** | Nómina: `pagar_nomina()` no verifica que el período ya fue pagado | Nómina | Media | Sin `operation_id` único, pagar nómina dos veces crea dos registros en `nomina_pagos` y dos asientos en `financial_event_log`. |

### 7.2 Riesgos resueltos (auditados y corregidos)

| ID | Descripción | Resolución | Referencia |
|----|-------------|------------|------------|
| **R-F01** | `_compra_stock` en `_wire_flujos_criticos` causaba doble incremento de inventario al combinarse con `PurchaseInventoryHandler` | Handler removido. Solo `PurchaseInventoryHandler` maneja stock de compras | `core/events/wiring.py:81-99` |
| **R-F02** | `_compra_egreso` causaba doble asiento GL al combinarse con `PurchaseFinanceHandler` | Handler removido. Solo `PurchaseFinanceHandler` maneja GL de compras | Ídem |
| **R-F03** | `_merma_perdida` causaba doble asiento GL al combinarse con `_wire_merma_financiero` | Handler removido. Solo `_wire_merma_financiero` maneja GL de mermas | Ídem |
| **R-F04** | `SaleCreatedFinanceHandler` registrado pero nunca suscrito → dead code con riesgo de doble asiento si se activaba | Eliminado en auditoría 2026-05-21 | `core/events/handlers/finance_handler.py:9` |

---

## 8. Fases de migración

### 8.1 Estado actual por capa

| Capa | Tabla(s) activas | Idempotencia | Trazabilidad source→GL | Estado |
|------|-----------------|--------------|------------------------|--------|
| Libro mayor | `financial_event_log` | No | Parcial (referencia_id) | Operacional |
| Tesorería | `treasury_ledger` | No | Parcial (referencia) | Operacional |
| CxP | `accounts_payable` | No | Parcial | Operacional |
| CxC | `cuentas_por_cobrar` + `accounts_receivable` | No | Parcial | Operacional (riesgo R-01) |
| Activos | `activos` | No | No | Operacional |
| Depreciación | `depreciacion_acumulada` | Sí (UNIQUE activo+período) | Parcial | Operacional |
| Merma GL | `financial_event_log` vía handler | No | Parcial | Operacional |
| Fidelidad | `loyalty_ledger` | No | No | Operacional |

### 8.2 Plan de migración por fases

#### FASE 3 — Rearquitectura (en curso)
**Objetivo:** Activar `journal_entries` como capa nueva en paralelo con `financial_event_log`.

- [ ] Crear `FinancialTraceService` que envuelva `GeneralLedgerService` y escriba en ambas tablas simultáneamente.
- [ ] Agregar `operation_id` a todas las llamadas a `registrar_asiento()`.
- [ ] Activar escritura dual en `journal_entries` + `financial_event_log`.
- [ ] Añadir test de idempotencia: llamar dos veces con el mismo `operation_id` → sin duplicados.

#### FASE 4 — Refactor módulos UI
**Objetivo:** Activar `treasury_movements` como capa nueva en paralelo con `treasury_ledger`.

- [ ] Crear `TreasuryMovementService` con `operation_id` UNIQUE.
- [ ] `TreasuryService` escribe en `treasury_movements` + `treasury_ledger` simultáneamente.
- [ ] Módulos UI no llaman a `treasury_ledger` directamente.
- [ ] Resolver R-01: unificar `cuentas_por_cobrar` y `accounts_receivable` mediante adapter en `FinanceService.crear_cxc()`.
- [ ] Resolver R-02: unificar `accounts_payable` y `cuentas_por_pagar`.

#### FASE 5 — Microservicios (en curso — WhatsApp 80% completo)
**Objetivo:** `financial_documents` como capa nueva para todos los documentos.

- [ ] Activar `financial_documents` para ventas crédito (CxC).
- [ ] Activar `financial_documents` para compras crédito (CxP).
- [ ] Activar `financial_documents` para nómina.
- [ ] Activar `fixed_assets` para activos nuevos.
- [ ] Proceso batch de reconciliación inicial: `activos` → `fixed_assets`.

#### FASE 6 — Integración
**Objetivo:** Completar la cadena y agregar conciliación automática.

- [ ] Implementar `MercadoPagoWebhookHandler` con `operation_id` idempotente.
- [ ] Implementar proceso batch de depreciación mensual en `asset_depreciation_entries`.
- [ ] Activar `reconciliation_records` con proceso batch nocturno.
- [ ] Resolver R-08: verificar períodos de nómina ya pagados.
- [ ] Resolver R-06: enlazar activos `activos` ↔ `fixed_assets`.

#### FASE 7 — Validación
**Objetivo:** 100% de operaciones con trazabilidad completa.

- [ ] Todos los `operation_id` en `financial_trace_log`.
- [ ] Proceso de conciliación ejecutándose diariamente.
- [ ] `financial_event_log` y `journal_entries` en perfecta sincronía (0 discrepancias).
- [ ] `treasury_ledger` y `treasury_movements` en perfecta sincronía.
- [ ] Eliminar rutas que escriben directo en tablas legacy sin pasar por servicios nuevos.

---

## 9. Política de Insumos Operativos (Rollos Térmicos y similares)

### 9.1 Decisión de diseño

**Resolución:** Los rollos térmicos y todos los insumos operativos de consumo rápido se registran como **gasto operativo en el momento de la compra**. No existe costo por ticket impreso en esta fase.

**Fundamento:**
- Volumen de impresión en un turno típico: 20-100 tickets.
- Costo de un rollo de 80mm × 80m: ~$12-18 MXN.
- Complejidad de asignar costo por ticket: alta (requiere contador de impresión por rollo + sensor de fin de rollo).
- Beneficio contable de esa granularidad: bajo para el tamaño de la empresa.
- Costo de implementar el control por ticket: no justificado en FASE 3/4.

**Implementación:**
```
Compra de 10 rollos térmicos ($180 MXN) →
  operating_supplies: supply_type=thermal_rolls, total_amount=180, status=paid
  journal_entry: Debe 6109 → Haber 1101 Caja
```

**Cuándo revisar esta política:**
- Si una sucursal supera 500 tickets/día y el gasto de rollos supera el 1% de las ventas.
- Si se necesita auditoría por turno del consumo de rollos.
- Si se implementa un sistema de impresión central (servidor de impresión) que pueda contar jobs.

### 9.2 Tipos de insumos operativos

| `supply_type` | Ejemplo | Cuenta contable |
|---------------|---------|-----------------|
| `thermal_rolls` | Rollos de papel térmico 80mm | 6109 Gastos de Papelería y Empaque |
| `labels` | Etiquetas de precio, código de barras | 6109 |
| `cleaning` | Jabón, desengrasante, cloro, jergas | 6100 Gastos de Operación |
| `stationery` | Bolígrafos, folders, sellos | 6109 |
| `bags` | Bolsas de empaque, cajas de cartón | 6109 |
| `packaging` | Contenedores, empaques especiales | 6109 |
| `other` | Cualquier insumo no clasificado | 6100 o 6109 según criterio |

---

## 10. Política de capitalización de Activos Fijos

### 10.1 Umbral de capitalización

| Condición | Tratamiento contable |
|-----------|---------------------|
| Monto > $5,000 MXN **Y** vida útil esperada > 12 meses | **Capitalizar** → `fixed_assets` + `1301 Equipo y Maquinaria` |
| Monto ≤ $5,000 MXN | **Expensear** → `6106 Mantenimiento y Reparación` o `6109 Gastos de Papelería y Empaque` |
| Monto > $5,000 MXN pero vida útil ≤ 12 meses | **Expensear** → `6100 Gastos de Operación` |

**Umbral configurable:** $5,000 MXN. Se puede ajustar por módulo de configuración sin cambiar código.

### 10.2 Métodos de depreciación soportados

| Método | `depreciation_method` | Fórmula |
|--------|----------------------|---------|
| Línea recta | `straight_line` | `monto_mensual = costo_adquisicion / vida_util_meses` |
| Doble saldo decreciente | `double_declining` | (futuro — FASE 6) |
| Unidades de producción | `units_of_production` | (futuro — FASE 6) |

**Actualmente implementado:** solo `straight_line`.

### 10.3 Tipos de activos

| `asset_type` | Vida útil típica (meses) | Cuenta SAT |
|--------------|--------------------------|------------|
| `equipment` | 60 (5 años) | 1301 |
| `vehicle` | 48 (4 años) | 1301 |
| `furniture` | 120 (10 años) | 1301 |
| `computer` | 36 (3 años) | 1301 |
| `other` | 60 | 1301 |

### 10.4 Asiento de baja de activo

Cuando un activo se da de baja (`status=disposed`):
```
journal_entry:
  Debe: 1302 Depreciación Acumulada (por el total depreciado)
  Debe: Pérdida en Baja de Activos (si valor en libros > 0)
  Haber: 1301 Equipo y Maquinaria (por el costo original)
```

---

## 11. Elementos pendientes / Open items

### 11.1 Pendiente de implementación (crítico)

| Item | Módulo | Riesgo si no se implementa | Fase objetivo |
|------|--------|---------------------------|---------------|
| `MercadoPagoWebhookHandler` idempotente | Ventas MP | Ingresos MP no contabilizados (R-07) | FASE 6 |
| `FinancialTraceService` dual-write | Todos | Sin trazabilidad nueva hasta FASE 3 completa | FASE 3 |
| Reconciliación CxC `cuentas_por_cobrar` vs `accounts_receivable` | CxC | Cartera inconsistente (R-01) | FASE 4 |
| `operation_id` en `FinanceService.pagar_nomina()` | Nómina | Doble pago sin detección (R-08) | FASE 4 |
| Proceso batch depreciación mensual | Activos | Depreciaciones sin registrar en periodos sin ejecución manual | FASE 5 |
| Proceso batch conciliación | Todos | Sin detección automática de discrepancias | FASE 6 |

### 11.2 Deuda técnica (no crítico)

| Item | Descripción | Fase sugerida |
|------|-------------|---------------|
| `FinanceService.registrar_asiento()` marcado DEPRECATED | Wrappers hacia `GeneralLedgerService`. Completar migración y eliminar wrapper | FASE 4 |
| `TreasuryService._ensure_tables()` como no-op | Tablas movidas a m082. Función vacía conservada por backward compat. Eliminar en limpieza | FASE 6 |
| `activos` legacy sin enlace a `fixed_assets` | Los activos registrados antes de m083 no tienen `fixed_assets.id`. Requiere migración de datos | FASE 5 |
| Plan de cuentas sin enforced en asientos | `financial_event_log` acepta cualquier string en `cuenta_debe/haber`. Agregar FK a `plan_cuentas` | FASE 5 |
| Comisión delivery sin `journal_entry` dedicado | `DriverSettlementHandler` liquida al conductor pero sin asiento contable formal | FASE 4 |

### 11.3 Decisiones de diseño abiertas (requieren validación)

| Decisión | Opciones | Estado |
|----------|---------|--------|
| ¿Umbral de capitalización $5,000 MXN configurable en BD? | `config` table vs hardcoded vs `module_config` | Pendiente validar con contador |
| ¿`financial_documents` debe reemplazar eventualmente `accounts_payable`? | Reemplazo vs coexistencia permanente | Política actual: coexistencia. Revisar en FASE 7 |
| ¿Conciliación batch diaria o en tiempo real por evento? | Batch nocturno vs EventBus handler | Batch nocturno recomendado (costo menor) |
| ¿Rollos térmicos necesitan inventario por sucursal en FASE 5? | OPEX directo vs inventario auxiliar | Revisar si volumen justifica control |
| ¿`journal_entries` debe reemplazar eventualmente `financial_event_log`? | Reemplazo vs coexistencia | Política actual: coexistencia. Revisar en FASE 7 |

---

## Apéndice A — Índice de archivos de referencia

| Archivo | Descripción |
|---------|-------------|
| `pos_spj_v13.4/migrations/standalone/083_financial_traceability_tables.py` | Definición DDL de todas las tablas canónicas nuevas |
| `pos_spj_v13.4/migrations/standalone/059_plan_cuentas.py` | Catálogo NIF/SAT (41 cuentas) |
| `pos_spj_v13.4/migrations/standalone/082_treasury_tables.py` | Tablas de tesorería (`treasury_ledger`, `treasury_capital`, etc.) |
| `pos_spj_v13.4/core/services/finance/general_ledger_service.py` | `GeneralLedgerService` — motor de libro mayor |
| `pos_spj_v13.4/core/services/finance/treasury_service.py` | `TreasuryService` — motor de tesorería |
| `pos_spj_v13.4/core/services/enterprise/finance_service.py` | `FinanceService` — fachada legacy (wrappers) |
| `pos_spj_v13.4/core/events/handlers/finance_handler.py` | `SaleFinanceHandler`, `CreditSaleFinanceHandler`, `SaleCancelledFinanceHandler` |
| `pos_spj_v13.4/core/events/wiring.py` | Cableado completo de EventBus → handlers |
| `pos_spj_v13.4/core/events/event_bus.py` | Definición de constantes de eventos de dominio |
| `pos_spj_v13.4/docs/architecture/FINANCE_CANONICAL_TABLES.md` | Mapa de tablas canónicas legacy vs nuevas |
| `pos_spj_v13.4/migrations/MIGRATION_LOG.md` | Log de decisiones de migración |

---

*Documento generado como parte de FASE 3 — Rearquitectura SPJ ERP v13.4*  
*Mantener sincronizado con `FINANCE_CANONICAL_TABLES.md` y `MIGRATION_LOG.md`*
