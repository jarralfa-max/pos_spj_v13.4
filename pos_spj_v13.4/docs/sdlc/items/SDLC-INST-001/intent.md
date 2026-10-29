# SDLC-INST-001 — El actualizador confía en update_job.json escribible por cualquier usuario local

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`update_job.json` vive bajo la raíz de datos, que el instalador deja `users-modify`. El actualizador (elevado) verifica el instalador sólo contra tamaño/SHA escritos en ese mismo archivo, no vuelve a verificar el manifiesto firmado, y su verificación Authenticode acepta cualquier instalador firmado válido (sin `expected_subject`); en builds sin firma se omite. Un usuario local puede sustituir el instalador y ejecutarlo elevado.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/shared/app_paths.py:230-231` — ubicación del job
- `installer/windows/spj_setup.iss:119` — carpeta de datos `users-modify`
- `backend/application/software_updates/update_transaction.py:109-112` — compara contra el propio job
- `backend/infrastructure/updater/updater_main.py:98` — sin `expected_subject`
- `backend/infrastructure/updater/installer_trust.py:58-61`, `update_launcher.py:44-45` — se omite en builds sin firma

## Impacto
Escalada de privilegios local en cualquier PC con la app instalada.

## Objetivo
- El proceso elevado sólo ejecuta un instalador cuyo hash proviene del manifiesto firmado verificado en el propio proceso elevado.
- Authenticode exige el sujeto/huella esperados del publicador.
- Builds sin firma no pueden ejecutar actualizaciones elevadas fuera de modo desarrollo explícito.

## Alcance
- **Incluye:** Updater, launcher, ubicación/ACL del job.
- **No incluye:** Provisión de la llave de release (SDLC-INST-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria INST-0 (2026-10-14/16): instalador + updater firmado, CI Windows verde.

## Preguntas abiertas
- ¿Nombre/huella del certificado de firma de código que se usará?

## Ampliación (`/sdlc-plan arquitectura`, 2026-10-29)
Además, `AuthenticodeVerifier` se construye sin `expected_subject` (`backend/infrastructure/updater/updater_main.py:98`, *verificado directamente*; `backend/infrastructure/updater/installer_trust.py:50`), así que acepta un instalador firmado por **cualquier** editor con certificado válido. Con `update_job.json` manipulable, se ejecutaría elevado cualquier exe firmado por un tercero. Va en este ítem porque comparte superficie de ataque y archivos. Requisito: `requisitos-arquitectura.md` §13 (verificar firma e integridad).
