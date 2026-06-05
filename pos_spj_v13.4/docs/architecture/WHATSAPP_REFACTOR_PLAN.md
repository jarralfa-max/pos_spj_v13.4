# WHATSAPP_REFACTOR_PLAN.md — Plan incremental y guardrails

Actualizado: 2026-05-28

## Estado por fase

- Fase 0: mapa de seguridad documentado.
- Fase 1: legacy congelado a nivel de directriz/documentación.
- Fase 2: guardas para bloquear writes SQLite en `production`.
- Fase 3: idempotencia persistente de negocio incorporada en acciones críticas.
- Fase 4: normalización de teléfono centralizada.
- Fase 5: `PedidoFlow` más delgado con `ConfirmWhatsAppOrderUseCase`.
- Fase 6: partición inicial de `ERPBridge` en gateways (fachada compatible).
- Fase 7: reducción inicial de `MessageRouter` mediante pipeline.
- Fase 8: clasificación de eventos dominio/canal/legacy.
- Fase 9: suite de regresión reforzada en áreas críticas.
- Fase 10: documentación final consolidada (este documento + arquitectura + auditoría + catálogo de eventos).

## Reglas obligatorias (no regresión)

1. WhatsApp **no** es fuente de verdad de ventas/precios/stock/crédito.
2. WhatsApp **no** debe calcular precio final ni anticipo final como autoridad.
3. En `production`, WhatsApp **no** debe escribir negocio directo en SQLite.
4. Acciones de negocio críticas deben pasar por idempotencia persistente.
5. Legacy WA queda congelado: solo compatibilidad/fallback, sin nueva lógica de negocio.

## Estrategia operativa

### A. Seguridad de escrituras

- Verificar despliegues con `ERP_API_URL` + `ERP_API_KEY` obligatorios.
- Fallback SQLite permitido solo en `development`/`test`.
- Alertar cualquier excepción de `_handle_api_write_failure` en monitoreo.

### B. Idempotencia

- Usar `run_once` para acciones críticas nuevas.
- Definir `action_key` determinística por caso de uso.
- Persistir resultado/estado/error para respuestas seguras en reintentos.

### C. Router y flows

- Seguir extrayendo responsabilidades a middlewares/servicios pequeños.
- Mantener APIs/salidas visibles al cliente sin cambios bruscos de UX.

### D. Eventos

- Consumidores nuevos deben integrarse primero con eventos de dominio.
- Eventos legacy se mantienen por transición; planificar retiro por consumidor.

## Backlog priorizado (TODO)

1. Validar idempotencia en rutas secundarias de anticipo/delivery restantes fuera de `BusinessOrchestrator` (si aparecen nuevos entry points).
2. Reducir más `MessageRouter` (FlowRegistry explícito ya incorporado); extraer middlewares restantes y estandarizar contratos.
3. Terminar migración de lógica residual de negocio desde `ERPBridge` hacia adapters/ports/use cases.
4. Ejecutar el plan de deprecación formal de eventos legacy por consumidor (ver `docs/events/WHATSAPP_EVENT_CATALOG.md`).
5. Cerrar gaps de pruebas E2E aisladas para webhook + sender + eventos en escenarios de error extremo.

## Cómo ejecutar pruebas WhatsApp

Ejemplos de comandos:

- `pytest -q pos_spj_v13.4/tests/test_wa_bridge.py`
- `pytest -q pos_spj_v13.4/tests/test_wa_refactor.py`
- `pytest -q pos_spj_v13.4/tests/test_wa_phase5_use_case.py`
- `pytest -q pos_spj_v13.4/tests/test_wa_phase9_regression.py`

> Nota: usar mocks para servicios externos (Meta/MercadoPago/HTTP) y SQLite temporal o in-memory.
