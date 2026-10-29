# SDLC-SALES-002 — Totales de venta nunca se redondean a centavos

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`quantity*unit_price` no se redondea, `rounding_adjustment` nunca se calcula (siempre 0) y las lecturas de báscula en LB generan muchos decimales. Pagos con tarjeta/transferencia/crédito no pueden exceder el saldo, así que tendrían que igualar importes como 111.0265; Finanzas redondea cada campo por separado y valida `bruto-descuento==neto`, lo que puede fallar cerca de medio centavo y atascar el evento.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/sales/services/sale_totals_service.py:32-41`
- `backend/domain/sales/entities.py:111,264-266`
- `backend/application/sales/scale_reading_service.py:96-101` (factor 0.45359237)
- `backend/domain/sales/policies/payment_policy.py:46-50`
- `backend/application/event_handlers/finance/sale_completed_handler.py:68-84`

## Impacto
Cajeros: cobros con tarjeta imposibles o con centavos fantasma; Finanzas: ventas que no llegan al mayor.

## Objetivo
- El total de venta y cada importe cobrable se expresan en centavos con una regla de redondeo única y documentada.
- El evento de venta cuadra por construcción con lo que Finanzas valida.
- Pruebas con pesos de báscula (KG y LB) y descuentos en el borde de medio centavo.

## Alcance
- **Incluye:** Dominio de ventas, política de pagos, handler de Finanzas.
- **No incluye:** Redondeo de efectivo a la moneda física (si aplica, decisión aparte).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria SALES-23 (productos KG), SALES-AUD.

## Preguntas abiertas
- ¿Regla de redondeo: por línea o sobre el total? ¿HALF_UP o bancario?
