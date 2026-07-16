# Module relocation map

| Módulo | Legacy actual | Frontend nuevo | Backend nuevo | Estado | Wrapper legacy | Pendiente |
| ------ | ------------- | -------------- | ------------- | ------ | -------------- | --------- |
| rrhh | Eliminado del runtime (`modulos/rrhh.py`, `modulos/rrhh_turnos.py`, `core/rrhh/`, servicios RRHH legacy y `core/use_cases/nomina.py`) | `frontend/desktop/modules/hr/` | `backend/domain/hr/`, `backend/application/use_cases/hr/`, `backend/application/queries/*_hr*`, `backend/infrastructure/db/repositories/*hr*`, `backend/infrastructure/db/schema/hr_schema.py` | MIGRATED | No | Fases 1 a 11 cerradas; validación final ejecutada, no quedan rutas runtime RRHH legacy ni lógica funcional de RRHH en carpetas legacy. |
