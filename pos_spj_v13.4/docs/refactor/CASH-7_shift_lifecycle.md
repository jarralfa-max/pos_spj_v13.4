# CASH-7 — Apertura y turnos

Fecha: 2026-08-03  
Estado: `IMPLEMENTED` en la ruta canónica.

## Flujo

- `OpenCashShiftUseCase` valida permiso, scope, límite de fondo, dispositivos activos y asignaciones.
- Apertura, fondo inicial, auditoría, evento y outbox comparten un UnitOfWork.
- El fondo usa `Decimal`; cero es válido y no crea un movimiento vacío.
- Un fondo sobre el umbral exige autorización independiente; sobre el hard cap se rechaza.
- Índices parciales impiden dos turnos activos para la misma caja, cajón, terminal o cajero.
- `SuspendCashShiftUseCase` exige turno abierto y motivo.
- `ResumeCashShiftUseCase` exige turno suspendido.
- `BeginCashShiftClosingUseCase` cambia `OPEN → CLOSING`, sin cerrar ni generar Corte Z.

## Asignación

Caja, cajón y terminal deben pertenecer a la sucursal, estar activos y el cajón/terminal deben estar asignados a la caja. El cajero queda identificado por UUIDv7 dentro del turno.

## Eventos

`CASH_SHIFT_OPENED`, `CASH_SHIFT_SUSPENDED`, `CASH_SHIFT_RESUMED` y `CASH_SHIFT_CLOSING_STARTED` se persisten junto con auditoría y outbox antes del commit.

## Tests

- Apertura y fondo atómicos.
- Dispositivos bloqueados rechazados.
- Umbral y hard cap del fondo.
- Asignación activa duplicada rechazada sin escrituras parciales.
- Suspensión, reanudación y cierre preliminar.
- Guardrail contra `FinanceService`, tablas legacy, `float` y `lastrowid`.
