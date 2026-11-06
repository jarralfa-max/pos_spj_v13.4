# SDLC-PROC-001 — Lo recibido no llega al despiece: falta orquestación recepción → transformación

- **Prioridad:** P0 (subida de P1 el 2026-10-31 por `inputs/correcciones.md` C-03)
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`); ampliado con `inputs/correcciones.md` C-03 (oleada 3: se diseña después de los ítems de arquitectura de idempotencia/outbox)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-TRF-001, SDLC-TRF-003, SDLC-PROC-002, SDLC-INV-003, SDLC-CORE-002, SDLC-ARQ-IDEM-005

## Problema
Producción sólo consulta almacenes `PRODUCTION` con saldos `AVAILABLE`; una canal recibida por transferencia o compra queda en otro almacén e invisible (esa parte pasa a SDLC-TRF-003). No existe coordinación durable entre la recepción confirmada y la petición de transformación; `ExecuteDirectTransformationUseCase` comitea por etapas sin transacción con la recepción, y la transformación es una acción separada en otra pantalla.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/meat_processing/queries/direct_transformation_query_service.py` (`lots`)
- `backend/application/meat_processing/use_cases/direct_transformation_use_cases.py`
- Auditoría 2026-10-26 §3 P0 #2 y #3

**Re-verificado el 2026-10-31 sobre `4639fed2` (correcciones C-03):**
- `backend/application/meat_processing/use_cases/direct_transformation_use_cases.py:49` (`ExecuteDirectTransformationUseCase`) — `connection.commit()` en `:112`, `:124`, `:143` y `:189` entre registro, creación, aprobación/preparación/liberación/ejecución; repetir el mismo `operation_id` continúa donde quedó (`:27`, `:78-82`), pero no hay vínculo con la línea de recepción ni con el lote recibido.
- `frontend/desktop/modules/meat_processing/pages/direct_transformation_page.py:23` — `DirectTransformationPage` es una página aparte; `backend/infrastructure/desktop/meat_processing_factory.py:207,233-235` la compone sin relación con Compras/Transferencias.
- No existe ninguna petición de transformación ni política por destino: búsqueda de `OFFER_AFTER_RECEIPT`, `AUTO_ESTIMATE`, `PENDIENTE_DE_LOTE`, `transformation_request` en `backend/` sin resultados en los módulos de producción, compras ni transferencias (los `receipt_line_id` existentes son de Compras: `backend/domain/procurement/entities.py`).

## Impacto
El flujo principal de SPJ (planta → POS → despiece → venta de cortes) no corre de punta a punta.

## Objetivo
- Petición de transformación única por `receipt_line_id + inventory_lot_id + yield_version_id + logical_attempt`, con estados visibles `RECIBIDO`, `PENDIENTE_DE_LOTE`, `ESPERA_CALIDAD`, `PENDIENTE_DE_MOVIMIENTO`, `TRANSFORMANDO`, `COMPLETADO`, `ERROR_REINTENTABLE`.
- Reutiliza outbox, bus y composition root existentes (no un mecanismo nuevo).
- Reintentos y reinicios no duplican consumo, lotes ni costo (prueba con caída entre etapas).
- Política por destino `NEVER` / `OFFER_AFTER_RECEIPT` / `AUTO_ESTIMATE_AFTER_RECEIPT` con alcance producto + sucursal + almacén + origen.

## Alcance
- **Incluye:** Política de transformación y coordinador.
- **No incluye:** Conciliación de cortes estimados (SDLC-PROC-004); almacén destino y movimiento interno (SDLC-TRF-003); unidades de la disponibilidad (SDLC-PROC-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria. La llave determinista de la petición depende de la respuesta a SDLC-CORE-002 (ids derivados vs UUIDv7 persistido).

## Trabajo previo relacionado
Auditoría integral 2026-10-26 §4-7; memoria PROC-AUD 32cfbf; `inputs/correcciones.md` C-03; SDLC-ARQ-IDEM-005 (vocabulario común de estados de operación); SDLC-CORE-002 (operation_id derivados); `arquitectura/matriz-brechas.md` (idempotencia, sincronización, autoridad por entidad).

## Preguntas abiertas
- ¿Política por producto/sucursal/almacén de qué dispara la transformación? Concretamente (C-03): ¿qué productos y sucursales usan `NEVER`, `OFFER_AFTER_RECEIPT` o `AUTO_ESTIMATE_AFTER_RECEIPT`? · bloquea `/sdlc-design SDLC-PROC-001`
- ~~La auditoría lo clasificó P0; el triage P1.~~ Respondida 2026-10-31 por `inputs/correcciones.md` C-03: **P0**.
