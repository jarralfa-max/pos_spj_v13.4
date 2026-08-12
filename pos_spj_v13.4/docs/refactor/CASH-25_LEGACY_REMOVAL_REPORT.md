# CASH-25 - Eliminacion de legacy

## Eliminado

- `modulos/caja.py`.
- `core/services/caja_ticket_service.py`.
- Import legacy `from modulos.caja import ModuloCaja`.
- Diagnostico legacy `modulos.caja`.
- Wiring `container.caja_ticket_service`.
- Entrada `modulos/caja.py` en allowlist de defaults numericos UI.
- Tests que protegian la ruta legacy de tickets fueron repuntados a `PrintCashDocumentUseCase`/renderers canonicos.

## Consolidado

- La navegacion principal carga `frontend.desktop.modules.cash_register.CashRegisterWorkspace`.
- La UI de Caja vive en `frontend/desktop/modules/cash_register/`.
- La impresion de Caja vive en `backend/application/cash_register/printing.py`.
- Los renderers viven en `backend/infrastructure/printing/cash_register_renderers.py`.
- La cola/auditoria persistente vive en `CashPrintRepository`.
- `CashRegisterUnitOfWork.printing` expone la cola/auditoria born-clean.
- `cash_print_jobs` y `cash_print_audit` nacen en la migracion `175_cash_register_bounded_context_schema.py`.

## Inventario y clasificacion

- `modulos/caja.py`: eliminado, era UI legacy con dialogos, impresion y presentacion historica.
- `core/services/caja_ticket_service.py`: eliminado, era servicio legacy de impresion/PDF de Corte Z.
- `print_job_log`: tabla legacy historica no usada por Caja canonica; no se reutiliza para evitar identidad/deuda dual.
- `cash_print_jobs`: tabla canonica de cola.
- `cash_print_audit`: tabla canonica de auditoria.

## Allowlist

- La allowlist especifica de Caja para defaults numericos queda vacia.
- Los guardrails ahora exigen ausencia de `modulos/caja.py`.

## Pendientes fuera de esta fase

- Adaptador fisico de spool/thermal printer sobre `cash_print_jobs`.
- Repuntar `PrintXCutUseCase` y `PrintZCutUseCase` para construir `CashPrintDocument` directamente.
- DROP final de tablas legacy financieras/caja compartidas cuando Finanzas cierre su propio cutover.
