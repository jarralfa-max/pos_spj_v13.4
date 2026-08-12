# CASH-24 - Impresion

## Alcance implementado

- Contrato canonico `PrintCashDocumentUseCase`.
- Documentos de caja para Corte X, Corte Z, movimientos, safe drops, entregas y reembolsos.
- Renderers HTML y ESC/POS deterministicos.
- Cola de impresion como puerto `CashPrintQueue`.
- Auditoria como puerto `CashPrintAuditRepository`.
- Reimpresion con `original_print_id`, motivo obligatorio y validacion contra el documento original.
- Idempotencia por `operation_id`.
- Evento canonico `CASH_DOCUMENT_PRINTED` con `event_id`, `operation_id`, `entity_id`, `branch_id` y `user_id`.

## Conexion persistente

- CASH-25 conecta `CashPrintRepository` dentro de `CashRegisterUnitOfWork`.
- La cola nace en `cash_print_jobs` y la auditoria en `cash_print_audit`, ambas UUIDv7 born-clean.

## Pendiente operativo

- Reemplazar los gateways directos de `PrintXCutUseCase` y `PrintZCutUseCase` por el nuevo `PrintCashDocumentUseCase` cuando los presenters ya construyan `CashPrintDocument`.
- Conectar adaptadores reales de spool/thermal printer sin meter drivers en application.

## Validacion manual

- [ ] Generar Corte X y encolar impresion.
- [ ] Generar Corte Z y encolar impresion.
- [ ] Reimprimir Corte Z con motivo obligatorio.
- [ ] Confirmar que la auditoria registra usuario, sucursal, impresora, formato, copias y original.
- [ ] Simular impresora fuera de linea y confirmar registro `FAILED`.
