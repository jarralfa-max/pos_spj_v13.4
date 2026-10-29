# SDLC-HR-002 — Asiento de nómina sin reintento periódico; la UI dice 'pagada' aunque Finanzas falle

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El asiento PAYROLL_PAID se entrega desde `hr_outbox` sólo justo después de pagar y al arrancar; no hay ciclo periódico (Caja, Lealtad y Finanzas sí). El presenter ignora el conteo `failed` de `dispatch_hr_outbox` y muestra 'Nómina pagada'.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/hr/hr_presenter.py:505-514`
- `backend/bootstrap/wiring/event_wiring.py:91-96`
- `frontend/desktop/shell/desktop_shell_window_composition.py:221-271`

## Impacto
Nómina pagada sin asiento hasta el siguiente reinicio, sin aviso.

## Objetivo
- `hr_outbox` se drena en el ciclo periódico.
- La UI informa cuando el asiento quedó pendiente.

## Alcance
- **Incluye:** Tarea periódica y presenter.
- **No incluye:** Cuentas de nómina (HR-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
HR-AUD.

## Preguntas abiertas
- Ninguna por ahora.
