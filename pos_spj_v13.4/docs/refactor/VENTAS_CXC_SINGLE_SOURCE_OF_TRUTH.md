# VENTAS — CxC Single Source of Truth (FASE 9)

Fecha: 2026-05-27  
Estado: propuesta ejecutable incremental (sin cambios destructivos de esquema en esta fase).

## 1) Objetivo
Definir una **fuente única de verdad** para CxC de ventas a crédito y evitar doble escritura entre:
- `cuentas_por_cobrar`
- `accounts_receivable`
- `financial_documents`

Además, alinear trazabilidad con:
- `clientes.saldo` / `clientes.credit_balance`
- `financial_event_log`
- `journal_entries`
- `movimientos_caja`
- `treasury_ledger`
- `treasury_movements`

---

## 2) Hallazgos de auditoría técnica

### 2.1 Escrituras CxC detectadas
1. **Ruta de venta principal** (`SalesService.execute_sale`) no crea CxC directa; delega a handlers de `SALE_ITEMS_PROCESS`.
2. `CreditSaleFinanceHandler` está suscrito a `SALE_ITEMS_PROCESS` (prioridad 85) y es el punto más cercano a writer canónico para CxC de venta crédito.
3. Existen servicios alternos capaces de crear deuda/documento:
   - `AccountsReceivableService` → `accounts_receivable`
   - `FinancialDocumentService` → `financial_documents`
4. `FinanceService` y módulos financieros consultan múltiples tablas (legacy + nuevas), generando riesgo de lectura inconsistente.

### 2.2 Riesgo de doble CxC
Riesgo alto de duplicidad cuando:
- un flujo crea CxC en `cuentas_por_cobrar` vía handler;
- otro flujo vuelve a crear deuda equivalente en `accounts_receivable` o `financial_documents`.

### 2.3 Saldos de cliente
- `clientes.saldo` y aliases como `credit_balance` funcionan como snapshot/read model,
  pero no deben ser tratados como ledger canónico de CxC.

---

## 3) Decisión arquitectónica (FASE 9)

## 3.1 Tabla canónica temporal (runtime actual)
**`cuentas_por_cobrar`**

Motivo:
- ya está integrada al flujo de venta crédito vía `CreditSaleFinanceHandler` en `SALE_ITEMS_PROCESS`;
- participa en el momento transaccional correcto de la venta;
- minimiza riesgo de romper operación actual.

## 3.2 Tabla canónica futura (target)
**`financial_documents`** (document ledger unificado)

Motivo:
- modelo unificado para CxC/CxP;
- soporte explícito de `operation_id` idempotente;
- mejor trazabilidad ERP y convergencia contable.

## 3.3 Writer único permitido (regla)
**Solo `CreditSaleFinanceHandler` debe crear CxC automática por venta crédito, dentro de `SALE_ITEMS_PROCESS`**.

Prohibido (durante fase incremental):
- crear CxC de venta crédito directamente desde UI;
- duplicar CxC desde `SalesService` post-commit;
- recrear documento equivalente por otro handler sin verificación por `operation_id`.

---

## 4) Política de coexistencia (sin ruptura)

1. `cuentas_por_cobrar` = **source of truth temporal** para venta crédito POS.
2. `accounts_receivable` y/o `financial_documents` = **read model / compatibilidad** mientras dura migración.
3. Cualquier proceso de espejo (sync) debe ser **idempotente por `operation_id`** y nunca crear segundo documento económico.
4. En reportes, priorizar una sola fuente por reporte y etiquetar origen de datos.

---

## 5) Estrategia anti-duplicidad

## 5.1 Llave idempotente obligatoria
Para CxC de venta crédito:
- `operation_id` derivado de la venta (`sale_operation_id` o `sale_id + tipo_evento`).

## 5.2 Constraint recomendado
Agregar constraint único en writer canónico (cuando aplique migración SQL):
- `UNIQUE(operation_id)` en tabla de CxC canónica.
- Si no existe `operation_id`, usar llave compuesta temporal: `(venta_id, tipo_documento)`.

## 5.3 Guardrail en handlers
`CreditSaleFinanceHandler` debe:
- verificar existencia previa por `operation_id` antes de insertar;
- registrar no-op idempotente si reintento detectado;
- no lanzar segunda escritura de deuda.

---

## 6) Reconciliación de saldos de cliente

### 6.1 Fuente de cálculo de saldo usado
`SUM(saldo_pendiente)` de CxC canónica (temporal: `cuentas_por_cobrar`).

### 6.2 `clientes.saldo` / `credit_balance`
Tratar como cache/read projection.

### 6.3 Job de conciliación recomendado
- recalcular saldo de cliente desde CxC canónica;
- comparar contra `clientes.saldo`;
- registrar diferencias en `financial_event_log` con tipo `CXC_RECONCILIATION`.

---

## 7) Casos de pago y criterio financiero

1. **Venta contado**
   - no crea CxC.
   - registra ingreso en caja/tesorería según policy.

2. **Venta crédito**
   - crea una sola CxC en writer canónico (handler crédito).

3. **Mercado Pago pendiente**
   - no registra ingreso definitivo hasta confirmación de pago.
   - no debe crear CxC de crédito comercial salvo regla explícita de negocio.

4. **Reintento con mismo `operation_id`**
   - no duplica CxC ni movimientos financieros.

---

## 8) Plan de implementación incremental

## Paso 1 (inmediato)
- Bloquear nuevos writers de CxC fuera de handler canónico.
- Documentar tabla canónica temporal por módulo/report.

## Paso 2
- Instrumentar/verificar idempotencia `operation_id` en `CreditSaleFinanceHandler`.
- Añadir pruebas de reintento.

## Paso 3
- Definir bridge controlado `cuentas_por_cobrar -> financial_documents` (one-way, idempotente).

## Paso 4
- Migrar reportes a `financial_documents` cuando cobertura sea completa.

---

## 9) Tests mínimos requeridos (aceptación Fase 9)

1. `venta_credito_crea_una_sola_cxc`
2. `reintento_mismo_operation_id_no_duplica_cxc`
3. `venta_contado_no_crea_cxc`
4. `mercadopago_pendiente_no_registra_ingreso_hasta_confirmacion`

> Nota: en esta fase documental no se altera esquema; los tests se implementan en fases de endurecimiento financiero/eventos.

---

## 10) Riesgos abiertos

1. Coexistencia prolongada de múltiples tablas CxC.
2. Reportes que mezclan fuentes sin indicar precedencia.
3. Handlers legacy sin control de idempotencia fuerte.

Mitigación: reforzar `operation_id`, unificar writer y mantener catálogo de eventos financiero asociado.
