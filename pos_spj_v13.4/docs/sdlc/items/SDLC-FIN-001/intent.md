# SDLC-FIN-001 — 16 handlers de Finanzas muertos duplican las reglas del puente de Lealtad

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Handlers de cupones, tarjetas de regalo, vales, valor almacenado, puntos y compra recibida no tienen importadores en producción; las rutas reales son el puente `loyalty/integrations/finance_posting.py` y los puentes de Compras. Dos implementaciones de las mismas reglas contables, una abandonada en silencio.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/finance/{coupon_*,gift_card_*,voucher_*,stored_value_adjusted,loyalty_points_*,loyalty_reward_granted,loyalty_transaction_reversed,purchase_received}_handler.py`
- `backend/application/loyalty/integrations/finance_posting.py:1-40`

## Impacto
Riesgo de que alguien cablee la versión vieja y asiente doble.

## Objetivo
- Una sola implementación por regla contable; las muertas se eliminan con sus pruebas migradas.

## Alcance
- **Incluye:** Eliminación de handlers muertos.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
LOY-29, FIN-AUD.

## Preguntas abiertas
- Ninguna por ahora.
