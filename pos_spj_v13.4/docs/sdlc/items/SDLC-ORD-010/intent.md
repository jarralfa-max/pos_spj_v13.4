# SDLC-ORD-010 — Restos del legacy de Delivery: 31 archivos de prueba importan paquetes borrados y no se pueden recolectar

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/refactor/ORD-30_validacion_final.md` → "Pendiente" §7 (ORD-29, eliminación del legacy) y `docs/audits/DELIVERY_REFACTOR_AUDIT.md` (plan §13 y §15). Re-verificado (`/sdlc-plan` Modo B, 2026-10-31).
- **Estado:** borrador
- **Depende de:** —

## Problema
El legacy de Delivery que ORD-29 dejó pospuesto ya se borró (`a35b8bab`, 2026-09-10): `modulos/delivery.py`, `core/delivery/`, `core/services/delivery_service.py`, `repositories/delivery_repository.py`, `integrations/delivery_pwa/`, `delivery/ticket_delivery.py` y `delivery/asignacion_repartidor.py`. Con eso quedan cerrados los pendientes de la auditoría Fase 0: SQL directo en la UI de asignación, cobro, tickets y cortes; el `LegacyDeliveryEventBridge`; el `payload["db"]`; el JSON `historial_cambios`; y las migraciones defensivas del migrador. Las pruebas de ese legacy, en cambio, siguen en `tests/`: 31 archivos fallan al recolectarse porque importan esos paquetes. Ningún job de CI los corre, así que nadie lo nota. Además, `tests/test_phase17_uuid_schema_and_flow.py` importa `core.services.reservation_service` dentro de cinco funciones.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- Existencia: los 18 caminos legacy de la auditoría y de ORD-30 (`modulos/`, `core/`, `main_window.py`, `menu_lateral.py`, `services/bot_pedidos.py`, etc.) dan `GONE`. Borrado en `a35b8bab` "Commit despues de refacturacion ERP" (2026-09-10).
- Grep de `LegacyDeliveryEventBridge|historial_cambios|pedido_delivery_creado` en `backend/`, `frontend/` y `whatsapp_service/`: cero resultados. Grep de `payload["db"]`/`payload.get("db")` en `backend/`: cero.
- `python -m pytest --collect-only -q tests/test_delivery_*.py tests/test_driver_service.py tests/test_order_totals_phase8.py`: `31 errors during collection`. Ejemplos: `tests/test_delivery_state_machine.py`, `test_delivery_outbox.py`, `test_delivery_phase12_required.py`, `test_delivery_board_query_route.py:17` (`from core.delivery.application.query_service import ...`), `test_driver_service.py`, `test_order_totals_phase8.py`.
- `tests/test_phase17_uuid_schema_and_flow.py:177,184,191,200,331`: `from core.services.reservation_service import ...` dentro de funciones. El archivo se recolecta, pero esas pruebas fallan al ejecutarse (**no ejecutado**, solo leído).
- `tests/test_rrhh_phase8_cleanup.py` también falla al recolectarse. Es de RRHH; se reporta y no entra en este ítem.
- Grep de `tests/test_delivery|tests/test_driver|tests/test_order_totals` en los workflows: cero. CI no los corre.
- El código de producción sin llamadores que sobrevive (`settle_delivery_driver_use_case.py`, `delivery_query_service.py`, `driver_query_service.py`, `driver_settlement_query_service.py`) ya está en **SDLC-CORE-005**, que se amplió en esta corrida. No se duplica aquí.

## Impacto
Es deuda. Hay 31 archivos de prueba que no prueban nada y aparentan cobertura del dominio de entregas, y ensucian cualquier `pytest tests/` sin lista curada (memoria: "bare `pytest tests/` carries pre-existing unrelated failures").

## Objetivo
- Ningún archivo de `tests/` importa `core.delivery`, `core.services.(delivery|order_total|reservation|driver)*`, `repositories.(delivery|driver)_repository`, `modulos.delivery`, `integrations.delivery_pwa` ni `delivery.*`.
- Antes de borrar cada archivo se revisa si cubre una regla de negocio que el estrato canónico no prueba (máquina de estados, tolerancia de peso, deduplicación, totales). Si es así, se porta a `tests/*/test_orders_delivery_*` y la lista queda en el plan.
- `python -m pytest --collect-only tests/` no reporta errores de Delivery.

## Alcance
- **Incluye:** Las 31 pruebas de Delivery y las cinco funciones de `test_phase17_uuid_schema_and_flow.py`, con portado de reglas no cubiertas.
- **No incluye:** Código de producción muerto (SDLC-CORE-005), restos de Activos (SDLC-ASSET-003) ni `test_rrhh_phase8_cleanup.py`.

## Restricciones
CLAUDE.md regla 1 (no perder lógica de negocio: revisar cobertura antes de borrar); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO y rutas dentro de `pos_spj_v13.4/`; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
ORD-29 (pospuesto y luego superado por `a35b8bab`); SDLC-CORE-005; SDLC-ASSET-003 (mismo patrón en Activos); memoria `env_nested_git_repo_pos_spj` (fallas preexistentes en `tests/` sin curar).

## Preguntas abiertas
- Ninguna por ahora.
