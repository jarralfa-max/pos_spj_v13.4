# SDLC-WA-029 — Aprobación del ajuste de peso por el cliente escribe tablas legacy de delivery y no usa el caso de uso de Orders

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §35, §36 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-005, SDLC-WA-003

## Problema
Cuando el cliente responde a un ajuste, el microservicio actualiza directamente `delivery_items` y `delivery_orders` (legacy) y recalcula el total; identifica el ajuste pendiente por sufijo de teléfono y no lleva `operation_id`. Orders/Delivery ya tiene `AcceptWeightAdjustmentUseCase` y `RejectWeightAdjustmentUseCase` sobre `customer_orders`, pero exigen el permiso de empleado `CUSTOMER_APPROVAL_OVERRIDE` y no hay comando del lado cliente. El aviso del ERP le dice al cliente "contacta a la sucursal", mientras el canal espera "acepto".

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/adjustment_approval.py:15-17,46,58-70,80-121`
- `backend/application/orders_delivery/use_cases/catch_weight_use_cases.py:55,119,125,146`
- `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py:52-61`
- Prueba: `whatsapp_service/tests/test_adjustment_approval_phase7.py` (no se recolecta; DDL INTEGER propio)

## Impacto
Dinero: el total ajustado de un pedido se decide fuera de Orders, sin rastro de quién aprobó.

## Objetivo
- La respuesta del cliente se convierte en un comando idempotente a Orders, que actualiza el pedido canónico.
- La aprobación queda persistida en Orders, no solo en la conversación.

## Alcance
- **Incluye:** Comando de decisión del cliente y su llamada desde el canal.
- **No incluye:** Imports rotos y negación mal leída (SDLC-WA-005).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
ORD-0..30 (catch weight); SDLC-WA-005.

## Preguntas abiertas
- ¿La aceptación del cliente por WhatsApp basta como aprobación, o un ajuste por encima de cierto monto requiere además a un empleado con `CUSTOMER_APPROVAL_OVERRIDE`?
