# SDLC-SEC-003 — Alcance de seguridad abierto: central acepta cualquier actor y algunos checkers omiten sucursal

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`StationScopedAuthorizer.allows` devuelve True y es el default: el central nunca valida el permiso del usuario, una estación comprometida puede empujar cualquier tipo de evento de su sucursal (documentado, abierto). Además, las políticas de Compras y RRHH simplemente retornan si el checker no implementa `can_access_branch` (fail-open).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sync/central_ingestion.py:88-94,109`
- `backend/application/procurement/authorization.py:41-43`
- `backend/domain/hr/policies/authorization_policy.py:112-114`
- Checker productivo de Compras sí implementa (`procurement/session_authorization.py:29`); el de RRHH **no verificado**

## Impacto
Defensa en profundidad débil.

## Objetivo
- Ausencia de capacidad = denegar.
- El central valida tipo de evento contra capacidades de la estación/usuario.

## Alcance
- **Incluye:** Autorizadores mencionados.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
PERM-AUD (`unwired()` fail-closed), ORG-AUD fase 2.

## Preguntas abiertas
- Ninguna por ahora.
