# BI-28 — Alerts UI

Estado: **DONE**, alcance deliberadamente limitado a 2 de los 16 tipos de
alerta canónicos (ver justificación abajo)

## Alcance

§14/§46-50: página "Alertas" — evaluar reglas de umbral contra métricas
reales y aplicar el ciclo de vida (§50: OPEN→ACKNOWLEDGED→IN_PROGRESS→
RESOLVED/DISMISSED/EXPIRED).

## Decisión central: migrar 2 alertas ad-hoc del dashboard al motor canónico, no inventar nuevas

`BiDashboardService._alerts()` (BI-4, prexistente) ya calcula "merma alta" y
"margen bajo" con `if` de Python directos contra `BiSettingsService`. BI-20
ya construyó un motor de reglas de umbral genérico
(`AnalyticalAlertRule.is_breached()` + `AnalyticalAlertEngine.evaluate()`,
con fingerprint de deduplicación y cooldown, §49) pero **nunca tuvo un
consumidor real** — evaluaba reglas sintéticas en sus propios tests. BI-28
conecta ambos: dos `AnalyticalAlertRule`s reales (`WASTE_SPIKE` sobre la KPI
`merma`, `MARGIN_DROP` sobre `margen`) se evalúan contra los valores que
`BiDashboardService.build_dashboard()` YA calcula hoy, produciendo
`AnalyticalAlert`s reales con el ciclo de vida completo de 6 estados que el
`Alert` ad-hoc del dashboard nunca tuvo.

## Por qué solo 2 de los 16 `AlertType` (§47)

Los otros 14 (`STOCKOUT_RISK`, `FORECAST_DEVIATION`, `PURCHASE_RISK`,
`BRANCH_UNDERPERFORMANCE`, `CASH_RISK`, etc.) necesitan una fuente de
métrica real que hoy no está expuesta como un valor escalar único listo
para comparar contra un umbral — requerirían nueva agregación (ej.
"¿cuántos productos con riesgo de quiebre por sucursal?" de BI-13/17, que es
una lista, no un escalar). Construir esas reglas con datos inventados habría
sido la misma "infraestructura sin consumidor real" evitada en cada fase
anterior — documentado, no fabricado.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/presenters/alert_explorer_presenter.py` | `AlertExplorerPresenter.evaluate_all()` — construye las 2 reglas reales (umbral desde `BiSettingsService.threshold_merma_pct`/`threshold_margen_bajo_pct`, reutilizados — §3/§64, no un segundo umbral inventado) y las evalúa contra `BiDashboardService.build_dashboard()` real. `apply_transition()` aplica las funciones puras reales de `alert_lifecycle.py` (BI-20), exigiendo un `actor_user_id` real (nunca fabricado) para reconocer/resolver/descartar. |
| `frontend/desktop/modules/business_intelligence/pages/alert_explorer_page.py` | `AlertExplorerPage` — botón "Evaluar alertas" → `StandardTable` (Tipo/Severidad/Estado/Mensaje, puede listar 0, 1 o 2 filas — un resultado vacío es real, no una carga fallida) + campo de motivo + botones de ciclo de vida (Reconocer/Iniciar progreso/Resolver/Descartar) sobre la fila seleccionada. |
| `business_intelligence_routes.py` (editado) | `bi_alerts` ahora construye `AlertExplorerPage`, pasando el `actor_user_id` que ya recibía `build_page()` desde BI-23 (hasta ahora sin usar). |

## Limitaciones honestas de esta fase

- **Cooldown/dedup inertes**: `AnalyticalAlertEngine.evaluate()` recibe
  `existing_alerts=()` siempre — sin persistencia de `AnalyticalAlert`
  (mismo hueco documentado que `BusinessRecommendation`, BI-22/27) no hay
  historial contra el cual comparar el fingerprint, así que cada evaluación
  parte de cero. El mecanismo es real y probado (BI-20); simplemente no
  tiene todavía memoria entre sesiones.
- **Ciclo de vida solo en memoria**: igual que BI-27, las transiciones
  aplicadas se pierden al refrescar la tabla.
- El actor autenticado real (`actor_user_id`) todavía no llega desde ningún
  caller en producción — `build_page()` lo acepta desde BI-23 pero
  `main_window.py` no invoca este módulo todavía (BI-23's propia decisión de
  no-corte).

## Auditoría REGLA CERO

`AnalyticalAlertRule.id`/`AnalyticalAlert.id`/`rule_id` ya validan UUIDv7 en
su propio `__post_init__` (BI-20) — el presenter solo los invoca. N/A.

## Tests

`test_alert_explorer_presenter.py` (8: mapeo KPI, una evaluación real contra
una conexión sin esquema que confirma el breach real de MARGIN_DROP —
margen=0% bajo el umbral por defecto de 10% — y que WASTE_SPIKE NO dispara
con merma=0%, transición sin actor rechazada, secuencia completa de
transiciones válidas con actor, resolución sin motivo rechazada, salto
inválido rechazado, acción desconocida rechazada),
`test_alert_explorer_page.py` (5: construcción, listado real tras
`refresh()`, transición sin fila seleccionada (mensaje, no crash),
transición real actualiza la tabla, ruteo). **13 tests nuevos, todos
verdes** (96 en el paquete `business_intelligence` completo).

## Pendiente

- Los otros 14 `AlertType` esperan una fuente de métrica real.
- Sin persistencia de `AnalyticalAlert` — dedup/cooldown reales pero inertes.
- BI-29 construye Escenarios (what-if de precio/demanda/compras, BI-19).
