# SDLC-WA-005 — Microservicio WhatsApp importa el paquete core.* eliminado y la bandeja del POS nunca recibe avisos

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Varios módulos importan `core.*`, que ya no existe: la aceptación/rechazo de ajuste de peso por el cliente está muerta (error tragado por el router), la demanda programada y las notificaciones de escritorio se omiten con `except: pass`, y hay `int(sucursal_id)`/`int(venta_id)` sobre UUID. Las notificaciones a `notification_inbox` insertan sin `id` (columna TEXT NOT NULL) y el error se registra en debug; el DDL de respaldo usa INTEGER AUTOINCREMENT.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/erp/adjustment_approval.py:15-17`; `whatsapp_service/router/message_router.py:217-234`
- `whatsapp_service/erp/bridge.py:506,570-587`; `whatsapp_service/application/confirm_order_use_case.py:114`
- `whatsapp_service/erp/pos_notifier.py:228-231,268-285`; `migrations/m000_base_schema.py:2741-2743`
- Línea base: `tests/architecture/test_whatsapp_runtime_imports.py::test_channel_uses_qualified_imports` FALLA listando esos mismos imports `core.*` *(verificado directamente en el triage)*

## Impacto
Flujos de WhatsApp que el usuario cree activos están muertos sin aviso.

## Objetivo
- Ningún import a `core.*` en el microservicio (prueba de arquitectura).
- Las notificaciones al POS llegan a la bandeja con id UUIDv7.
- Errores de estos flujos visibles, no tragados.

## Alcance
- **Incluye:** Imports, notificador, ajuste de peso.
- **No incluye:** Webhook/cutover.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
WA-22.

## Preguntas abiertas
- Ninguna por ahora.
