# HR (RRHH) Refactor Execution Plan — Bounded Context de Recursos Humanos

> Estado global: **IN_PROGRESS**
> Fecha: 2026-07-16
> Skills (prioridad): SPJ_REFACTOR_SKILL.md → SPJ_UI_UX_ARCHITECTURE_SKILL.md → SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

---

## 1. Inventario legacy (a sustituir)

### 1.1 UI (PyQt con lógica de negocio)

| Archivo | Líneas | Problemas |
|---|---|---|
| `modulos/rrhh.py` | 1,503 | Monolito con SQL/estilos; cálculo de nómina y asistencia en la vista |
| `modulos/rrhh_turnos.py` | 344 | Turnos con lógica en widget |

### 1.2 Servicios y use cases legacy

| Ubicación | Líneas | Nota |
|---|---|---|
| `core/rrhh/` (domain/application/infrastructure + events.py) | — | DDD parcial legacy; vocabulario español de eventos |
| `core/services/rrhh_service.py` | 297 | Servicio monolítico |
| `core/services/rrhh_catalog_service.py` | 158 | Catálogos |
| `core/services/rrhh_turnos_service.py` | 140 | Turnos |
| `core/services/hr_rule_engine.py` | — | Reglas laborales dispersas |
| `core/use_cases/nomina.py` | 193 | **Ruta de nómina legacy** (a eliminar en FASE 8) |

### 1.3 Tablas legacy (m000 + standalone)

`personal`, `asistencias`, `nomina_records`, `nomina_pagos`, `evaluaciones_personal`,
`turno_roles`, `turno_asignaciones`, `turno_notificaciones_log`.
Migraciones: `093_rrhh_payroll_traceability`, `094_rrhh_delivery_cleanup_schema`,
`095_rrhh_identity_links` (agrega `usuarios.personal_id` — **se conserva el patrón de vínculo**).

### 1.4 Eventos (vocabulario dual)

- `core/rrhh/events.py`: `NOMINA_GENERADA/AUTORIZADA/PAGADA/CANCELADA`, `ASISTENCIA_REGISTRADA`, `EMPLEADO_*` (español).
- Canónico en inglés: solo `PAYROLL_PAID` existe (consumido por el bridge financiero `PayrollFinanceHandler`).

### 1.5 Integración Caja (violaciones detectadas)

- `CashRegisterApplicationService.open_shift` publica `CASH_SHIFT_OPENED` con `"user": nombre` — **usa nombre como identidad**, sin `user_id` ni `employee_id`.
- No existe `CloseCashShiftUseCase` que publique `CASH_SHIFT_CLOSED` con `employee_id`.
- No hay handler que convierta apertura/cierre de caja en marcaciones de asistencia.

### 1.6 Consumidores de legacy a actualizar

`interfaz/main_window.py` (`ModuloRRHH`, `ModuloRRHHTurnos`), `interfaz/menu_lateral.py`,
`core/app_container.py`, `core/events/wiring.py`, `core/ui/module_loader.py`,
`application/use_cases/__init__.py`.

### 1.7 Infraestructura reutilizable (se conserva)

- `backend/shared/ids.py` (`new_uuid` UUIDv7), `backend/shared/events/` (EventName), `backend/infrastructure/db/` (UoW, transaction).
- `frontend/desktop/components/` (StandardTable, MoneyInput, inputs) y patrón `frontend/desktop/modules/finance/` como referencia arquitectónica.
- `usuarios.personal_id` (vínculo usuario↔empleado, migración 095) — el nuevo esquema lo formaliza como `users.employee_id`.
- Bridge financiero: `PayrollFinanceHandler` ya consume `PAYROLL_PAID` → la nueva nómina publica ese evento canónico.

## 2. Arquitectura destino

```
backend/domain/hr/            entities, value_objects, enums, exceptions, policies/, services/, repository_ports
backend/application/          commands/, dto/, queries/, use_cases/hr/, event_handlers/hr/
backend/infrastructure/db/    schema/hr_schema.py, repositories/{employee,department,position,attendance,...}
frontend/desktop/modules/hr/  hr_view + presenter + routes + 8 pages + dialogs
```

Principios: UUIDv7 born-clean; UI sin SQL/repos/DB; lecturas por QueryService, mutaciones por UseCase;
reglas laborales en `domain/hr/policies`; marcaciones inmutables + jornadas calculadas; nómina
generar→autorizar→pagar idempotente; asistencia desde Caja por eventos (nunca llamada directa).

## 3. Estado de fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Auditoría + este plan | ✅ COMPLETE |
| 1 | Dominio + esquema limpio UUIDv7 | ✅ COMPLETE |
| 2 | Repositorios + QueryServices + DTOs | ✅ COMPLETE |
| 3 | Empleados, catálogos, permisos, vínculo usuario↔empleado | ✅ COMPLETE |
| 4 | Asistencia manual + jornada + ajustes + incidencias | ✅ COMPLETE |
| 5 | Integración Caja↔Asistencia por eventos | ✅ COMPLETE |
| 6 | Turnos laborales | ✅ COMPLETE |
| 7 | Vacaciones y permisos | ✅ COMPLETE |
| 8 | Nómina canónica idempotente | ✅ COMPLETE |
| 9 | UI/UX enterprise (`frontend/desktop/modules/hr/`: 9 páginas + diálogos) | ✅ COMPLETE |
| 10 | Eliminación de legacy (`modulos/rrhh*`, `core/rrhh/`, servicios y nómina legacy) | ✅ COMPLETE |
| 11 | Validación final (tests de arquitectura HR, born-clean UUIDv7, sin SQL en UI) | ✅ COMPLETE |

Estado global: **MIGRATED**. La UI de RRHH vive en `frontend/desktop/modules/hr/`
y delega en el bounded context (`backend/domain/hr`, `backend/application/**/hr`,
`backend/infrastructure/db/{schema/hr_schema.py,repositories/hr}`). Nómina sigue la
secuencia canónica Generar→Autorizar→Pagar (idempotente, un solo `PAYROLL_PAID`
para finanzas). Caja↔Asistencia se integra por eventos (`CASH_SHIFT_OPENED/CLOSED`).
111 tests HR verdes (dominio, integración, arquitectura).

## 4. Lista de eliminación (FASE 10)

`modulos/rrhh.py`, `modulos/rrhh_turnos.py`, `core/rrhh/`, `core/services/rrhh_service.py`,
`core/services/rrhh_catalog_service.py`, `core/services/rrhh_turnos_service.py`,
`core/services/hr_rule_engine.py`, `core/use_cases/nomina.py`, tablas legacy (§1.3, born-clean),
`docs/refactor/rrhh_refactor_plan.md` (reemplazado por este documento).

## 5. Riesgos

1. La nómina legacy (`core/use_cases/nomina.py`) y el bridge financiero conviven; el corte debe mantener
   una sola ruta a `PAYROLL_PAID` sin doble movimiento financiero.
2. La integración de Caja está acoplada a `finanzas_service.abrir_turno` con nombre de usuario; el nuevo
   evento debe portar `user_id`+`employee_id` sin romper el flujo de Caja existente.
3. `personal` es referenciada por drivers/comisiones/delivery; el corte a `employees` requiere el vínculo
   `users.employee_id` y migración born-clean sin rescate.
