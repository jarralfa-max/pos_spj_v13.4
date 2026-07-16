# Module Relocation Map

Mapa obligatorio de reubicación estructural (SPJ_UI_UX_ARCHITECTURE_SKILL.md §3.6).

Estados permitidos: `NOT_STARTED | IN_PROGRESS | WRAPPED | MIGRATED | LEGACY_REMOVED | BLOCKED`

| Módulo | Legacy actual | Frontend nuevo | Backend nuevo | Estado | Wrapper legacy | Pendiente |
| ------ | ------------- | -------------- | ------------- | ------ | -------------- | --------- |
| finanzas | `modulos/finanzas_unificadas.py`, `modulos/finanzas.py`, `modulos/tesoreria.py`, `core/services/finance/*`, `core/services/enterprise/finance_service.py`, `application/services/accounts_receivable_service.py`, `backend/infrastructure/db/repositories/finance_read_repository.py` | `frontend/desktop/modules/finance/` | `backend/domain/finance/`, `backend/application/{commands,dto,queries,use_cases/finance,event_handlers/finance}`, `backend/infrastructure/db/{schema/finance_schema.py,repositories/finance/}` | MIGRATED | Sí (wrappers delgados: finanzas.py, tesoreria.py, proveedores.py) | Plomería operativa remanente documentada en §6 del plan (migra con Caja/Compras/Producción/Clientes) |
| rrhh | `modulos/rrhh.py`, `modulos/rrhh_turnos.py`, `core/rrhh/`, `core/services/rrhh_service.py`, `core/services/rrhh_catalog_service.py`, `core/services/rrhh_turnos_service.py`, `core/services/hr_rule_engine.py`, `core/use_cases/nomina.py` | `frontend/desktop/modules/hr/` | `backend/domain/hr/`, `backend/application/{commands,dto,queries,use_cases/hr,event_handlers/hr}`, `backend/infrastructure/db/{schema/hr_schema.py,repositories/}` | IN_PROGRESS | Pendiente | FASES 1-11 del plan `hr_refactor_execution_plan.md` |
