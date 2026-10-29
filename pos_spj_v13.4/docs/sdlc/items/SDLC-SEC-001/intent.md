# SDLC-SEC-001 — Contraseñas de usuario se hashean en la UI y saltan la política de contraseñas

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El presenter de Configuración hashea con bcrypt y envía un `password_hash` ya hecho; el caso de uso lo guarda sin validar, así que `PasswordPolicy` nunca corre y cualquier cadena se acepta como hash. Además el alta de dueño y la recuperación usan bcrypt mientras el login trata Argon2id como primario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/configuracion/configuracion_presenter.py:1007-1009,1038-1040`
- `backend/application/use_cases/save_user_use_case.py:36`; `backend/application/configuracion/settings_services.py:56-66`
- `frontend/desktop/shell/desktop_shell_authentication_composition.py:92,104,111`

## Impacto
Seguridad: contraseñas débiles aceptadas; hashing fuera del backend.

## Objetivo
- La UI envía la contraseña en claro a un caso de uso que aplica `PasswordPolicy` y hashea con el algoritmo primario.
- Un único hasher para alta, cambio, recuperación y login; hashes bcrypt existentes siguen validando y se re-hashean al iniciar sesión.

## Alcance
- **Incluye:** Presenter, caso de uso de usuarios, composición de autenticación.
- **No incluye:** Bloqueo/lockout (ya existe).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria PERM-AUD 968e0bc, SET-26.

## Preguntas abiertas
- Ninguna por ahora.
