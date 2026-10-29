# SDLC-ARQ-INST-003 — Llave maestra de secretos en claro sin pywin32; DPAPI por usuario con datos de alcance máquina

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §13 · §14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R13.3 Sin secretos en texto plano, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** SDLC-INST-003

## Problema
Si falta pywin32, `master.key` se guarda en claro, y en modo máquina la carpeta de datos es modificable por todos los usuarios (SDLC-INST-003). DPAPI se usa con flags=0 (por usuario de Windows) igual que Credential Manager, así que con datos de alcance máquina y varios usuarios de Windows uno no puede descifrar los secretos del otro.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/secrets/encrypted_local_secret_store.py:155-165,169-182`
- `backend/security/secrets/default_secret_store.py:18-33`
- Pruebas: `tests/unit/security/test_windows_credential_manager_secret_store.py` (no cubre la ruta sin pywin32).

## Impacto
Credenciales de integraciones (pagos, WhatsApp, central) expuestas en disco, o inaccesibles al cambiar de usuario de Windows.

## Objetivo
- Sin protección del SO disponible, el almacén falla cerrado (nunca escribe la llave en claro).
- Ámbito de protección coherente con el modo de instalación (máquina vs usuario).
- Pruebas por plataforma con dobles.

## Alcance
- **Incluye:** Almacén de secretos.
- **No incluye:** Permisos de carpeta (SDLC-INST-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-INST-003.

## Preguntas abiertas
- ¿Las PCs de sucursal tienen varios usuarios de Windows? (misma pregunta que SDLC-INST-003)
