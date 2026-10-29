# SDLC-SEC-005 — Endurecimiento menor: rate limit por cabecera no autenticada, nonce por proceso, respaldo de secretos en claro

- **Prioridad:** P3
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El rate limit se indexa por `X-SPJ-Station-Id` sin autenticar; `NonceCache` es por proceso (replay posible con varios workers en 300 s); sin pywin32 la llave maestra se guarda en claro y cualquier error de Credential Manager cae al archivo (pywin32 está fijado en el build de release).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/routers/sync.py:76-79`
- `backend/api/central_app.py:41`; `backend/shared/security/device_signature.py:114-134`
- `backend/security/secrets/encrypted_local_secret_store.py:159-181`; `default_secret_store.py:28-29`; `installer/windows/requirements-release.txt:68`

## Impacto
Bajo.

## Objetivo
- Rate limit tras autenticar; nonce compartido; fallback en claro sólo en modo desarrollo explícito.

## Alcance
- **Incluye:** —
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
