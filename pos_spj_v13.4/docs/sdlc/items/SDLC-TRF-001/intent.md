# SDLC-TRF-001 — Recepción de transferencias no captura peso, piezas, lote ni temperatura

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

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

## Impacto
No se puede recibir canal entera ni producto de peso variable entre sucursales; recepciones parciales por peso cero.

## Objetivo
- El diálogo exige neto observado, piezas, lote, caducidad y temperatura según el perfil del producto.
- Perfiles, cadena de frío y calidad inyectados en la composición.
- Prueba UI → comando → ledger para recepción completa y parcial.

## Alcance
- **Incluye:** Diálogo, DTO del ciclo, composición de transferencias.
- **No incluye:** Eventos/diferencias (TRF-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría integral 2026-10-26; `docs/refactor/TRF-23_transfers_final_validation.md`; memoria LOG-INT.

## Preguntas abiertas
- La auditoría lo clasificó P0; aquí P1 (flujo roto, sin pérdida de dinero). ¿De acuerdo?
