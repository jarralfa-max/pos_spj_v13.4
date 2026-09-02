# LOY-15 — Sorteos (Sweepstakes)

Fecha: 2026-08-31
Alcance: master prompt §27 (modelo) + §28 (regla folio/boleto) + §29
(antifraude, parcial), fase LOY-15.

## Bounded context nuevo, separado de la rifa legacy

`backend/domain/sweepstakes/` es un bounded context nuevo, independiente de
Fidelidad — un sorteo es su propio mecanismo promocional, aunque comparte la
superficie de permisos `GROWTH_ENGINE.sorteo.*` (ya definida en LOY-1:
`LoyaltyPermissions.SWEEPSTAKES_VIEW/MANAGE/DRAW/TICKET_PRINT/
TICKET_REPRINT`, y ya registrada en `core/security/permission_catalog.py` —
LOY-1 se adelantó correctamente a esta fase).

Ya existía un subsistema de rifas legacy (`raffles`, `raffle_tickets`,
`raffle_winners`, `raffle_rules`, `raffle_prizes`, `raffle_financial_ledger`,
`raffle_eligible_*` — migración 113, `LoyaltyService`) que Ventas SÍ consume
hoy mismo en producción: `backend/infrastructure/integrations/
sales_sweepstakes_client.py` (`SalesSweepstakesClient`, del cutover SET-15)
emite boletos de rifa al cobrar una venta llamando a
`core.services.loyalty_service.LoyaltyService` contra esas tablas legacy.
Las tablas nuevas se nombraron con el prefijo `sweepstakes_` precisamente
para no colisionar con `raffle_*` — ambos esquemas conviven hasta que LOY-24
(Integraciones) reconecte `SalesSweepstakesClient` al nuevo dominio y LOY-27
elimine las tablas/servicio legacy. Verificado con grep contra
`migrations/m000_base_schema.py` y `113_raffle_subsystem.py` antes de
nombrar — sin colisión.

## La regla central de §28: un boleto nunca existe sin un derecho previo

`SweepstakesEntry` es un registro append-only (nunca se edita/elimina, mismo
patrón que `LoyaltyTransaction`) que representa un derecho ya ganado (N
"chances"). `SweepstakesTicket.entry_id` es un campo obligatorio a nivel de
tipo — el constructor de la entidad literalmente no permite crear un boleto
sin un `entry_id` — y `IssueSweepstakesTicketUseCase` además verifica en la
capa de aplicación que ese `entry_id` corresponde a una `SweepstakesEntry`
real, ya persistida, de la MISMA campaña, antes de emitir el boleto.

La reimpresión (`PrintSweepstakesTicketUseCase`) nunca crea un boleto ni un
derecho nuevo: `SweepstakesTicket.record_print()` muta la MISMA fila
(incrementa `print_count`, actualiza `last_printed_at`) — la primera llamada
transiciona ISSUED→PRINTED y usa el permiso `SWEEPSTAKES_TICKET_PRINT`; toda
llamada posterior es una reimpresión y usa `SWEEPSTAKES_TICKET_REPRINT`
(gate distinto, tal como especifica LOY-1's catálogo).

## Antifraude del sorteo (§29, parcial): semilla reproducible, no solo impredecible

`ExecuteSweepstakesDrawUseCase` usa `secrets.token_hex(16)` para generar el
`random_seed` (impredecible ANTES del sorteo) pero baraja el pool con
`random.Random(seed)` — no con `SystemRandom` directo — a propósito:
`SystemRandom` sería impredecible pero irreproducible después del hecho, y
un auditor debe poder tomar el `random_seed` y el `pool_hash` ya grabados y
re-derivar exactamente los mismos ganadores. `SweepstakesDrawPolicy.
pool_hash()` es un hash SHA-256 del conjunto ordenado de IDs de boletos
elegibles (excluye `VOID` y boletos que ya ganaron en un sorteo anterior de
la misma campaña) — mismo propósito que `raffle_winners.pool_hash` en el
esquema legacy, pero ahora derivable independientemente en vez de solo
almacenado.

Una campaña puede correr más de un sorteo (p. ej. 1er lugar en un sorteo,
2do lugar agregado y sorteado después) — `campaign.mark_drawn()` solo se
invoca en el PRIMER sorteo completado; sorteos posteriores de la misma
campaña dejan el estado como está (ya `DRAWN`), en vez de fallar por una
transición de estado inválida.

## Qué se construyó

Entidades: `SweepstakesCampaign` (ciclo DRAFT→PENDING_APPROVAL→APPROVED→
ACTIVE⇄PAUSED→DRAWN→CLOSED/CANCELLED, con segregación de funciones
aprobador≠creador igual que `Campaign` de Fidelidad), `SweepstakesRule`
(1:1 por campaña, `chances_for_amount()` calcula boletos ganados por una
venta), `SweepstakesPrize`, `SweepstakesEntry`, `SweepstakesTicket`,
`SweepstakesDraw`, `SweepstakesWinner`. Política pura
`SweepstakesDrawPolicy` (elegibilidad + hash del pool, sin IO).

Esquema `sweepstakes_{campaigns,rules,prizes,entries,tickets,draws,winners,
outbox}` (migración 235), repositorios + `SweepstakesUnitOfWork`, y
`backend/application/sweepstakes/use_cases/{campaign,entry,draw,winner}_
use_cases.py`: creación/aprobación/activación/pausa/cierre de campaña,
configuración de regla, alta de premio, otorgamiento de derecho (solo
manual por ahora — ver alcance honesto abajo), emisión/impresión/
reimpresión/anulación de boleto, programación/ejecución/cancelación de
sorteo, validación/descalificación/entrega de premio a ganador.

## Alcance honesto

- `GrantSweepstakesEntryUseCase` solo soporta el otorgamiento MANUAL hoy.
  El otorgamiento automático desde una venta real (`PURCHASE_AMOUNT`/
  `PRODUCT_PURCHASE`, usando `SweepstakesRule.chances_for_amount()`)
  requiere un gancho de integración con Ventas que no existe todavía —
  mismo patrón de brecha honesta que LOY-14 documentó para
  cupón/vale de cumpleaños. `SalesSweepstakesClient` HOY llama al sistema
  legacy, no a este nuevo dominio — LOY-24 debe resolver esa migración.
- Ningún dispatcher conecta `sweepstakes_outbox` a un handler real todavía
  (mismo hueco confirmado en cada bounded context de esta sesión).
- No se tocó el subsistema `raffle_*` legacy ni `LoyaltyService` — coexisten
  hasta LOY-27.

## Tests

47 tests nuevos (`tests/unit/sweepstakes/test_sweepstakes_domain.py`: 29;
`test_sweepstakes_use_cases.py`: 18), todos pasando en el primer intento
real. Verificado con bootstrap real completo
(`scripts/bootstrap_db.py`) — migración 235 corre limpia, las 8 tablas
`sweepstakes_*` se crean; los 3 errores de migraciones 024/029/080 que
aparecen en el log son preexistentes y no relacionados (ya documentados en
memoria de sesiones anteriores).

360 tests de todo el dominio Fidelidad/Comercial/Sorteos corridos juntos
(`tests/unit/loyalty`, `tests/unit/commercial_instruments`,
`tests/unit/sweepstakes`, más los 2 archivos de seguridad de LOY-1), sin
regresión.

## Pendiente para fases futuras

- LOY-16 (Tarjetas base): siguiente bounded context, `backend/domain/
  loyalty_cards/` — LOY-1 ya construyó su cimiento de seguridad
  (`permissions.py`, `authorization.py`, `session_authorization.py`,
  `audit.py`, `exceptions.py`).
- Otorgamiento automático de derechos desde una venta real — pendiente,
  señalado arriba.
- Migrar `SalesSweepstakesClient` del sistema legacy a este dominio nuevo —
  trabajo de LOY-24.
- Eliminación de `raffle_*`/`LoyaltyService` — LOY-27.
