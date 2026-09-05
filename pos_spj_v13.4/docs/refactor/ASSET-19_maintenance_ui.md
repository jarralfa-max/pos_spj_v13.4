# ASSET-19 — Maintenance UI (Activos / EAM)

Ejecutado: 2026-09-02. §95-96 del prompt maestro.

## Decisión: vista de solo lectura, no el Kanban interactivo que pide §95

§95 dice explícitamente "Mover tarjeta debe invocar UseCase. No modificar estado solo en UI." Eso es imposible de construir honestamente hoy: `MaintenanceWorkOrder` (ASSET-6) tiene una máquina de estados completa en el dominio, pero **no existe ningún caso de uso de aplicación** (`StartMaintenanceWorkOrderUseCase`, `CompleteMaintenanceWorkOrderUseCase`, etc.) que un `dropEvent` pudiera invocar. Construir un Kanban con arrastrar-y-soltar que no mutara nada real habría sido peor que no construirlo — el usuario pensaría que algo pasó cuando no pasó nada.

En vez de eso, esta fase construye dos vistas **de solo lectura**, y lo dice explícitamente en su propio subtítulo visible en la UI (no solo en un comentario de código que nadie usando la app vería):

## Qué se construyó

`frontend/desktop/modules/assets/pages/work_orders_board_page.py` — `WorkOrdersBoardPage`, ruta `assets.maintenance.work_orders`. Tablero agrupado por estado (9 columnas: Solicitadas/Aprobadas/Programadas/Asignadas/En progreso/Pausadas/Esperando refacciones/Esperando proveedor/Completadas), cada tarjeta muestra folio/prioridad/fecha programada. Sin arrastrar-y-soltar.

`frontend/desktop/modules/assets/pages/maintenance_agenda_page.py` — `MaintenanceAgendaPage`, ruta `assets.maintenance.calendar`. §96 pide un calendario día/semana/mes con indicadores vencido/hoy/próximo/bloqueado — no existe ningún componente de calendario-grid en el Design System de este repo (mismo tipo de brecha "aspiracional" que otros módulos ya documentaron para otros componentes nombrados en el prompt maestro), y clasificar "vencido" necesitaría la fecha de hoy más el mismo caso de uso faltante. Esta fase construye una **agenda ordenada por fecha** en su lugar — lo real que sí existe (`scheduled_at` de cada orden abierta), sin inventar un juicio de "vencido/bloqueado" que el backend no hace.

`backend/domain/assets/repository_ports.py`/`backend/application/assets/queries/asset_read_services.py` — se agregó `MaintenanceWorkOrderRepositoryPort.list_all_open(branch_id=None)` y `MaintenanceWorkOrderQueryService.list_all_open()`, ya que ningún método existente de ASSET-14 devolvía "todas las órdenes abiertas de la sucursal" (solo por activo o por estado individual) — extensión aditiva, mismo patrón usado en fases anteriores.

`assets_presenter.py` — nuevo método `work_orders()`, mismo patrón de degradación a lista vacía cuando no hay QueryService wireado.

## Tests

`tests/unit/assets/test_assets_maintenance_ui.py` — presenter (delegación, vacío cuando no wireado), tablero (agrupa por estado, estado vacío, estado de error), agenda (ordena por fecha, excluye órdenes sin fecha programada, estado vacío).

## Siguiente fase

ASSET-20 — Responsive/Touch.
