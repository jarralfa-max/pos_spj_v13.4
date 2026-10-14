# FIN-AUD — Respuesta a la auditoría directa de Finanzas (d9f2bca)

Fecha: 2026-10-10. Auditoría recibida: «Auditoría directa del módulo de Finanzas»
(26 hallazgos, 30 escenarios reproducidos, commit d9f2bcaf). Cada hallazgo se
volvió a comprobar contra el código ACTUAL (HEAD posterior a d9f2bca, que ya
traía parte de F01, F22 y F25 por la auditoría de CRM) y se corrigió o se dejó
abierto con su motivo.

Migraciones: **332** (esquema) y **333** (permisos). Pruebas nuevas:
`tests/integration/finance/test_audit_fin_d9f2bca_{integrity,figures,process}.py`
(53 casos, uno o más por escenario del anexo).

## Decisiones tomadas por defecto (revisables)

| Tema | Decisión | Por qué / cómo cambiarla |
|---|---|---|
| Quién opera Finanzas (F02) | Los 24 permisos `FINANZAS.<accion>` se siembran sólo en `system_owner` y `admin`. | Hoy ningún otro rol tiene `FINANZAS.ver`; la migración no cambia quién entra, sólo exige permiso por comando. Abrir a gerente: matriz de permisos. |
| Deuda por venta o por pago (F03) | **Total por venta**, con cada pago como cargo identificado. | El esquema exige un documento por origen; los cargos conservan la trazabilidad por pago. |
| Moneda (F06) | **Una moneda por operación, sin conversión.** Mezclar monedas se rechaza; los saldos se calculan por moneda. | La base real sólo tiene MXN. Multimoneda con tipo de cambio queda abierta. |
| Fecha contable (F17) | `business_date` del productor si viene; si no, día **local** del instante (zona del equipo). | Misma regla que Compras y Caja. No hay calendario por sucursal. |
| Evidencia del pago (F13) | EXECUTED exige referencia externa (folio SPEI/cheque/recibo) y guarda quién ejecutó. | No hay integración bancaria: EXECUTED = contabilizado + evidencia, no "confirmado por el banco". |
| Espejos compartidos (F05) | No se prohíben; se marcan y se cuentan una vez. | Varias cajas POS comparten legítimamente 1102. |

## Hallazgo por hallazgo

| # | Prioridad | Estado | Qué se hizo | Prueba |
|---|---|---|---|---|
| F01 | P0 | Cerrado | Ventas ya usaba `owns_transaction=False` (CRM F01). Compras: la CxP y su asiento se escriben en **una** `FinanceUnitOfWork` (`CreatePayableUseCase.create_in`); un fallo de contabilización ya no deja CxP sin asiento. | `TestF01SingleTransactionOwner` |
| F02 | P0 | Cerrado | `FinanceCommandService` (capa de aplicación) es la única puerta de la UI a los comandos: actor de la sesión viva obligatorio (sin actor se rechaza, se acabó el `"desktop"`), permiso por acción vía `FinanceAuthorizationPolicy` + `FinanceSessionPermissionChecker`, actor propagado a `created_by` del asiento y a la auditoría. Acciones de control separadas (autorizar/ejecutar pago, revertir, cerrar/reabrir, aceptar diferencias). El rechazo ocurre antes de abrir la UoW. | `TestF02CommandAuthorization` |
| F03 | P1 | Cerrado | `RegisterSaleCreditChargeUseCase`: clave por pago (`sale:payment:credit-charge`), deuda total por venta, cargos en `receivable_charges`. Ventas entrega `payment.id`. Si al completar la venta el crédito contabilizado difiere del auxiliar, queda excepción de cierre `SALE_CREDIT_VS_RECEIVABLE`. | `TestF03SeparateCreditPayments` |
| F04 | P1 | Cerrado | Flujo por **método directo** (`CashFlowBuilder`): variación de cuentas de efectivo por asiento, clasificada por la contrapartida del lado opuesto. Efectivo = espejos de banco/caja/fondo/caja POS + cuentas de efectivo/banco de los perfiles. Verifica neto == final − inicial (medidos aparte). | `TestF04DirectCashFlow` |
| F05 | P1 | Cerrado | Posición sólo con asientos contabilizados de la moneda de la cuenta; espejos compartidos marcados (`shared_mirror`) y `treasury_total()` los cuenta una vez. | `TestF05TreasuryPosition` |
| F06 | P1 | Cerrado (moneda única) | Saldos del mayor filtrados por moneda; el motor toma la moneda de las líneas y rechaza mezclas; cobro, pago, aportación y CAPEX validan moneda de la cuenta de tesorería. | `TestF06Currency` |
| F07 | P1 | Cerrado | El match exige la línea de la **cuenta espejo** de la cuenta del estado y su moneda; unicidad global de matches activos (validación + índices únicos parciales). | `TestF07EligibleAndUniqueMatches` |
| F08 | P1 | Cerrado | Completar exige todas las partidas conciliadas o un motivo de diferencia (con permiso aparte). Revertir inactiva matches, libera partidas y conserva quién/cuándo. | `TestF08CompleteAndRevert` |
| F09 | P1 | Cerrado | `SaleCompletedHandler` arma las líneas sin tocar agregados, contabiliza, y aplica canjes / vales prepagados / CxC **sólo si este evento creó el asiento**. Devolución: la nota de crédito, una vez por devolución. | `TestF09F10Idempotency` |
| F10 | P1 | Cerrado | El motor compara el contenido económico (moneda + cuentas/importes/dimensiones) en cada acierto idempotente; misma clave con otro contenido → `IdempotencyConflictError`. Igual en CxC, CxP, cobros y solicitudes de gasto. | `TestF09F10Idempotency` |
| F11 | P1 | Cerrado | CxC/CxP creadas desde Finanzas exigen contrapartida y nacen con asiento (`RECEIVABLE_/PAYABLE_RECOGNITION`); sólo Ventas/Compras (que reconocen en su propio asiento) las crean sin ella. CAPEX sin pagar exige proveedor y crea su CxP en la misma transacción. Control de cierre auxiliar contra mayor (CxC y CxP). | `TestF11SubledgerAndLedgerAgree`, `test_subledger_gap_is_persisted_and_blocks` |
| F12 | P1 | Cerrado | La nota de crédito se aplica también al documento original; no se repite. | `TestF12CreditNoteAppliedToTheInvoice` |
| F13 | P1 | Cerrado | Programar y ejecutar revalidan: proveedor en el maestro (existe, activo, sin bloqueo financiero), cuenta bancaria del proveedor para pagos por banco, tesorería activa, no Caja POS ni monedero, misma moneda, saldo vigente. Evidencia obligatoria guardada con el ejecutor. Pantalla con diálogo de evidencia. | `TestF13PaymentExecutionRevalidates` |
| F14 | P1 | Cerrado | La transferencia general rechaza un monedero promocional como origen o destino. | `TestF14PromotionalBalanceIsNotMoney` |
| F15 | P1 | Cerrado en Finanzas | `expense_requests`: idempotencia antes de comprometer, id de solicitud devuelto; `ResolveExpenseRequestUseCase` devenga contra documento o libera con motivo. **Abierto:** Compras aún no envía el id de solicitud con la factura, así que el devengo automático no está cableado. | `TestF15BudgetCommitments` |
| F16 | P1 | Cerrado (ver abiertos) | Cierre: conciliaciones abiertas acotadas a estados hasta fin de periodo; controles auxiliar-mayor medidos y persistidos; toda excepción abierta del periodo o anteriores bloquea; autorización con motivo (`FINANZAS.periodo.autorizar_excepcion`). La conciliación comercial persiste sus diferencias materiales. El motor ya no abre en silencio un mes anterior a uno cerrado. | `TestF16PeriodClose` |
| F17 | P1 | Cerrado | `event_date` usa `business_date` o el día local; todos los handlers resuelven el perfil con la sucursal del evento por omisión. | `TestF17BusinessDateAndBranchProfile` |
| F18 | P1 | Cerrado | `row_version` + `UPDATE … WHERE row_version=?` en CxC, CxP, documentos y presupuestos; conflicto explícito. | `TestF18OptimisticConcurrency` |
| F19 | P2 | Cerrado | El último mes de vida útil liquida el remanente (33.33/33.33/33.34); asiento con fecha de fin de mes. Meses omitidos no se recuperan a mitad de vida; el último los liquida. | `TestF19DepreciationSchedule` |
| F20 | P2 | Cerrado | `decimal_sum` como única suma monetaria de Finanzas: mayor, estados, flujo, tesorería, tablero, asientos, obligaciones, presupuesto, activos, BI por sucursal/centro de costo, controles de cierre y la verificación de asientos desbalanceados. No queda ningún `SUM(CAST(... AS NUMERIC))` en consultas ni repositorios de Finanzas. | `TestF20Precision` |
| F21 | P1 | Cerrado | `wire_hr_finance` + `dispatch_hr_outbox` (al pagar y al arrancar), con intentos/último error; PAYROLL_PAID trae `occurred_at`. `dispatch_finance_outbox` entrega el `finance_outbox` tras cada comando y al arrancar. | `TestF21PayrollReachesTheLedger` |
| F22 | P1 | Cerrado | Antigüedad: grupo `NO_DUE_DATE` separado de corriente (el plazo desde el perfil ya venía de CRM F23). | `TestF22AgingWithoutDueDate` |
| F23 | P1 | Cerrado | «Cobros» es historial real (`collection_history`). «Conciliación» es un espacio de trabajo: importar estado, conciliar lado a lado, completar, revertir. | `TestF23F24ReadModels` |
| F24 | P2 | Parcial | Asientos con búsqueda y paginación del servidor (más de 200 accesibles); CxC con nombre de cliente, búsqueda y filtro real desde CRM; selectores de tesorería con saldo y moneda. **Abierto:** selector estándar de productos en gastos/activos y búsqueda de proveedores en CxP. | `test_more_than_200_entries_remain_reachable` |
| F25 | P2 | Cerrado | Ya heredaban de `StandardDialog`; ahora el rechazo se explica junto al formulario y lo escrito se conserva. | `TestF25DialogExplainsRejection` |
| F26 | P2 | Cerrado | Reversión como caso de uso (`ReverseJournalEntryUseCase`); proveedores compuestos en `finance_routes`; política única de contabilización de compras (`procurement_posting_policy.py`). `_query` repetido entre bases de consulta y repositorios se deja (la auditoría misma no lo considera razón para otra jerarquía). | suites existentes |

## Validación

- Pruebas nuevas: 53 (`test_audit_fin_d9f2bca_*`), todas pasan.
- Selección amplia (Finanzas, Compras, Caja, Ventas, CRM, Fidelidad, RR. HH., shell, catálogo de permisos): 1425 pasan.
  Los fallos restantes son previos y ajenos a este cambio: 26 pruebas importan `core/`, `repositories/` o
  `modulos/` (ya borrados); 2 por `nav.losses → LOSSES_VIEW`; 2 de navegación de Productos/Cárnico
  (trabajo sin commit de esos módulos); la e2e de Compras falla antes de Finanzas (escenario de
  configuración con proveedor `'sup-1'` no UUIDv7); la guardia de DDL fuera de migraciones ya fallaba
  por decenas de esquemas — `finance_schema.py` quedó dentro de su tolerancia (24→28) y
  `hr_schema.py` (sin tolerancia previa, 15 DDL) suma el `ALTER` de esta auditoría.
- Migraciones 332/333 ejecutadas dos veces sobre una copia de la base real: idempotentes; tesorería sin
  espejos compartidos; flujo directo cuadra con efectivo final (21,090.20); controles de cierre sin
  diferencias.

## Abierto, con motivo

- **Multimoneda real** (F06): no hay tipo de cambio ni diferencias cambiarias; hoy se rechaza mezclar.
- **Devengo automático desde Compras** (F15): falta que el evento de factura lleve el id de solicitud.
- **Obligaciones comerciales contra sus cuentas del mayor** (F16): no se agregó; el mapeo obligación→cuenta depende de perfil y base de reconocimiento (una obligación sin reconocimiento inicial no está en el mayor) y un control ingenuo daría falsos positivos.
- **Calendario por sucursal** (F17) y **apertura automática de periodos futuros** (F16): se mantiene la apertura automática hacia adelante.
- **Integración bancaria** (F13): sin gateway; la evidencia es manual.
- **F24 restante**: selector de productos en gastos/activos y búsqueda de proveedores en CxP.
