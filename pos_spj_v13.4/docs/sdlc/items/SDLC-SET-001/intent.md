# SDLC-SET-001 — Anclar la sucursal de la instalación no cambia la sesión en curso

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Tras anclar la sucursal con éxito, la página llama `main_win.aplicar_sucursal_activa(...)`, método que no existe, dentro de `hasattr` + `except: pass`. `ApplicationWindow.update_context` no tiene llamador y `ApplicationContextService.change_branch` nunca se instancia fuera de su archivo. La sesión conserva el `branch_id` anterior hasta reiniciar y el mensaje de éxito no lo avisa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/configuracion/pages/empresa_page.py:408-412`
- `frontend/desktop/shell/application_shell/application_window.py:153`
- `frontend/desktop/modules/configuracion/configuracion_presenter.py:1193`

## Impacto
Operaciones registradas en la sucursal equivocada tras re-anclar.

## Objetivo
- Anclar actualiza el contexto de sesión (o exige reinicio de forma explícita y bloqueante).
- Sin `hasattr`/`except: pass` en el camino.

## Alcance
- **Incluye:** Página Empresa y servicio de contexto.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria SET (install-branch pin), ORG-AUD (sitio de sesión = pin).

## Preguntas abiertas
- ¿Cambio en caliente o reinicio obligatorio?
