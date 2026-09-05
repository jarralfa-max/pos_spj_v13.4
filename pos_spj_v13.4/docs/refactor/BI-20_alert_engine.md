# BI-20 — Alert Engine (lifecycle, dedupe, cooldown)

Estado: **DONE** (motor de umbrales genérico + ciclo de vida + dedup
completos; sin wiring a métricas reales de producción todavía)

## Alcance

§46-51: `AnalyticalAlertRule`/`AnalyticalAlert`, 16 tipos (§47), severidad
configurable por regla (§48, nunca hardcodeada), deduplicación por
fingerprint + cooldown (§49), ciclo de vida OPEN→ACKNOWLEDGED→IN_PROGRESS→
RESOLVED/DISMISSED/EXPIRED con `acknowledged_by`/`resolved_by`/`reason`/
timestamps (§50). Nuevo bounded context `backend/domain/analytical_alerting/`
(§7), separado de `decision_intelligence` (§46: "No mezclar alerta con
recomendación").

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/analytical_alerting/enums.py` | `AlertType` (16 de §47), `AlertSeverity` (5 de §48), `AlertStatus` (6 de §50), `Comparison` (GT/GTE/LT/LTE). |
| `backend/domain/analytical_alerting/value_objects/alert_rule.py` | `AnalyticalAlertRule` — `metric_key`+`comparison`+`threshold`+`severity`+`cooldown_minutes`+`enabled`. `is_breached(metric_value)` evalúa la comparación configurada. |
| `backend/domain/analytical_alerting/value_objects/alert.py` | `AnalyticalAlert` — invariantes: `acknowledged_by`/`acknowledged_at` deben coexistir; `resolved_by`/`resolved_at`/`reason` deben coexistir; `RESOLVED`/`DISMISSED` exigen los 3; `EXPIRED` no los exige (una expiración la nota un scheduler, no una decisión humana). |
| `backend/domain/analytical_alerting/services/fingerprint.py` | `build_fingerprint(alert_type, branch_id, target_id)` — clave compuesta legible (no hash criptográfico; la trazabilidad para depurar una decisión de dedup importa más que el ofuscamiento). |
| `backend/domain/analytical_alerting/services/alert_lifecycle.py` | `acknowledge`/`start_progress`/`resolve`/`dismiss`/`expire` — mismo patrón de reemplazo inmutable que `decision_intelligence.recommendation_transitions` (BI-18): cada función devuelve una instancia nueva, nunca muta in-place. `dismiss` es alcanzable directo desde `OPEN` (no obliga a reconocer antes de descartar un falso positivo). |
| `backend/domain/analytical_alerting/services/alert_deduplication.py` | `should_suppress(existing_alerts, fingerprint, cooldown_minutes, now)` — suprime si existe **cualquier** alerta (resuelta o no) con el mismo fingerprint creada dentro de la ventana de cooldown; `cooldown_minutes<=0` nunca suprime. |
| `backend/application/analytical_alerting/services/alert_engine.py` | `AnalyticalAlertEngine.evaluate()` — orquesta: regla deshabilitada → `None`; no rebasa umbral → `None`; rebasa pero está en cooldown → `None`; en otro caso crea la `AnalyticalAlert` en estado `OPEN`. No calcula métricas — recibe `metric_value` ya calculado por quien sea (BI-13..17, u otra query analítica). |

## Por qué un motor de umbrales genérico y no 16 evaluadores especializados

Los 16 `AlertType` de §47 comparten la misma forma: "¿un valor cruza un
umbral configurado?" — `STOCKOUT_RISK` sobre `stockout_probability`,
`MARGIN_DROP` sobre `expected_margin_change_pct`, `MODEL_DEGRADATION` sobre
`wape`, etc. Un solo `AnalyticalAlertRule`+`AnalyticalAlertEngine` genérico
cubre los 16 sin código repetido; lo que cambia entre tipos es solo qué
`metric_key`/`comparison`/`threshold`/`severity` trae la regla configurada,
no la lógica de evaluación.

## Auditoría REGLA CERO

`AnalyticalAlertRule.id`/`AnalyticalAlert.id`/`.rule_id` validados con
`validate_uuidv7()`. N/A para el resto.

## Tests

`test_alert_rule.py` (9, las 4 comparaciones + validaciones),
`test_alert.py` (7, invariantes de consistencia), `test_fingerprint.py` (4),
`test_alert_lifecycle.py` (7, camino feliz completo + inmutabilidad +
terminal states + dismiss sin reconocer primero), `test_alert_deduplication.py`
(5, dentro/fuera de cooldown, fingerprint distinto, cooldown=0),
`test_alert_engine.py` (5, breach/no-breach/disabled/suppressed/re-fires
tras cooldown). **40 tests nuevos** (2 requirieron corregir el fixture del
test, no el código de dominio — la propia validación de `AnalyticalAlert`
atrapó un `_make()` de prueba incompleto). **Suite acumulada BI-1..BI-20:
368/368 verdes**, cero regresiones, cero errores de sintaxis en todo el
repo.

## Pendiente

- Ningún caller real todavía alimenta `AnalyticalAlertEngine` con métricas
  de producción (`stockout_probability` de BI-13, `wape` de BI-10, etc.) —
  eso es wiring de BI-21 (Integración de Notificaciones) o de una fase de
  Use Case/scheduler futura.
- Sin persistencia de `AnalyticalAlertRule`/`AnalyticalAlert` — viven en
  memoria, mismo criterio que `BusinessRecommendation` (BI-18): se
  construye cuando exista un caller real.
- Sin integración con Notification Management/WhatsApp (§51-55) — eso es
  BI-21, deliberadamente fuera de esta fase.
