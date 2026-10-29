# SDLC-TRF-002 — Ciclo de transferencia termina en la recepción: faltantes desaparecen sin merma ni asiento

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-TRF-001, SDLC-LOSS-001

## Problema
Despacho y recepción se construyen sin `event_sink`, así que no se emite ningún evento de transferencia. Diferencias, devoluciones, recepción ciega, empaque y sugerencias no se componen (las devoluciones lanzan `TransferReturnNotWired`); los handlers de caso de merma e impacto económico nunca se suscriben. `TRANSFER_DISPATCH` es una disminución simple y el estado `IN_TRANSIT` no se usa: lo que nunca llega simplemente sale del ledger.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/transfers/composition.py:148-164`
- `backend/infrastructure/integrations/transfers_inventory_gateway.py:250-264`
- `backend/application/transfers/integrations/outbound_handlers.py:16,34`; `backend/infrastructure/desktop/losses_factory.py:192`
- `backend/domain/inventory/enums.py:175`

## Impacto
Mercancía perdida en tránsito sin rastro ni responsable.

## Objetivo
- Lo despachado queda en tránsito hasta recibirse; la diferencia genera caso de merma y asiento.
- Devolución de transferencia funcional.
- Eventos de transferencia emitidos y consumidos.

## Alcance
- **Incluye:** Composición de transferencias, handlers hacia Mermas/Finanzas.
- **No incluye:** Captura de recepción (TRF-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
TRF-23; memoria alcance por sucursal.

## Preguntas abiertas
- Ninguna por ahora.
