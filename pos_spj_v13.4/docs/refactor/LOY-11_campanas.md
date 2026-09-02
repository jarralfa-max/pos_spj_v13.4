# LOY-11 — Campañas

Fecha: 2026-08-31
Alcance: master prompt §19, fase LOY-11 (Audiencias, Aprobaciones, Vigencia, Límites).

## Qué se construyó

`backend/domain/loyalty/entities/campaign.py` — `Campaign` (10 tipos de §19, 8 estados: DRAFT→
PENDING_APPROVAL→APPROVED→SCHEDULED→ACTIVE⇄PAUSED→COMPLETED, o CANCELLED). `audience_definition` queda como
string opaco — no existe motor de segmentación de audiencias en este bounded context ni se consumen los
segmentos de CRM por referencia todavía; una fase futura puede reemplazarlo por un value object estructurado
sin tocar el ciclo de vida.

Esquema `loyalty_campaigns` (`UNIQUE(program_id, code)`, migración 231 — verificado sin colisión con la
tabla no relacionada `marketing_campaigns` de Settings/Document Output, migración 215), repositorio
(`campaign_repository.py`), y `backend/application/loyalty/use_cases/campaign_use_cases.py`:
`CreateCampaignUseCase` (envía a aprobación automáticamente, mismo criterio que
`CreateLoyaltyProgramUseCase` — LOY-4), `ApproveCampaignUseCase`, `ScheduleCampaignUseCase`,
`ActivateCampaignUseCase`, `PauseCampaignUseCase`, `CompleteCampaignUseCase`, `CancelCampaignUseCase`.

## Segregación de funciones aplicada en la propia entidad

A diferencia de LOY-1's `authorize_exception()` (que requiere un segundo usuario en tiempo de autorización),
aquí §60 ("quien crea campaña no la activa solo") se aplicó directamente en `Campaign.approve()`/
`.activate()`: comparan `approved_by_user_id`/`activated_by_user_id` contra `created_by_user_id` y lanzan
`LoyaltySegregationOfDutiesError` si coinciden — la regla vive en el dominio, no solo en la capa de
autorización, así que ningún caso de uso futuro puede saltársela por accidente.

## Tests

14 tests nuevos, todos pasando en el primer intento: `tests/unit/loyalty/test_loyalty_campaign.py` (8,
dominio, incluyendo que el creador no puede aprobar ni activar su propia campaña) y
`tests/unit/loyalty/test_loyalty_campaign_use_cases.py` (6, ciclo de vida completo con usuarios distintos).
Verificado con bootstrap real — migración 231 corre limpia junto a `marketing_campaigns`/`content_campaigns`
sin colisión.

260 tests LOY-1..11 corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-12 (Cupones): `CouponDefinition`/`CouponInstance` — una campaña con `benefit_type="COUPON"` podrá
  referenciar una `CouponDefinition` vía `benefit_reference_id`.
- Sin límites de frecuencia/presupuesto realmente aplicados todavía — `frequency_cap`/`customer_cap`/
  `budget_limit` se almacenan pero ningún caso de uso los verifica contra actividad real (necesitaría
  integración con Ventas para saber cuánto se ha gastado/aplicado).
