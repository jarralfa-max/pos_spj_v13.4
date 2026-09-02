# LOY-0 — Auditoría del bounded context de Fidelidad / Instrumentos Comerciales / Sorteos / Tarjetas

Fecha: 2026-08-28
Alcance: master prompt "REFACTOR ENTERPRISE DEL MÓDULO DE FIDELIDAD..." (LOY-0..LOY-28).
Mismo protocolo que `docs/refactor/customers_crm_master_prompt.md` (CRM-0) y `SALES-0`/`PUR-0A`: auditar antes de construir, no asumir greenfield.

## 0. Nota de raíz de repo

Confirmada la anomalía ya documentada en memoria (`env_nested_git_repo_pos_spj`): la raíz real de la aplicación es
`pos_spj_v13.4/pos_spj_v13.4/` (dentro de `Downloads/pos_spj_v13.4/`). Existe además una tercera copia anidada
`pos_spj_v13.4/pos_spj_v13.4/pos_spj_v13.4/` con su propio árbol duplicado (incluye su propio
`frontend/desktop/modules/purchasing/...`) — tratarla como copia obsoleta a limpiar por separado, no como
fuente de verdad. Todas las rutas de este documento son relativas a `pos_spj_v13.4/pos_spj_v13.4/`.

## 1. Veredicto

**Fidelidad NO es greenfield.** Está en el mismo estado que tenía Procurement/Products antes de su refactor:
una implementación legacy grande, funcional y con tests (~4,000+ líneas entre servicios/repos/UI, ~30 archivos
de test, varios docs de auditoría previos), **más** una frontera de arquitectura limpia que YA fue declarada y
parcialmente cableada desde el otro lado por bounded contexts ya terminados (Finanzas, Ventas, CRM,
Document Output/Settings) — todos esperando a que aparezca un `backend/domain/loyalty` real (y sus hermanos).

No existen `backend/domain/loyalty/`, `backend/domain/commercial_instruments/`, `backend/domain/sweepstakes/`,
`backend/domain/loyalty_cards/`, ni `frontend/desktop/modules/loyalty/`. Esto es una reconstrucción de alto
apalancamiento sobre una base real, no una construcción desde cero.

## 2. Módulos UI legacy (`modulos/`)

| Archivo | Líneas | ¿Cableado en `main_window.py`? | Qué hace |
|---|---|---|---|
| `modulos/tarjetas.py` | 61 | Sí — `_conectar("TARJETAS_FIDELIDAD", ModuloTarjetas, "💳 Tarjetas Fidelidad")` | Wrapper delgado que instancia `ModuloLoyaltyCardDesigner`. |
| `modulos/loyalty_card_designer.py` | 801 | Sí (vía tarjetas.py) | `ModuloLoyaltyCardDesigner` — 5 tabs: Diseñador, Config QR, Generar Lote, Emitidas, Historial Lotes. Todo vía `core/services/loyalty_card_designer_service.py`. |
| `modulos/fidelidad_config.py` | 671 | Sí — `_conectar("GROWTH_ENGINE", ModuloFidelidadConfig, "⭐ Fidelización")` | `ModuloFidelidadConfig` — 5 tabs: Metas y Misiones, Referidos, Cumpleaños, Retención, Rifas y Sorteos (incluye wizard de creación de rifa). Todo vía `container.loyalty_service`. |
| `modulos/modulo_growth_engine.py` | 353 | **No — muerto/huérfano.** Importado en `main_window.py:1560` pero nunca pasado a `_conectar(...)`. | `ModuloGrowthEngine` — 5 tabs que solapan/duplican la pestaña "Metas y Misiones" de `fidelidad_config.py`. Iteración anterior nunca eliminada. |
| `modulos/growth_engine.py` | No existe en disco | — | Docs (`docs/audits/LOYALTY_LEGACY_ROUTES.md`, `LOYALTY_REFACTOR_BUGFIX_REPORT.md`) aún lo describen como "shim temporal" con retiro programado 2026-08-31 — docs desactualizados, ya no existe. |

No hay módulos UI separados para cupones/vales/sorteos como entidades propias — sorteos vive dentro de la
pestaña "Rifas y Sorteos" de `fidelidad_config.py`.

## 3. Servicios/repositorios legacy

| Archivo | Líneas | Tablas | Notas |
|---|---|---|---|
| `core/services/loyalty_service.py` | 1092 | `loyalty_ledger`, `loyalty_pasivo_log`, `clientes`, `usuarios`, `configuraciones`, tablas de rifa | Fachada única: acumulación (`acreditar_venta`/`process_loyalty_for_sale`), canje (`canjear`/`apply_redemption`/`preview_redemption`), referidos, cumpleaños, retención, ciclo de vida completo de rifas. |
| `repositories/loyalty_repository.py` | 757 | `loyalty_ledger`, `clientes`, `configuraciones`, `referidos`, `tarjetas_fidelidad`, `raffle_*` | Capa SQL detrás de `LoyaltyService`. |
| `application/services/loyalty_application_service.py` (raíz `application/`, NO `backend/application/`) | 62 | vía `LoyaltyRepository` | Capa de casos de uso idempotente: `award_points_for_sale`, `preview_redemption`, `redeem_points_for_sale`, `reverse_redemption`, `expire_points`, `assign_card_to_customer`. |
| `core/services/card_batch_engine.py` | 512 | `card_batches`, `tarjetas_fidelidad`, `card_assignment_history` | **Segundo motor de lotes de tarjetas, sin uso en producción** — cero llamadores reales, solo 3 archivos de test. |
| `core/services/loyalty_card_designer_service.py` | 139 | `configuraciones`, `tarjetas_fidelidad`, `lotes_tarjetas_pdf` | El que SÍ está cableado a la UI. Su propio docstring admite que referencia columnas legacy (`codigo`, `puntos`, `fecha_emision`) que ya no existen en el schema born-clean y "ya fallan en runtime". |
| `repositories/tarjetas.py` | 414 | `tarjetas_fidelidad`, `historico_tarjetas`, `config_diseno_tarjetas`, `clientes` | **Tercer repositorio de tarjetas**, aparentemente no importado por los otros dos — candidato a código muerto/duplicado. |

**Hallazgo clave**: existen **tres rutas distintas de gestión de tarjetas** contra esencialmente las mismas
tablas, con solo una viva. Esta duplicación es lo primero a resolver en la reconstrucción.

## 4. Esquema de base de datos

| Tabla | Creada en | PK |
|---|---|---|
| `tarjetas_fidelidad` | `m000_base_schema.py:1728` (+ columnas `numero`/`batch_id`/`activa` vía `112_card_schema_reconciliation.py`) | `TEXT PK` |
| `card_batches` | `m000_base_schema.py:1752` | `TEXT PK` |
| `card_assignment_history` | `m000_base_schema.py:1768` | `TEXT PK` |
| `historico_tarjetas` | `m000_base_schema.py:1780` | `TEXT PK` |
| `config_diseno_tarjetas` | `m000_base_schema.py:1386` | `TEXT PK` |
| `loyalty_ledger` | `standalone/057_loyalty_ledger_unificado.py`, re-canonicalizado en `092_loyalty_ledger_canonicalization.py` (`UNIQUE(cliente_id,tipo,referencia)`, migra datos desde `growth_ledger` legacy) | `TEXT PK` |
| `loyalty_pasivo_log` | `m000_base_schema.py:3080` | `TEXT PK` |
| `referidos` | `m000_base_schema.py:322` | `id TEXT PK`, **pero `cliente_referidor`/`cliente_referido` siguen siendo `INTEGER`** — no migrados a UUIDv7. |
| `raffles`, `raffle_tickets`, `raffle_financial_ledger`, `raffle_winners`, `raffle_rules`, `raffle_prizes`, `raffle_eligible_products/categories/branches` | `standalone/113_raffle_subsystem.py` (centraliza lo que `LoyaltyRepository.ensure_raffle_tables()` creaba ad-hoc) | `TEXT PK`, born-clean UUIDv7 |
| `marketing_campaigns` | `standalone/215_marketing_campaigns_schema.py` → `document_output_schema.py` | born-clean |
| `sales.loyalty_redeemed_amount` | `standalone/202_sales_loyalty_redemption_column.py` (columna, TEXT) | n/a |
| `growth_ledger` | legacy, predecesora de `loyalty_ledger`; migrada en 092 pero no confirmado su DROP | INTEGER-era |

No existen tablas propias para cupones/vales/gift cards/store credit — solo el contrato de eventos y el
reconocimiento contable en Finanzas (ver §5).

## 5. Arquitectura limpia ya declarada por otros bounded contexts (esperando un productor)

- `backend/application/commands/loyalty_commands.py`, `backend/application/use_cases/assign_loyalty_card_use_case.py`,
  `backend/application/queries/loyalty_query_service.py` — puro scaffolding, sin lógica real.
- `backend/domain/finance/entities/commercial_obligation.py` — real y probado, pero explícitamente solo el lado
  de Finanzas ("Finance never owns the operational instrument").
- `backend/application/event_handlers/finance/*` — **12 handlers reales y probados**: `loyalty_points_issued/
  redeemed/expired_handler.py`, `loyalty_reward_granted_handler.py`, `loyalty_transaction_reversed_handler.py`,
  `coupon_issued/redeemed/expired_handler.py`, `voucher_issued/redeemed/expired_handler.py`,
  `gift_card_sold/redeemed/refunded_handler.py`. Cubiertos por `tests/integration/finance/test_loyalty_instruments.py`.
- `backend/shared/events/event_names.py` — ya define el contrato canónico completo: `LOYALTY_POINTS_ISSUED/
  EXPIRED`, `LOYALTY_REWARD_GRANTED`, `LOYALTY_TRANSACTION_REVERSED`, `COUPON_*`, `VOUCHER_*`, `GIFT_CARD_*`,
  `STORE_CREDIT_*`, `PROMOTIONAL_BALANCE_*`, `STORED_VALUE_ADJUSTED`.
  **GAP CRÍTICO: nada en el repo publica ninguno de estos eventos canónicos.** Los handlers de Finanzas solo se
  ejercitan con payloads sintéticos en tests. El `LoyaltyService` legacy publica un conjunto de nombres
  completamente distinto (`LOYALTY_POINTS_EARNED/REDEEMED/REVERSED/EXPIRED` vía `core/events/event_bus.py`) que
  Finanzas no escucha. **Esta es la tarea de más alto valor de toda la reconstrucción**: el nuevo dominio de
  Fidelidad debe emitir exactamente el contrato que Finanzas ya construyó y probó.
- `backend/domain/document_output/` — solo puntos de contacto para impresión de tickets, no propiedad:
  `value_objects/loyalty_summary.py` (DTO puro), `value_objects/sweepstakes_ticket_data.py`,
  `sweepstakes_ports.py` (`SweepstakesTicketPort`, protocolo sin implementación real todavía).
- `frontend/desktop/modules/finance/pages/commercial_instruments_page.py` — su propio docstring aclara que NO
  administra cupones/puntos/campañas, solo muestra el reconocimiento contable.
- No existe entrada `loyalty` en `frontend/desktop/modules/` (sí existen customers_crm, sales_pos, finance,
  purchasing, etc.).

## 6. Consumidores

- **Ventas/POS**: `modulos/ventas.py` ya no existe (reemplazado por `modulos/ventas_pos.py`, sin referencias a
  fidelidad). La integración real está en `core/use_cases/venta.py` (documenta explícitamente que la
  acreditación ocurre solo vía `wiring.py` al recibir `VENTA_COMPLETADA`, nunca en el UC) y en
  `backend/application/services/sales_application_service.py`, que ya tiene `LoyaltyRedemptionRequest`/
  `LoyaltyRedemptionPreview` y pasa `puntos_canjeados`/`puntos_ganados`/`nivel`/`loyalty_result` por todo el
  checkout, leyendo del `LoyaltyService` legacy inyectado. `frontend/desktop/modules/sales_pos/` (customer_panel,
  checkout_panel, totals_card, payment_dialog) ya muestra puntos/`loyalty_total` — **Ventas/POS ya tiene un
  contrato completamente formado esperando un servicio de Fidelidad real.**
- **Clientes/CRM**: guardrail real `tests/architecture/test_customers_crm_does_not_own_loyalty.py` — prohíbe que
  el código de CRM contenga tokens como `tarjetas_fidelidad`, `CardBatchEngine`, `loyalty_ledger`,
  `loyalty_card_template`, `loyalty_card_batch`, `loyalty_qr`, `coupon_ledger`, `voucher_ledger`, `tier_history`,
  `points_ledger`, `points_balance`. El documento `docs/refactor/customers_crm_master_prompt.md` (líneas 57-65)
  ya declara el alcance de Fidelidad casi textualmente igual al master prompt actual, y su línea 270 pide una
  `LoyaltyCustomerSummaryQuery` que **no existe** — hoy CRM/WhatsApp leen fidelidad vía
  `LoyaltyService.get_customer_loyalty_summary()` (legacy) o no la leen.
- **WhatsApp** (`whatsapp_service/`, fuera del árbol anidado): lee fidelidad indirectamente vía el Customer
  Master de CRM (`erp/bridge.py:330`, comentario "CRM-21"), no contra tablas de Fidelidad directamente.

## 7. Tests existentes (~30 archivos)

`tests/`: `test_loyalty_application_service.py`, `test_loyalty_repository_phase2.py`,
`test_loyalty_redemption_source.py`, `test_loyalty_redemption_transactional.py`,
`test_loyalty_single_accrual.py`, `test_loyalty_bugfix_regression.py`, `test_loyalty_canonical_migration.py`,
`test_loyalty_refactor_regression.py`, `test_loyalty_card_designer_service.py`,
`test_card_subsystem_born_clean.py`, `test_loyalty_event_wiring_phase7.py`,
`test_phase6_sale_loyalty_policy.py`, `test_sales_customer_loyalty.py`, `test_fase2_loyalty_scanner.py`,
`test_loyalty_raffle_issue_tickets.py`, `test_raffle_financial_safety.py`, `test_raffle_rules_engine.py`,
`test_raffle_sales_pos_cutover.py`, `test_ticket_designer_raffle_layout_contract.py`.

`tests/integration/`: `test_card_batch_engine_lifecycle.py`, `test_loyalty_snapshot_scheduler_schema.py`,
`finance/test_loyalty_instruments.py`, `document_output/test_sales_reprint_marketing_loyalty_cutover.py`,
`document_output/test_sweepstakes_document_persistence.py`.

`tests/unit/`: `document_output/test_loyalty_summary_and_ticket_data.py`,
`document_output/test_sweepstakes_ticket_data.py`, `document_output/test_sweepstakes_integration_and_reprint.py`,
`test_remediacion0_raffle_finance_handler.py`, `test_sales_pricing_loyalty.py`, `test_sales_sweepstakes.py`.

`tests/migrations/test_112_card_schema_reconciliation.py`;
`tests/architecture/test_customers_crm_does_not_own_loyalty.py`.

## 8. Docs existentes

No existe una serie `docs/refactor/LOY-*` previa (a diferencia de CRM-1..42, SALES-0..22, PUR-*, TRF-*, LOSS-*,
CASH-*). Pero Fidelidad no está indocumentada:

- `docs/architecture/LOYALTY_FLOW.md`, `LOYALTY_EVENT_FLOW.md`, `LOYALTY_LEDGER_SOURCE_OF_TRUTH.md` — describen
  el flujo actual y los nombres de eventos legacy.
- `docs/audits/LOYALTY_REFACTOR_AUDIT.md`, `LOYALTY_LEGACY_ROUTES.md`, `LOYALTY_REFACTOR_BUGFIX_REPORT.md` —
  auditorías de refactors incrementales previos; **desactualizadas** (referencian `modulos/growth_engine.py`
  como vivo, ya no existe en disco).
- `docs/refactor/customers_crm_master_prompt.md` §3 — el estatuto de alcance más autoritativo de Fidelidad hoy,
  desde el lado de CRM.
- `docs/refactor/MODULE_QUEUE.md:35-36` marca `FIDELIDAD`/`TARJETAS_FIDELIDAD` como "DONE" — pero es la tabla
  vieja de `SPJ_REFACTOR_SKILL.md` (Fase A: quitar `int()`, quitar defaults hardcodeados), NO implica que la
  transformación enterprise esté completa (mismo patrón ya visto en VENTAS/CLIENTES).

## 9. Permisos (`core/security/permission_catalog.py`)

Extremadamente plano — solo:
- `"GROWTH_ENGINE": ["ver"]` (línea 331) — protege todo `ModuloFidelidadConfig`.
- `"TARJETAS_FIDELIDAD": ["ver"]` (línea 332) — protege `ModuloTarjetas`/`ModuloLoyaltyCardDesigner`.
- Una cadena suelta `"fidelidad.ver"` en el bundle de `pedidos`/`entregas`.

Cero códigos granulares `FIDELIDAD.*`/`LOYALTY.*`/`TARJETA.*`/`CUPON.*`/`VALE.*`/`SORTEO.*` (comparar con
`POS`/`CAJA`, 15-30 códigos punteados cada uno). Sin distinción de permiso entre ver saldo, canjear puntos,
ajustar saldo, bloquear tarjeta, crear/activar rifa, aprobar entrega de premio, etc.

## 9.1. Corrección post-LOY-3 (2026-08-28): tablas legacy no detectadas originalmente

Al construir el esquema limpio (LOY-3) se encontró que `migrations/m000_base_schema.py::_create_loyalty`
(~línea 1538) crea toda una familia adicional de tablas legacy del Growth Engine que esta auditoría original
no listó: `loyalty_programs` (colisionó de hecho con un primer borrador del nuevo esquema — ver
`docs/refactor/LOY-3_esquema_limpio.md`), `loyalty_config`, `loyalty_scores`, `loyalty_level_history`,
`loyalty_challenges`, `loyalty_challenge_progress`, `loyalty_community_goals`,
`loyalty_community_contributions`, `loyalty_budget_caps`, `loyalty_multiplier_rules`,
`loyalty_redemption_limits`, `loyalty_roi_tracking`, `loyalty_snapshots`, `loyalty_ticket_messages`, y
`config_programa_fidelidad`. Todas con columnas en español y/o `REAL`, mismo perfil que el resto del §2-3 —
se añaden al inventario de legacy calificado para LOY-27, no cambian el veredicto de §1/§10.

## 10. Conclusión y orden de trabajo recomendado

Fidelidad queda entre el perfil "Procurement" (mucho legacy real que reconciliar) y "Sales" (otros contextos ya
construyeron expectativas contra ella). La lógica de negocio legacy es amplia y probada (puntos vía ledger,
referidos, cumpleaños, retención, ciclo de vida completo de rifas, diseño/impresión/QR/lotes de tarjetas), pero
vive 100% fuera de la arquitectura limpia, con duplicación real que resolver (3 rutas de tarjetas).

Consistente con CLAUDE.md Prioridad 0 (no perder lógica de negocio sin migración completa) y con el propio orden
de fases del master prompt (LOY-27 "Eliminación de legacy" es la penúltima fase, no la primera — igual que
CRM-24 solo eliminó `modulos/clientes.py` después de que CRM-21/22/23 migraran consumidores y construyeran
reemplazo real): construir primero el dominio nuevo completo (LOY-1..26), verificar que reemplaza function por
función a lo legacy, y solo entonces ejecutar la eliminación (LOY-27).

**Primer movimiento de más alto valor**: construir el dominio de Fidelidad para que emita el contrato canónico
de eventos que Finanzas ya tiene implementado y probado (`EventName.LOYALTY_*`/`COUPON_*`/`VOUCHER_*`/
`GIFT_CARD_*`), y satisfacer los contratos que Ventas (`LoyaltyRedemptionRequest`) y CRM
(`LoyaltyCustomerSummaryQuery`) ya asumen.
