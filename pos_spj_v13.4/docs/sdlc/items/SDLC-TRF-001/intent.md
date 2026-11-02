# SDLC-TRF-001 — Recepción de transferencias no captura peso, piezas, lote ni temperatura

- **Prioridad:** P0 (subida de P1 el 2026-10-31 por `inputs/correcciones.md` C-01)
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`); ampliado con `inputs/correcciones.md` C-01 (oleada 1)
- **Estado:** borrador
- **Depende de:** SDLC-CORE-012

## Problema
El diálogo de recepción recoge cantidad y aceptación; `cycle_service.receive` construye `ReceiveTransferLineCommand` sólo con cantidad y aceptado. Las líneas de la UI siempre llevan `lot_required=False`, por lo que los controles de lote, cadena de frío y calidad nunca aplican; si una línea viniera marcada, la recepción lanzaría porque perfiles de producto, cadena de frío y calidad no se inyectan. Un producto `catch_weight` no puede recibirse correctamente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/transfers/cycle_service.py:124-131` *(verificado directamente en el triage)*
- `backend/application/transfers/commands/transfer_request_commands.py:20`
- `backend/application/transfers/use_cases/transfer_receipt_use_cases.py:139-163`
- `backend/application/transfers/integrations/product_profiles.py` — nunca inyectado
- `frontend/desktop/modules/transfers/dialogs/cycle_dialogs.py` (`ReceiveTransferDialog`); `workflow_dialogs.py:85-92` (alias)
- Auditoría 2026-10-26 §3 P0 #1; sin cambios funcionales desde entonces *(verificado directamente en el triage)*

**Re-verificado el 2026-10-31 sobre `4639fed2` (correcciones C-01):**
- `backend/application/transfers/cycle_service.py:124-131` — sigue armando `ReceiveTransferLineCommand(l["line_id"], Decimal(str(l["quantity"])), accepted=...)`: `observed_weight` y `observed_pieces` quedan en su valor por omisión `Decimal("0")`, `lot_id`/`temperature`/`expires_on` en `None` (`backend/application/transfers/commands/transfer_request_commands.py:165-173`).
- `cycle_service.py:127` — `operation_id=new_uuid()` en cada llamada: reintentar la misma recepción desde la pantalla no es idempotente (mismo patrón que SDLC-ARQ-IDEM-001 en el cobro).
- `frontend/desktop/modules/transfers/dialogs/cycle_dialogs.py:91-107` — el diálogo solo tiene `DecimalInput` de cantidad y casilla «aceptado» por línea.
- `backend/application/transfers/use_cases/transfer_receipt_use_cases.py:141-148` — si la línea exige perfil y no hay `product_profiles`/`cold_chain_policy`, rechaza; `:152-155` exige lote y peso/piezas > 0 para `catch_weight`.
- `backend/application/transfers/composition.py:162-164` — `ConfirmTransferReceiptUseCase(...)` se construye sin `product_profiles`, `cold_chain_policy` ni `quality_gateway`.
- Pruebas actuales (pasan): `tests/unit/test_transfers_receipt_use_cases.py` (caso de uso) y `tests/integration/transfers/test_transfer_full_cycle_32cfbf.py`; ninguna cubre el camino pantalla → `cycle_service.receive` con producto de peso variable.

## Impacto
No se puede recibir canal entera ni producto de peso variable entre sucursales; recepciones parciales por peso cero.

## Objetivo
- El diálogo exige neto observado, piezas, lote, caducidad y temperatura según el perfil del producto.
- Perfiles, cadena de frío y calidad inyectados en la composición.
- Recepción completa y parcial correctas; lo rechazado o en cuarentena no queda disponible para venta.
- Reintentar la misma recepción no duplica la entrada (operation_id estable por intento lógico).
- Prueba UI → comando → ledger para recepción completa y parcial, incluida una canal entera de 100 kg de planta a POS.

## Alcance
- **Incluye:** Diálogo, DTO del ciclo, composición de transferencias, idempotencia del reintento desde la pantalla.
- **No incluye:** Eventos/diferencias (TRF-002); almacén destino y movimiento a producción (SDLC-TRF-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría integral 2026-10-26; `docs/refactor/TRF-23_transfers_final_validation.md`; memoria LOG-INT; `inputs/correcciones.md` C-01; SDLC-ARQ-IDEM-001 (mismo defecto de operation_id por clic, en cobro).

## Preguntas abiertas
- ~~La auditoría lo clasificó P0; aquí P1. ¿De acuerdo?~~ Respondida 2026-10-31 por `inputs/correcciones.md` C-01: **P0**.
- ¿Qué productos usan perfil `catch_weight` / lote obligatorio hoy en la BD real (se medirá sobre copia)? · no bloquea Design; dimensiona la migración de datos, si hace falta.
