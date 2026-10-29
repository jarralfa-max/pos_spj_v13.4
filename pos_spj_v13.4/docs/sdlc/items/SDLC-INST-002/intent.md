# SDLC-INST-002 — Llavero de releases vacío: ninguna actualización puede aplicarse

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-INST-001

## Problema
`EMBEDDED_RELEASE_KEYS` está vacío, así que `TrustedKeyring.verify` rechaza toda actualización en línea y fuera de línea. Falla de forma segura, pero la función de actualización firmada no funciona.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/updater/trusted_keys.py:30-33`
- `backend/application/software_updates/update_manifest.py:155-158`

## Impacto
No hay ruta de actualización para sucursales instaladas.

## Objetivo
- La llave pública de release está embebida en el build de release (no en el repo de desarrollo si se decide así).
- Una prueba de CI firma un manifiesto de prueba y verifica que el build lo acepta.

## Alcance
- **Incluye:** Provisión de llave y prueba.
- **No incluye:** Endurecimiento del job (INST-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria INST-0.

## Preguntas abiertas
- ¿Dónde se genera y custodia la llave privada de release? (el humano la crea; Claude no la ve)
