# SDLC-ARQ-PERM-001 — Configuración autoriza sólo en el presentador: casos de uso de escritura sin política en backend

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.6 Autorización en backend en cada operación, estado `parcial`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El documento exige verificar la autorización en backend en cada operación. La mayoría de los casos de uso de Configuración se construyen sólo con `connection` y se autorizan únicamente en `ConfiguracionPresenter._authorize`: feature flags, temas, dispositivos, integraciones **y sus credenciales**, notificaciones, rutas de impresión, plantillas. `SaveCompanyProfile`, `SaveSystemSetting`, SMTP y proveedor de pagos no tienen verificación. El actor sale del comando (`command.user_name`).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/configuracion/configuracion_routes.py:230-300`
- `frontend/desktop/modules/configuracion/configuracion_presenter.py:322,701,727`
- `backend/application/use_cases/save_user_use_case.py:24`
- `backend/application/use_cases/set_installation_branch_use_case.py:22-28`
- Pruebas: `tests/unit/configuracion/test_configuracion_presenter_authorization.py` (presentador).

## Impacto
Cualquier llamador que no pase por el presentador (API futura, script, otro módulo, WhatsApp) puede cambiar credenciales de integraciones y configuración del sistema sin autorización.

## Objetivo
- Cada caso de uso de escritura de Configuración recibe una política y la verifica con el actor de la sesión, no del comando.
- Sin política cableada falla cerrado (patrón `unwired_policy`).
- Guardia de arquitectura: ningún caso de uso de Configuración se construye sin autorizador.
- Pruebas de backend por caso de uso.

## Alcance
- **Incluye:** Casos de uso de Configuración listados, composición, guardia.
- **No incluye:** Re-anclaje de sucursal (TERM-002) más allá de su autorización; contraseñas (SDLC-SEC-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Pipeline CONFIGURACION en `work_queue.json` (`CONFIGURACION-06-DOMAIN_RULES` IN_PROGRESS): referenciar, no duplicar; este ítem cubre sólo la autorización. SDLC-SEC-001.

## Preguntas abiertas
- ¿Este ítem corre dentro del pipeline CONFIGURACION o como ítem SDLC independiente? (igual que SDLC-SET-002)
