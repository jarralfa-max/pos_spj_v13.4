# SDLC-PROC-001 — Lo recibido no llega al despiece: falta orquestación recepción → transformación

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-INV-003, SDLC-TRF-001

## Problema
Producción sólo consulta almacenes `PRODUCTION` con saldos `AVAILABLE`; una canal recibida por transferencia o compra queda en otro almacén e invisible. No existe coordinación durable entre la recepción confirmada y la petición de transformación; `ExecuteDirectTransformationUseCase` comitea por etapas sin transacción con la recepción.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/meat_processing/queries/direct_transformation_query_service.py` (`lots`)
- `backend/application/meat_processing/use_cases/direct_transformation_use_cases.py`
- Auditoría 2026-10-26 §3 P0 #2 y #3

## Impacto
El flujo principal de SPJ (planta → POS → despiece → venta de cortes) no corre de punta a punta.

## Objetivo
- Lote recibido y liberado en almacén elegible aparece para transformar (o se mueve de forma autorizada y trazable).
- Petición de transformación idempotente con estados visibles (RECIBIDO, PENDIENTE_DE_LOTE, ESPERA_CALIDAD, …).
- Reiniciar no duplica stock.

## Alcance
- **Incluye:** Política de transformación y coordinador.
- **No incluye:** Conciliación de cortes estimados (P1 de la auditoría, futuro ítem).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría integral 2026-10-26 §4-7; memoria PROC-AUD 32cfbf.

## Preguntas abiertas
- ¿Política por producto/sucursal/almacén de qué dispara la transformación?
