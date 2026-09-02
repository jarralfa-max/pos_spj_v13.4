# LOY-23 — Tarjeta digital

Fecha: 2026-08-31
Alcance: master prompt §48 (LoyaltyDigitalCardProjection), fase LOY-23.

## Una proyección, no una segunda fuente de verdad

`LoyaltyDigitalCardProjection` es deliberadamente un modelo de lectura desnormalizado — un snapshot listo
para mostrarse en la pantalla de una app/wallet — nunca la fuente de verdad de nada. `display_fields` (un
dict libre serializado a JSON) lo resuelve y suministra el LLAMADOR; esta pieza nunca cruza a Clientes ni al
ledger de Fidelidad para calcular nombre del cliente, nivel o saldo de puntos — mismo aislamiento de bounded
context aplicado en cada fase de esta sesión (LOY-12, LOY-16, LOY-22).

`refresh()` reemplaza el snapshot COMPLETO, nunca hace merge parcial de campos — así una proyección nunca
queda con una mezcla de valores viejos y nuevos si el llamador olvida incluir algún campo. Verificado con un
test dedicado (`test_refresh_replaces_entire_snapshot`).

## Reutilización de permisos sin inventar uno nuevo

LOY-1 no anticipó específicamente "ver/crear/refrescar tarjeta digital" como una acción granular separada
dentro de `LoyaltyCardsPermissions` — a diferencia de casi todas las fases anteriores, aquí no había un
permiso ya scaffoldeado esperando. En vez de inventar uno nuevo sin coordinarlo con el catálogo central, se
reutilizó `CARD_CREATE` (crear/refrescar la proyección es un efecto secundario directo y estrechamente
acoplado de aprovisionar una tarjeta DIGITAL, no una superficie de escritura independiente) y `CARD_VIEW`
(lectura). Decisión documentada aquí explícitamente, no asumida en silencio — si una fase futura necesita
una acción realmente distinta (p. ej., que el propio cliente refresque su tarjeta desde la app, sin pasar
por un operador), ese sería el momento de pedir un permiso dedicado nuevo.

## Qué se construyó

Entidad `LoyaltyDigitalCardProjection` (una por tarjeta, `UNIQUE(card_id)`). Esquema
`loyalty_digital_card_projections` (extiende `create_loyalty_cards_schema()`, migración 241), repositorio,
`LoyaltyCardsUnitOfWork` extendido, y `backend/application/loyalty_cards/use_cases/
digital_card_use_cases.py`: `CreateLoyaltyDigitalCardProjectionUseCase` (valida que la tarjeta sea DIGITAL y
tenga un token QR activo — reutiliza `LoyaltyCardTokenRepository.get_active_for_card()` de LOY-16 sin
modificarlo), `RefreshLoyaltyDigitalCardProjectionUseCase` (puede rotar el token si uno nuevo está activo),
`GetLoyaltyDigitalCardProjectionUseCase` (lectura para que una futura app/wallet renderice la tarjeta,
incluyendo el token QR para que el cliente lo dibuje del lado del cliente).

## Alcance honesto

- Ninguna API pública/externa expone esto todavía a una app real — esta fase construye el dominio y los
  casos de uso, no un endpoint de wallet.
- El refresco de `display_fields` es manual (invocado explícitamente); no hay una suscripción/evento que
  dispare un refresco automático cuando cambian los puntos o el nivel de membresía en Fidelidad — trabajo de
  integración futuro (LOY-24).

## Tests

13 tests nuevos (`test_digital_card_domain.py`: 6; `test_digital_card_use_cases.py`: 7), todos pasando en el
primer intento real. Verificado con bootstrap real — migración 241 corre limpia, las 11 tablas
`loyalty_card*` existen juntas.

512 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-24 (Integraciones): Ventas, Clientes, Inventario, Finanzas, BI, WhatsApp — incluyendo el refresco
  automático de la proyección digital cuando cambian los datos de origen, y la migración de
  `SalesSweepstakesClient` del sistema legacy de rifas al nuevo dominio `sweepstakes` (LOY-15).
