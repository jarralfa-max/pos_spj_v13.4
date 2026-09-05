# PROC-19 — Recursos y capacidad: Procesamiento Cárnico

Estado: **DONE** (catálogo área → centro de trabajo → estación → equipo, y
el ciclo de asignación/liberación/mantenimiento de equipo; sin un motor de
programación/capacidad por ventanas de tiempo — "sin construir un APS
completo", §19/§33)

## Alcance y decisión de arquitectura

`ProcessingOrder.production_area_id`/`.work_center_id` (PROC-2) y
`process_executions`/`operator_assignments.work_center_id` (PROC-7/8) ya
existían como referencias TEXT sueltas, a propósito diseñadas como
"placeholder hasta PROC-19" (ver `PROC-5_planning.md`: "eso es PROC-19").
PROC-19 construye el catálogo que esas referencias apuntan a, y — el único
consumidor real nuevo — el ciclo de vida de asignar/liberar/mantener
**equipo** sobre una orden, gemelo estructural de `OperatorAssignment` (§32,
PROC-7) pero para máquinas en vez de personas.

`CapacityValidationService` (PROC-5) ya modelaba "capacidad básica
configurable, sin construir un APS completo" — tomando `capacity_limit`
siempre como argumento del llamador. PROC-19 no le añade lógica nueva; le da
un lugar real donde vivir ese número (`WorkCenter.capacity_per_hour`/
`.capacity_basis`), consistente con la misma restricción deliberada de no
modelar turnos, calendarios ni una cola de reservas por ventana de tiempo.

## Entidades nuevas

Todas maestras (sin `operation_id` — mismo criterio que `Warehouse`/
`WarehouseZone`/`StorageLocation` en Inventory: catálogo administrado por
CRUD, no un hecho transaccional con idempotencia por operación), excepto
`EquipmentAssignment`, que sí es transaccional:

- **`ProductionArea`** — `branch_id`/`warehouse_id`/`code`/`name`/`is_active`.
- **`WorkCenter`** — pertenece a un área; `capacity_per_hour: Decimal`,
  `capacity_basis: Literal["quantity","weight"]` (mismo tipo que
  `CapacityValidationService.CapacityBasis`, no un enum nuevo — un solo
  vocabulario para "por cuál dimensión se mide la capacidad").
- **`ProductionStation`** — subdivisión de un centro de trabajo (línea).
- **`ProductionEquipment`** — `status: EquipmentStatus` (`AVAILABLE`/
  `MAINTENANCE`/`RETIRED`, deliberadamente sin `IN_USE`: si un equipo está
  en uso ahora mismo se determina por si tiene una `EquipmentAssignment`
  activa, no por un cuarto estado — la condición física del equipo y su
  ocupación actual son dos preguntas distintas). `start_maintenance()`/
  `complete_maintenance()` (registra `last_maintenance_at`)/`retire()`
  (terminal, alcanzable desde `AVAILABLE` o `MAINTENANCE`).
- **`EquipmentAssignment`** — idéntico en forma a `OperatorAssignment`:
  `processing_order_id`, `equipment_id`, `assigned_at`/`released_at`,
  `release()`.

## Casos de uso

`CreateProductionAreaUseCase`/`CreateWorkCenterUseCase`/
`CreateProductionStationUseCase`/`RegisterEquipmentUseCase` (todos
`RESOURCE_MANAGE`/`EQUIPMENT_MANAGE`) validan que su padre en la jerarquía
exista (`AREA_NOT_FOUND`/`WORK_CENTER_NOT_FOUND`) antes de crear.
`StartEquipmentMaintenanceUseCase`/`CompleteEquipmentMaintenanceUseCase`/
`RetireEquipmentUseCase` (`EQUIPMENT_MAINTENANCE`/`EQUIPMENT_MANAGE`) delegan
directo en la máquina de estados de la entidad.

`AssignEquipmentUseCase` (`EQUIPMENT_ASSIGN`) es la única pieza con una
regla de negocio real: exige `equipment.is_available` (`AVAILABLE`), fallando
`EQUIPMENT_NOT_AVAILABLE` si el equipo está en mantenimiento o retirado — el
único chequeo de disponibilidad que PROC-19 hace, sin reservar ventanas de
tiempo ni verificar solapamiento entre asignaciones activas.
`ReleaseEquipmentAssignmentUseCase` (`EQUIPMENT_RELEASE`) es idempotente,
igual que `ReleaseOperatorAssignmentUseCase`.

## Nuevos permisos

`RESOURCE_VIEW`/`RESOURCE_MANAGE` (área/centro/estación, una sola acción de
gestión para las tres — igual de coarse que otros catálogos maestros de este
bounded context), `EQUIPMENT_VIEW`/`EQUIPMENT_MANAGE`/`EQUIPMENT_ASSIGN`/
`EQUIPMENT_RELEASE`/`EQUIPMENT_MAINTENANCE`. Registrados en
`core/security/permission_catalog.py` bajo `"PRODUCCION"` (estándar Compras).

## Migración e integridad referencial

`252_meat_processing_resources_schema`: `production_areas` → `work_centers`
→ `production_stations` → `production_equipment` → `equipment_assignments`
(FK en cascada dentro de esta jerarquía, más `equipment_assignments` → FK a
`processing_orders`/`production_equipment`). Las columnas más antiguas que
ya guardaban `work_center_id`/`production_area_id` sin FK
(`processing_orders`, `process_executions`, `operator_assignments`) **no**
se retrofitean con una FK real — SQLite no permite añadir una constraint FK
a una columna existente sin reconstruir la tabla completa, y hacerlo aquí
sería un cambio de esquema mucho más invasivo que el resto de esta fase.
Quedan como referencias de aplicación, sin validar a nivel de base de datos
contra el nuevo catálogo — ver Pendiente.

## Tests

`tests/unit/meat_processing/test_meat_processing_resource_entities.py`
(17 tests: validación de cada entidad, ciclo de mantenimiento completo,
transiciones ilegales, `retire()` terminal, `EquipmentAssignment` idéntico a
`OperatorAssignment` en comportamiento).
`tests/integration/meat_processing/test_meat_processing_resource_use_cases.py`
(13 tests: catálogo completo área→centro→estación→equipo, padre inexistente
rechazado en cada nivel, mantenimiento ida y vuelta, asignación exitosa,
asignación rechazada si el equipo está en mantenimiento, orden/equipo
desconocidos, liberación + idempotencia).

## Pendiente

- Sin validación de que `ProcessingOrder.production_area_id`/`.work_center_id`
  referencien un `WorkCenter`/`ProductionArea` real del catálogo nuevo — ni a
  nivel de base de datos (ver arriba) ni a nivel de aplicación (los use
  cases de creación/liberación de orden, PROC-6, no fueron tocados). Cerrar
  esto exigiría decidir si vale la pena una migración de reconstrucción de
  tabla solo para la FK, o si basta una validación de aplicación.
- Sin ventanas de tiempo/turnos ni detección de solapamiento entre
  asignaciones de equipo — deliberadamente fuera de alcance (§19: "sin
  construir un APS completo").
- `LossCaseRequestPort.request_loss_case(..., equipment_ids=...)` (PROC-15)
  sigue recibiendo siempre una tupla vacía — ahora que `ProductionEquipment`
  existe, un futuro ajuste podría poblarlo desde
  `uow.equipment_assignments.list_by_order(order_id)`, mismo patrón que
  `operator_ids` ya usa con `OperatorAssignment`. No se hizo en esta fase
  para no tocar `yield_use_cases.py` sin que el usuario lo haya pedido.
