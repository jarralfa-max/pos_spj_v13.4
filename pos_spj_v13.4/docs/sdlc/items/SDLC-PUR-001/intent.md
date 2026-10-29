# SDLC-PUR-001 — Recepción de compra rechazada por Inventario se descarta, pero la CxP sí se crea

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Cuando el posteo a inventario devuelve `PERMISSION_DENIED` o el payload es inválido (p. ej. sin actor), el handler sólo registra y retorna normal; el outbox de Compras marca el evento como despachado. Mientras tanto el puente de CxP crea la cuenta por pagar y el asiento Dr Inventario: los libros muestran inventario que nunca entró.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/inventory/purchase_receipt_handler.py:64-67,89-92`
- `backend/application/event_handlers/inventory/supplier_return_handler.py:53-56,89-91`
- `backend/application/event_handlers/inventory/goods_receipt_reversed_handler.py:44-47,62-64`
- `backend/application/procurement/integrations/procurement_outbox_dispatcher.py:58-62`

## Impacto
Descuadre inventario físico vs mayor; compras pagadas sin stock.

## Objetivo
- Un rechazo de Inventario deja el evento pendiente/fallido visible, no despachado.
- CxP e inventario quedan consistentes (ambos o ninguno, o compensación explícita).
- Prueba de regresión del rechazo.

## Alcance
- **Incluye:** Handlers de inventario de Compras y su despachador.
- **No incluye:** Convención de ubicaciones (INV-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria Compras (PUR-AUD d9f2bca: eventos de compensación sin consumidor).

## Preguntas abiertas
- Ninguna por ahora.
