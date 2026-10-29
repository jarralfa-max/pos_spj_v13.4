# SDLC-SALES-007 — POS reporta cualquier OperationalError como 'no hay turno abierto'; folio de CxC = id de venta

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`sales_pos/composition.py` muestra cualquier `sqlite3.OperationalError` como 'sin turno abierto', ocultando errores reales de BD. Además el pago a crédito registra la CxC con `folio=sale.sale_number or sale.id` antes de que el checkout asigne folio: el documento queda con el UUID.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/composition.py:134-138`
- `backend/application/sales/use_cases/payment_use_cases.py:121`; `checkout_use_cases.py:134-139`

## Impacto
Diagnóstico confuso; CxC con folio ilegible.

## Objetivo
- Errores de BD visibles como tales; CxC con folio de venta.

## Alcance
- **Incluye:** —
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
