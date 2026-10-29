# SDLC-SET-003 — Secciones de Configuración que guardan datos que nada lee

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Apariencia (temas, tokens, densidad: el runtime sólo usa QSettings), Offline (políticas de caducidad: `is_expired` sin llamador), Notificaciones (cuentas, plantillas, rutas: `backend/application/notifications/` sólo tiene `user_inbox_service.py`) e Integraciones (webhooks). El administrador configura y nada cambia.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/configuracion/pages/apariencia_page.py:1-11`; `frontend/desktop/themes/theme_manager.py:66-80`
- `backend/domain/offline/policies/cache_expiration_evaluation_policy.py:14`

## Impacto
Configuración engañosa.

## Objetivo
- Cada sección se conecta al runtime o se oculta con decisión registrada.

## Alcance
- **Incluye:** Decisión por sección.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
work_queue CONFIGURACION-06 (IN_PROGRESS) a CONFIGURACION-17: referenciar.

## Preguntas abiertas
- ¿Qué secciones conectar y cuáles ocultar?
