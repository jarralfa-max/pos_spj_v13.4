# Module Relocation Map

Mapa obligatorio de reubicación estructural (SPJ_UI_UX_ARCHITECTURE_SKILL.md §3.6).

Estados permitidos: `NOT_STARTED | IN_PROGRESS | WRAPPED | MIGRATED | LEGACY_REMOVED | BLOCKED`

Estado CASH-25 (2026-08-08): Caja queda `LEGACY_REMOVED`. Se eliminaron
`modulos/caja.py` y `core/services/caja_ticket_service.py`; la navegacion carga
`frontend/desktop/modules/cash_register/` y la cola/auditoria de impresion nace
en `cash_print_jobs` / `cash_print_audit` via `CashPrintRepository`.

Estado CASH-P0-A/P0-B (2026-08-12): Caja se monta desde
`backend.infrastructure.desktop.cash_register_factory.CashRegisterModuleHost`.
`core/ui/module_loader.py` ya no apunta a `modulos.caja`; el frontend recibe
`CashRegisterPresenter` con dependencias explicitas y los permisos runtime son
exclusivamente `CAJA.accion` con catalogo global alineado.

Estado LOSS-0 (2026-08-01): Mermas/Losses está `IN_PROGRESS`. La UI activa sigue en
`modulos/merma.py`; el objetivo es `frontend/desktop/modules/losses/`,
`backend/domain/losses/`, `backend/application/losses/` y repositorios Losses.
Actualmente conviven `mermas` e `inventory_waste_event`; LOSS-1 debe comenzar por
seguridad y la consolidación funcional posterior debe impedir doble escritura.

Estado LOSS-4 (2026-08-03): existe `frontend/desktop/modules/losses/`, la navegación
global usa únicamente `MERMAS` y el sidebar interno es canónico. Estado `IN_PROGRESS`:
Desde LOSS-5, Registro usa `LossRegistrationPage`; el bridge temporal hacia
`modulos/merma.py` fue eliminado.

Estado SHELL-18 (2026-08-20): infraestructura del shell nuevo (bootstrap,
seguridad, provisioning, autenticación, sesiones, Composition Root, módulos,
rutas, navegación, shell, lifecycle, shutdown) queda `MIGRATED` — validada
end-to-end, sin mocks: un login real (`AuthenticationCoordinator`, vía
`build_authentication_coordinator()` en
`frontend/desktop/shell/desktop_shell_authentication_composition.py`)
produce un `ApplicationContext` real que, envuelto en `LegacySessionAdapter`
(`backend/bootstrap/legacy_session_adapter.py`), construye un
`ApplicationWindow` real y navegable (`build_application_window()` en
`frontend/desktop/shell/desktop_shell_window_composition.py`) con los 9
módulos ya migrados (sales_pos, cash_register, inventario, transferencias,
productos, clientes/CRM, compras, finanzas, rrhh) registrados, enrutables y
visibles en el sidebar — primera vez que esta cadena completa corre en este
repositorio.

Suite de validación SHELL-18: 1454 passed, cero regresiones en bootstrap,
seguridad, provisioning, autenticación, sesiones, Composition Root, módulos,
rutas, navegación, shell, lifecycle y shutdown. Las 75 fallas de
`tests/architecture/` son la línea base preexistente (confirmada
byte-a-byte idéntica contra ejecuciones aisladas previas de este mismo
trabajo), ninguna introducida aquí. Bootstrap limpio contra una BD nueva en
disco: 6/6 pasos y 6/6 checks de salud en `HEALTHY`. Secret scanning
(patrones AWS/GitHub/Slack/OpenAI/clave privada) sobre el árbol completo:
sin hallazgos.

Pendiente explícito, NO cubierto por este `MIGRATED`: `main.py` sigue
arrancando por la ruta legacy (`AppContainer`/`MainWindow`/`MenuLateral`/
`DialogoLogin`) — el shell nuevo existe, está probado end-to-end y es
sustituible, pero el corte real (cutover) de `main.py` es una decisión
separada, de mayor alcance, aún no tomada. Quedan ~15 módulos del menú
legacy (dashboard, merma, delivery, cotizaciones, producción, etiquetas,
planeación de compras, activos, growth engine, fidelidad, BI, WhatsApp,
diseñador de tickets, 3 pantallas de configuración) sin
`shell_registration.py` propio — SHELL-17 (eliminación de legacy) permanece
bloqueada hasta que `main.py` apunte al shell nuevo y todos los módulos
estén migrados.

| Módulo | Legacy actual | Frontend nuevo | Backend nuevo | Estado | Wrapper legacy | Pendiente |
| ------ | ------------- | -------------- | ------------- | ------ | -------------- | --------- |
| finanzas | `modulos/finanzas_unificadas.py`, `modulos/finanzas.py`, `modulos/tesoreria.py`, `core/services/finance/*`, `core/services/enterprise/finance_service.py`, `application/services/accounts_receivable_service.py`, `backend/infrastructure/db/repositories/finance_read_repository.py` | `frontend/desktop/modules/finance/` | `backend/domain/finance/`, `backend/application/{commands,dto,queries,use_cases/finance,event_handlers/finance}`, `backend/infrastructure/db/{schema/finance_schema.py,repositories/finance/}` | MIGRATED | Sí (wrappers delgados: finanzas.py, tesoreria.py, proveedores.py) | Plomería operativa remanente documentada en §6 del plan (migra con Caja/Compras/Producción/Clientes) |
| rrhh | `modulos/rrhh.py` (wrapper delgado), `modulos/rrhh_turnos.py` (eliminado), `core/rrhh/` (eliminado), `core/services/rrhh_service.py` (eliminado), `core/services/rrhh_catalog_service.py` (eliminado), `core/services/rrhh_turnos_service.py` (eliminado), `core/services/hr_rule_engine.py` (eliminado), `core/use_cases/nomina.py` (eliminado) | `frontend/desktop/modules/hr/` (view, presenter, routes, view_models, 9 páginas, dialogs) | `backend/domain/hr/`, `backend/application/{queries/hr,use_cases/hr,event_handlers/hr}`, `backend/infrastructure/db/{schema/hr_schema.py,repositories/hr/}` | MIGRATED | Sí (`modulos/rrhh.py` reexporta `create_hr_view`; sin SQL, lógica ni estilos) | Integración caja↔asistencia y nómina→finanzas vía eventos canónicos (CASH_SHIFT_*, PAYROLL_PAID). Evaluaciones de desempeño pendientes como caso de uso propio. |
| inventario | `modulos/inventario_enterprise.py` (monta la UI enterprise), `modulos/merma.py` (inyecta adaptador canónico), `core/services/inventory_service.py` (shim → ledger canónico), `core/services/inventory/canonical_waste_adapter.py` | `frontend/desktop/modules/inventory/` (view, presenter, routes, view_models, páginas INV-25) | `backend/domain/inventory/`, `backend/application/inventory/{use_cases,queries,cutover,labels,notifications,analytics}`, `backend/application/event_handlers/inventory/`, `backend/infrastructure/db/{schema/inventory_schema.py,repositories/inventory/}` | MIGRATED | Sí (`inventory_service.py` delega en `CanonicalInventoryRepository`) | Cutover activo por flag (migración 134). DROP destructivo de tablas legacy no relacionadas con Transferencias permanece diferido. |
| transferencias | eliminado | `frontend/desktop/modules/transfers/` (view, presenter, sidebar, 15 páginas, diálogos y view models) | `backend/domain/transfers/`, `backend/application/transfers/`, `backend/infrastructure/db/{schema/transfers_schema.py,repositories/transfers/}` | MIGRATED | No | Ninguno; validación final TRF-23 y guardrails TRF-22 activos. |
| compras | Eliminados monolito, servicios `application/purchases`, repositorios `purchase_*`/`compras_*` y entrada separada de compra directa | `frontend/desktop/modules/purchasing/` | `backend/domain/procurement/`, `backend/application/procurement/`, `backend/infrastructure/db/repositories/procurement/` | LEGACY_REMOVED | Sí (`modulos/compras_enterprise.py`, wrapper mínimo) | Planeación de compras permanece como bounded context/fase separada; no es una ruta de ejecución de Procurement. |
| logística | Eliminados `recepcion_qr_widget.py`, `recepcion_qr_service.py` y QR/recepción duplicados dentro de Procurement | `frontend/web/logistics/` y referencias read-only desde `PurchasingModuleShell` | `backend/domain/logistics/`, `backend/application/logistics/`, `backend/api/routers/mobile_logistics.py`, `backend/infrastructure/db/repositories/logistics_repository.py`, migración `171_logistics_bounded_context_schema.py` | LEGACY_REMOVED | No | Recepción física continúa siendo propiedad de Inventario/Almacén; Procurement solo consulta referencias. |
| configuración | `ui/themes/theme_engine.py`, `core/services/theme_service.py`, `modulos/config_modules.py`, `modulos/config_hardware.py`, `modulos/configuracion.py` | `frontend/desktop/modules/configuracion/` (view, presenter, routes, navigation, 9 páginas — General/Dispositivos/Documentos/Pantalla del cliente/Integraciones/Feature Flags/Apariencia/Notificaciones/Offline —, dialogs) | `backend/domain/{settings,device_management,document_output,customer_display,integrations,feature_flags,appearance,notifications,offline}/` (SET-0..23), `backend/application/{configuracion,queries/configuracion,use_cases/configuracion}/` | IN_PROGRESS | No | Registrado en `main_window.py`/`menu_lateral.py` como entrada adicional "Configuración (Nuevo)" (SET-25), junto a — no en reemplazo de — los 3 legacy. 4 de 9 secciones con escritura real: Feature Flags, Apariencia, **Dispositivos** (registrar/editar/activar/desactivar/bloquear/retirar dispositivos+perfiles), **Documentos** (crear plantilla+v1, nuevas versiones, ciclo de aprobación de 7 estados); las 5 restantes son de solo lectura por ahora (alcance documentado, no un descuido). `modulos/config_interfaz.py` (la pantalla "Apariencia" legacy, ya rota) fue eliminada — confirmado 100% muerta, nunca alcanzable. Las 3 pantallas de configuración legacy restantes (`config_modules.py`/`config_hardware.py`/`configuracion.py`) permanecen intactas y en uso — cubren funcionalidad real (cierre mensual, SMTP, hardware, alternado de módulos) que el módulo nuevo aún no iguala. |
