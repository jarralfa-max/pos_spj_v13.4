# LOY-21 — Lotes

Fecha: 2026-08-31
Alcance: master prompt §43-44 (LoyaltyCardBatch/LoyaltyCardBatchItem), fase LOY-21.

## Primera fase que conecta Plantillas + Pliegos/Imposición + Tarjetas

Hasta ahora Plantillas (LOY-17/18/19) y Pliegos/Imposición (LOY-20) eran conceptos de configuración
aislados. `CreateLoyaltyCardBatchUseCase` es la primera pieza que los une con Tarjetas (LOY-16): dada una
plantilla ACTIVE (con una versión vigente real) y un perfil de imposición ya calculado, más una lista de
`(customer_id, membership_id)`, emite una `LoyaltyCard` + `LoyaltyCardPublicToken` real por destinatario
(reutilizando exactamente la misma lógica de dominio que `IssueLoyaltyCardUseCase` de LOY-16, pero SIN
delegar a ese caso de uso — el lote se gatea con el permiso distinto `BATCH_CREATE`, no `CARD_CREATE`, mismo
principio de composición de todas las fases anteriores).

## sheets_required y sheet_number/position_in_sheet: siempre derivados

`LoyaltyCardBatch.sheets_required` es `ceil(item_count / cards_per_sheet)` (división de techo con enteros,
`-(-a // b)` — sin importar `math.ceil` para evitar la conversión a float). `LoyaltyCardBatchItem.
create_for_index()` deriva `sheet_number`/`position_in_sheet` del ÍNDICE SECUENCIAL del ítem dentro del lote
y de `cards_per_sheet` — nunca se aceptan como parámetros independientes que un llamador pudiera hacer
inconsistentes con el orden real de emisión. Mismo principio que LOY-20 aplicó a columnas/filas de
imposición, ahora aplicado a la posición física de cada tarjeta dentro de un pliego.

## Ciclo de vida del lote con segregación de funciones

`LoyaltyCardBatch`: DRAFT→PENDING_APPROVAL→APPROVED→PRINTING→COMPLETED, con CANCELLED alcanzable desde
cualquier estado no terminal. `approve()` exige que el aprobador sea distinto de quien generó el lote —
mismo patrón que Campañas de Fidelidad (LOY-11) y Plantillas (LOY-17). Completar el lote no es una
transición manual separada: `MarkLoyaltyCardBatchItemPrintedUseCase` completa automáticamente el lote
(`batch.complete()`) en la MISMA transacción cuando el último ítem pendiente se marca impreso — un lote
nunca queda "olvidado" en PRINTING con todos sus ítems ya resueltos.

## Qué se construyó

Entidades `LoyaltyCardBatch` y `LoyaltyCardBatchItem`. Esquema `loyalty_card_batches`/
`loyalty_card_batch_items` (extiende `create_loyalty_cards_schema()`, migración 239; verificado sin
colisión contra la tabla legacy `card_batches` de `m000_base_schema.py` — nombres nuevos con prefijo
`loyalty_card_`), repositorios, `LoyaltyCardsUnitOfWork` extendido, y `backend/application/loyalty_cards/
use_cases/batch_use_cases.py`: creación de lote (emite tarjetas reales), envío a aprobación, aprobación,
inicio de impresión, cancelación, marcar ítem impreso (con autocompletado del lote) / fallido.

## Alcance honesto

- Ningún caso de uso genera todavía el PDF de imposición real para enviar a imprenta — eso es LOY-22.
- `card_type` del lote es un parámetro único para todo el lote (todas las tarjetas del lote son físicas o
  todas digitales) — no hay lotes mixtos en esta fase.
- Reintentar un ítem `FAILED` (volver a PENDING para reimprimirlo) no está implementado — un ítem fallido
  queda fallido; una reimpresión real de un lote es trabajo de LOY-22.

## Tests

19 tests nuevos (`test_batch_domain.py`: 11; `test_batch_use_cases.py`: 8), todos pasando en el primer
intento real. Verificado con bootstrap real — migración 239 corre limpia, las 9 tablas `loyalty_card*`
existen juntas.

483 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-22 (Impresión): generación real del PDF de imposición, reintentos de ítems fallidos, reimpresión de
  lote completo.
- LOY-23 (Tarjeta digital): `LoyaltyDigitalCardProjection` para las tarjetas `DIGITAL` del lote.
