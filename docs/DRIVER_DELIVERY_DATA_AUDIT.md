# Driver / Delivery Data Audit

## Tablas detectadas
- `drivers`: creada en `repositories/delivery_repository.py` y también en UI (`modulos/delivery.py::_init_tables`) -> deuda técnica.
- `driver_locations`: creada en UI `modulos/delivery.py::_init_tables`.
- `delivery_driver_cuts`: creada en UI `modulos/delivery.py::_init_tables`.
- `delivery_orders`: relación con `driver_id`, `responsable_entrega`, `fecha_asignacion`, `fecha_entrega`.
- `delivery_order_history`: trazabilidad de cambios y observaciones.

## Problemas encontrados
1. La UI crea tablas (`drivers`, `driver_locations`, `delivery_driver_cuts`) en `_init_tables`.
2. SQL de asignación de repartidor estaba en UI (update directo en `delivery_orders`).
3. Selector de repartidor podía no filtrar por sucursal activa.
4. Mensaje de sin repartidores no diferenciaba sucursal.
5. Riesgo de mezcla naming driver/chofer/repartidor entre módulos legacy.

## Relaciones actuales
- `delivery_orders.driver_id -> drivers.id`
- `delivery_driver_cuts.driver_id -> drivers.id` (lógica por convención)
- `driver_locations.driver_id -> drivers.id` (sin FK explícita)

## Correcciones aplicadas
- Nuevo repositorio: `repositories/driver_repository.py`.
- Nuevo servicio: `core/services/driver_service.py`.
- Validaciones de asignación movidas a servicio:
  - driver existe/activo/sucursal.
  - pedido no mostrador/scheduled.
  - estado permitido (`preparacion`).
  - no asignar en entregado/cancelado.
- Registro de historial de asignación en `delivery_order_history`.
- UI Delivery usa `DriverService` para listar activos por sucursal y asignar.

## Queries con riesgo detectadas
- `SELECT id, nombre FROM drivers WHERE activo=1 ORDER BY nombre` sin sucursal.
- `UPDATE delivery_orders SET driver_id=...` desde UI sin validación central.

## Recomendación de ownership
- Creación/evolución schema: migraciones/repositorios.
- Reglas de asignación: `DriverService`.
- UI: solo render/acciones y llamadas a servicio.
