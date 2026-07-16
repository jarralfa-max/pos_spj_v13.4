# Module Relocation Map

Mapa obligatorio de reubicación estructural (SPJ_UI_UX_ARCHITECTURE_SKILL.md §3.6).

Estados permitidos: `NOT_STARTED | IN_PROGRESS | WRAPPED | MIGRATED | LEGACY_REMOVED | BLOCKED`

| Módulo | Legacy actual | Frontend nuevo | Backend nuevo | Estado | Wrapper legacy | Pendiente |
| ------ | ------------- | -------------- | ------------- | ------ | -------------- | --------- |
| finanzas | `modulos/finanzas_unificadas.py`, `modulos/finanzas.py`, `modulos/tesoreria.py`, `core/services/finance/*`, `core/services/enterprise/finance_service.py`, `application/services/accounts_receivable_service.py`, `backend/infrastructure/db/repositories/finance_read_repository.py` | `frontend/desktop/modules/finance/` | `backend/domain/finance/`, `backend/application/{commands,dto,queries,use_cases/finance,event_handlers/finance}`, `backend/infrastructure/db/{schema/finance_schema.py,repositories/finance/}` | MIGRATED | Sí (wrappers delgados: finanzas.py, tesoreria.py, proveedores.py) | Plomería operativa remanente documentada en §6 del plan (migra con Caja/Compras/Producción/Clientes) |
| rrhh | `modulos/rrhh.py` (wrapper delgado), `modulos/rrhh_turnos.py` (eliminado), `core/rrhh/` (eliminado), `core/services/rrhh_service.py` (eliminado), `core/services/rrhh_catalog_service.py` (eliminado), `core/services/rrhh_turnos_service.py` (eliminado), `core/services/hr_rule_engine.py` (eliminado), `core/use_cases/nomina.py` (eliminado) | `frontend/desktop/modules/hr/` (view, presenter, routes, view_models, 9 páginas, dialogs) | `backend/domain/hr/`, `backend/application/{queries/hr,use_cases/hr,event_handlers/hr}`, `backend/infrastructure/db/{schema/hr_schema.py,repositories/hr/}` | MIGRATED | Sí (`modulos/rrhh.py` reexporta `create_hr_view`; sin SQL, lógica ni estilos) | Integración caja↔asistencia y nómina→finanzas vía eventos canónicos (CASH_SHIFT_*, PAYROLL_PAID). Evaluaciones de desempeño pendientes como caso de uso propio. |
