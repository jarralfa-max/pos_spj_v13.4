# ORD-6 — Pedidos programados

Fecha: 2026-08-30. Alcance: master prompt §19.

## Qué se construyó

- `ScheduleStatus` enum (`NOT_APPLICABLE|SCHEDULED|ACTIVATION_PENDING|ACTIVATED|
  RESCHEDULED|CANCELLED|MISSED`) — ciclo de vida de la programación, independiente de
  `OrderStatus` (un pedido programado puede estar CONFIRMED mientras su programación
  todavía está SCHEDULED).
- `CustomerOrder` ganó 4 campos (`delivery_window_start/end`, `activation_at`,
  `schedule_status`) y 4 métodos: `schedule()`, `reschedule()`, `activate_schedule(now=...)`,
  `cancel_schedule()`.
- `ScheduledOrderPolicy` (dominio puro, sin reloj propio — recibe `now` como parámetro):
  valida ventana (`window_end > window_start`) y si la activación ya corresponde.
- Esquema: 4 columnas nuevas en `customer_orders` + índice
  `(schedule_status, activation_at)` — se editó directamente la migración 226 (esquema aún
  no liberado a producción, cero instalaciones reales dependiendo de ella todavía).
- Casos de uso: `ScheduleOrderUseCase`, `RescheduleOrderUseCase`,
  `ActivateScheduledOrderUseCase` (`backend/application/orders_delivery/use_cases/
  scheduled_order_use_cases.py`), gateados con `ORDER_SCHEDULE`/`ORDER_RESCHEDULE` (ORD-1).

## Decisiones

- **Activación NO evalúa disponibilidad/capacidad/ruta** — el propio §19 lo pide, pero eso
  requiere Inventario (ORD-8) y Rutas (ORD-17), que no existen todavía. `activate_schedule()`
  solo valida las reglas que el dominio puro puede detectar (estado válido, tiempo cumplido).
  La evaluación cross-context queda para cuando esos bounded contexts existan.
- **`now` se inyecta, nunca se lee del reloj del sistema dentro del dominio** — permite
  testear determinísticamente "activación antes de tiempo" sin mockear `datetime.now`.
- **Reutiliza permisos existentes** — no se crearon códigos nuevos para "activar"; se
  reutiliza `ORDER_SCHEDULE` (activación es la culminación del ciclo de programación, no
  una acción de usuario final distinta — normalmente la dispara un scheduler/cron).

## Tests

30 tests nuevos (17 dominio + 13 integración), suite acumulada ORD-1..6: **93/93 pasando**.

## Pendiente

- Un disparador real (cron/scheduler) que llame `ActivateScheduledOrderUseCase` en el
  momento correcto no existe todavía — es trabajo de infraestructura de una fase posterior.
- `MISSED` (programación que pasó su ventana sin activarse) no tiene lógica de detección
  todavía — requiere el mismo disparador periódico.
