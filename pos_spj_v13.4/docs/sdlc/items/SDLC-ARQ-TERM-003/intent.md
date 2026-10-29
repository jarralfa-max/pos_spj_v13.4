# SDLC-ARQ-TERM-003 — El login no verifica el estado del dispositivo: una terminal bloqueada o retirada sigue vendiendo

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §6 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R6.1 / R6.7 Estado de dispositivo en login, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-001

## Problema
El login valida identidad, cuenta, bloqueo y que el rol cubra el sitio, pero nunca lee el estado de la terminal (`workstations.status` BLOCKED/RETIRED ni el SUSPENDED central) ni compara el tipo de terminal con lo que el usuario intenta hacer. El documento exige que una terminal nueva o suspendida no haga operaciones productivas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/authentication/authenticate_user_use_case.py:87-99`
- `backend/bootstrap/application_context_builder.py:81-87`
- `backend/infrastructure/db/schema/settings_schema.py:172-175` (estados de workstation)
- Central sí rechaza: `backend/application/sync/device_provisioning.py:168-170`, `backend/api/routers/sync.py:115-120`
- Pruebas: `tests/integration/bootstrap/test_application_context_builder.py` (sin casos de dispositivo).

## Impacto
Equipos dados de baja o robados siguen operando en local.

## Objetivo
- Login operativo rechazado (con motivo) si la terminal no está ACTIVA o su tipo no admite el módulo.
- Prueba de integración por estado.

## Alcance
- **Incluye:** Builder de contexto y política de terminal.
- **No incluye:** Obtener el estado desde el central (TERM-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
