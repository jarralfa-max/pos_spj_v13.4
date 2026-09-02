# ORD-17 — Rutas

Fecha: 2026-08-31. Alcance: master prompt §35 (ruta, paradas, secuencia, ETA —
"planificación básica", sin optimizador).

## Qué se construyó

- `RouteStatus` (DRAFT/PLANNED/ASSIGNED/ACTIVE/COMPLETED/CANCELLED) y `RouteStopStatus`
  (PENDING/ARRIVED/COMPLETED/SKIPPED) enums.
- `backend/domain/orders_delivery/route.py` — `DeliveryRoute` + `DeliveryRouteStop`.
  Soporta una o varias entregas, secuencia (`ordered_stops`), ETA por parada
  (`estimated_arrival_at`). Sin optimizador de distancia/tiempo — literal del prompt
  maestro.
- `RoutePolicy` — tabla de transiciones + `ensure_can_add_stop` (SOLO en DRAFT) +
  `ensure_unique_sequence`.
- `DeliveryRouteRepository` (mismo patrón delete-then-reinsert de paradas que
  `CustomerOrderRepository` con líneas).
- `CreateRouteUseCase`, `AddStopToRouteUseCase` (sincroniza `DeliveryJob.route_id`),
  `PlanRouteUseCase` — reutilizan `ROUTE_PLAN` de ORD-1.

## Bug real encontrado y corregido antes de cerrar la fase

**`RoutePolicy.ensure_can_add_stop` permitía agregar paradas tanto en DRAFT como en
PLANNED** — un test que agregaba una parada después de planificar la ruta debía fallar y
no lo hacía. Esto habría permitido que una ruta "planificada" cambiara de contenido sin
ninguna re-planificación explícita, contradiciendo la propia idea de "planificar" como un
punto de congelamiento de la secuencia. Corregido: solo DRAFT acepta paradas nuevas —
re-planificación (editar una ruta ya planificada) queda fuera de alcance de esta fase,
consistente con "planificación básica".

## Decisiones

- **Sin asignación de ruta a conductor ni activación como casos de uso en esta fase** —
  `DeliveryRoute.assign_driver()/activate()/complete()/cancel()` ya existen en el
  agregado (mismo criterio que ORD-15/16: construir el ciclo de vida completo ahora,
  cablear los casos de uso restantes cuando la fase correspondiente los necesite —
  ORD-18, despacho).
- **`DeliveryJob.route_id` se sincroniza al agregar la parada**, no al planificar — un
  job ya "sabe" a qué ruta pertenece desde que se agrega, aunque la ruta en sí siga en
  DRAFT.

## Tests

13 tests nuevos (9 dominio + 4 integración). Suite acumulada ORD-1..17: **248/248
pasando** (173 unitarios + 75 de integración, verificados por separado).

## Pendiente

- Asignación de ruta a repartidor y activación como casos de uso reales (ORD-18).
- Distancia/tiempo estimado real (requiere un proveedor de mapas — infraestructura futura,
  no bloquea esta fase per el propio prompt maestro).
