# ORD-16 — Repartidores

Fecha: 2026-08-31. Alcance: master prompt §33-34 (perfiles, disponibilidad, asignación,
aceptación).

## Qué se construyó

- `backend/domain/orders_delivery/driver.py` — `DriverOperationalProfile` (identidad real
  vive en RRHH/Usuarios, §33; esta tabla SOLO guarda hechos operativos: activo, capacidad,
  conteo de asignaciones actuales, límite de efectivo — nunca un directorio de personas
  paralelo) y `DeliveryAssignment` (historial completo propose→accept/reject→activate→
  complete, separado de `DeliveryJob.assigned_driver_id`, que ORD-15 ya trata como el
  campo denormalizado "quién lo trae ahora").
- `AssignmentStatus` enum (§33, los 7 valores) + `DriverAssignmentPolicy` (nunca asignar
  por nombre libre — siempre contra un perfil real con capacidad).
- `RegisterDriverProfileUseCase`, `ProposeAssignmentUseCase` (verifica capacidad antes de
  proponer), `AcceptAssignmentUseCase` (sincroniza `DeliveryJob.assigned_driver_id` al
  aceptar — el job y la asignación quedan consistentes en la misma transacción),
  `RejectAssignmentUseCase` (libera la capacidad reservada).

## Decisiones

- **"Aceptación" (§34) la registra el staff, no el propio repartidor** — no existe todavía
  una PWA de repartidor con autoservicio (ORD-25); mismo criterio ya aplicado en ORD-10/11
  (aprobación del cliente) y ORD-14 (notificación de pickup): documentado como pendiente
  explícito, no simulado.
- **La capacidad se reserva al PROPONER, no al ACEPTAR** — `ProposeAssignmentUseCase`
  incrementa `current_assignment_count` inmediatamente; si se rechaza,
  `RejectAssignmentUseCase` la libera. Evita que dos propuestas simultáneas exploten la
  capacidad de un repartidor mientras ambas están "pendientes de aceptar".
- **Sin validación cruzada de `vehicle_id`** — igual criterio que `driver_id` en ORD-15:
  referencia opaca, sin bounded context de vehículos todavía.

## Tests

18 tests nuevos (12 dominio + 6 integración, incluye enforcement real de capacidad y la
sincronización `DeliveryAssignment.accept() → DeliveryJob.assign_driver()`). Suite
acumulada ORD-1..16: **235/235 pasando** (164 unitarios + 71 de integración, verificados
por separado).

## Pendiente

- PWA de repartidor real (ORD-25) para que la aceptación/rechazo sea autoservicio.
- Rutas (ORD-17) — `DeliveryJob.route_id` y `DeliveryAssignment.vehicle_id` siguen sin un
  bounded context de rutas/vehículos real detrás.
