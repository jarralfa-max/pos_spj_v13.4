# LOY-14 — Cumpleaños y retención

Fecha: 2026-08-31
Alcance: master prompt §18 (Cumpleaños) + §20 (Retención), fase LOY-14 (Reglas, Consentimientos, Campañas,
Win-back).

## Naturaleza de la fase: orquestación, no nuevos conceptos de dominio grandes

A diferencia de fases anteriores, §18/§20 no piden entidades nuevas de gran tamaño — piden que Fidelidad
REACCIONE (emitir un beneficio ya configurado) sin construir un segundo modelo analítico (§20 lo prohíbe
explícitamente para retención). Se construyó una sola entidad de configuración
(`BirthdayBenefitConfig`, §18) y dos casos de uso de orquestación que reutilizan directamente lo ya
construido en LOY-6 (ledger de puntos) y LOY-11 (`Campaign.benefit_type`/`benefit_reference_id`, ya
existentes desde esa fase, sin uso hasta ahora).

## Bug real de diseño encontrado y corregido ANTES de correr tests

Un primer borrador de `GrantBirthdayBenefitUseCase` intentaba componerse llamando a
`AccrueLoyaltyPointsUseCase`/`IssueCouponInstanceUseCase`/`IssueVoucherInstanceUseCase` completos — pero esos
casos de uso llaman `self._auth.require(actor_user_id, ...)` contra un `PermissionChecker` real respaldado
por sesión. Un otorgamiento de cumpleaños es disparado por sistema (una fecha coincide), sin un actor humano
autenticado real — en producción, cualquier `actor_user_id` inventado (p. ej. `SYSTEM_ACTOR_ID`) sería negado
por `LoyaltySessionPermissionChecker` (no hay sesión activa para un actor de sistema), así que el
otorgamiento habría fallado SIEMPRE con `PERMISSION_DENIED` en producción real. Corregido antes de escribir
ningún test: `GrantBirthdayBenefitUseCase`/`TriggerCampaignBenefitUseCase` construyen la transacción del
ledger directamente (mismo patrón que las barridas de sistema de LOY-6/7/9: `ExpireLoyaltyPointsUseCase`/
`EvaluateLoyaltyMembershipTierUseCase`), sin pasar por ningún caso de uso con gate de permiso de usuario.

También se encontró y limpió (antes de correr tests) un residuo del hack `__import__(...)` en
`ConfigureBirthdayBenefitUseCase` (mismo anti-patrón ya cometido y corregido dos veces en LOY-6/LOY-10) y
código muerto en `retention_use_cases.py` (`_ELIGIBLE_CAMPAIGN_TYPES` con un `hasattr` innecesario, ya que
`CampaignType.RETENTION` sí existe desde LOY-11).

## Qué se construyó

`backend/domain/loyalty/entities/birthday_benefit_config.py` (`BirthdayBenefitConfig`, valida
consistencia entre `benefit_type` y el campo de referencia requerido: `POINTS`→`points_amount`,
`COUPON`→`coupon_definition_id`, `VOUCHER`→`voucher_definition_id`, `REWARD`→`reward_id`).

Esquema `loyalty_birthday_configs` (`UNIQUE(program_id)` — una configuración por programa; migración 234),
repositorio, y `backend/application/loyalty/use_cases/{birthday_use_cases,retention_use_cases}.py`:
`ConfigureBirthdayBenefitUseCase` (gestión humana normal, permiso `BIRTHDAY_MANAGE`),
`GrantBirthdayBenefitUseCase` (disparado por sistema, respeta `has_marketing_consent` explícito —
Fidelidad no posee datos de consentimiento, §53, los recibe como parámetro),
`TriggerCampaignBenefitUseCase` (disparado por sistema, exige campaña `ACTIVE` de tipo `WIN_BACK`/
`RETENTION`).

## Alcance honesto: solo beneficio POINTS implementado

Tanto `GrantBirthdayBenefitUseCase` como `TriggerCampaignBenefitUseCase` solo implementan el tipo de
beneficio `POINTS` — `COUPON`/`VOUCHER`/`REWARD` devuelven `NOT_IMPLEMENTED` explícito, no un resultado
fabricado. Implementarlos correctamente requeriría cruzar hacia la propia `CommercialInstrumentsUnitOfWork`
de Cupones/Vales SIN pasar por sus casos de uso con gate de permiso (mismo problema ya resuelto para puntos)
— señalado como trabajo real pendiente, no ocultado.

## Tests

17 tests nuevos, todos pasando en el primer intento real (tras las correcciones de diseño previas a
escribirlos): `tests/unit/loyalty/test_loyalty_birthday_config.py` (8, dominio) y
`test_loyalty_birthday_and_retention_use_cases.py` (9, incluyendo denegación real por falta de
consentimiento, configuración deshabilitada que no otorga sin error, y beneficio de retención emitido desde
una campaña WIN_BACK activa). Verificado con bootstrap real — migración 234 corre limpia.

331 tests LOY-1..14 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-15 (Sorteos): bounded context nuevo (`sweepstakes`, §7.2).
- Beneficio COUPON/VOUCHER/REWARD para cumpleaños/retención — pendiente, señalado arriba.
- Ningún disparador real (barrida diaria de cumpleaños, señal de BI) invoca estos casos de uso todavía.
