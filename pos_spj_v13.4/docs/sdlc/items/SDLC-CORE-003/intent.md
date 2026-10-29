# SDLC-CORE-003 — La UI crea esquema y repositorios SQLite (22 archivos de frontend importan infraestructura)

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
RRHH y Proveedores ejecutan DDL (`create_hr_schema`, `create_supplier_schema`) cada vez que se construye la vista; `configuracion_routes.py` instancia `Sqlite*Repository`. 22 archivos de `frontend/` importan `backend.infrastructure` (peores: `sales_pos/composition.py` 11, `app.py` 10, `configuracion_routes.py` 7).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/hr/hr_routes.py:90,98`
- `frontend/desktop/modules/finance/suppliers/supplier_routes.py:52`
- `frontend/desktop/modules/configuracion/configuracion_routes.py:140-206`

## Impacto
Bloquea la arquitectura objetivo (CLAUDE.md regla 7).

## Objetivo
- DDL sólo en migraciones/bootstrap.
- Composición en `backend/bootstrap` o `infrastructure/desktop`; prueba de arquitectura que limite el número de importaciones (ratchet).

## Alcance
- **Incluye:** Composición de RRHH, Proveedores, Configuración + ratchet.
- **No incluye:** Resto de módulos (ítems posteriores).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria PASS 1-3.

## Preguntas abiertas
- Ninguna por ahora.
