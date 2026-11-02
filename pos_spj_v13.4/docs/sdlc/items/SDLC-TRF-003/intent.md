# SDLC-TRF-003 — La transferencia recibida cae al almacén de compras y el despiece nunca la ve

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `inputs/correcciones.md` C-02 (oleada 1); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P0 — El almacén por defecto de la transferencia no alimenta el despiece directo»
- **Estado:** borrador
- **Depende de:** SDLC-CORE-012, SDLC-TRF-001

## Problema
Si la transferencia no trae almacén destino, la recepción mete la mercancía en el almacén `PURCHASE` de la sucursal. El despiece directo solo lista lotes de almacenes `PRODUCTION`. Una canal enviada de planta a POS para despiezar queda recibida pero invisible para Producción, y no hay en la pantalla una forma autorizada de moverla al almacén de producción.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `backend/infrastructure/integrations/transfers_inventory_gateway.py:81-84` — `_destination` devuelve `destination_node.warehouse_id or resolve_branch_warehouse(conn, branch, "PURCHASE")`; usado en `:203` al aplicar la recepción.
- `backend/application/meat_processing/queries/direct_transformation_query_service.py:89-95` — `production_warehouses` = almacenes con propósito `PRODUCTION`; `:122-145` — `lots` filtra `b.warehouse_id IN (<almacenes PRODUCTION>)`.
- `frontend/desktop/modules/transfers/dialogs/cycle_dialogs.py:91-107` — `ReceiveTransferDialog` no ofrece elegir almacén destino (solo cantidad y aceptado).

## Impacto
Gerente de sucursal / producción: lo recibido no se puede despiezar; la tentación operativa es ajustar saldos a mano o recibir dos veces.

## Objetivo
- El almacén destino se elige (o se confirma) explícitamente al recibir; el valor por omisión sale de la política del destino, no de una constante `PURCHASE`.
- Si el almacén de recepción difiere del de producción, existe un movimiento interno autorizado y trazable (con permiso, actor y documento) que lo deja disponible para despiece.
- Prueba: 100 kg de canal planta → POS quedan visibles en `lots` tras recibir (directo o con movimiento interno); nunca saldo modificado desde UI ni doble recepción.

## Alcance
- **Incluye:** selección de almacén destino en la recepción de transferencias, movimiento interno recepción → producción, pruebas.
- **No incluye:** la regla única de resolución de ubicación para todos los flujos (SDLC-INV-003); la coordinación durable recepción → transformación (SDLC-PROC-001); la captura de peso/lote (SDLC-TRF-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` si el movimiento cambia valuación; sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio (SDLC-CORE-012), suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-INV-003 ya registraba este hallazgo dentro de su problema general (ubicaciones distintas por flujo); este ítem toma el caso transferencia → producción para la oleada 1 y debe usar el resolvedor único de INV-003 si llega antes. SDLC-ARQ-SCOPE-001 (almacenes acoplados a sucursal). Memoria LOG-INT.

## Preguntas abiertas
- ¿El almacén por omisión al recibir una transferencia hacia una sucursal con despiece debe ser directamente `PRODUCTION`, o siempre recepción y luego movimiento interno? · bloquea `/sdlc-design SDLC-TRF-003`
- ¿Quién autoriza el movimiento interno recepción → producción (el mismo que recibe, o un segundo usuario)? · bloquea `/sdlc-design SDLC-TRF-003`
