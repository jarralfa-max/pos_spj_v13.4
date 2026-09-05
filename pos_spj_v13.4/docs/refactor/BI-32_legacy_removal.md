# BI-32 — Legacy Removal

Estado: **DONE** — 2 de los 4 candidatos originales de BI-0 confirmados y
eliminados; los otros 2 **corrigen** la clasificación de BI-0 con evidencia
fresca y se dejan intencionalmente intactos (ver justificación detallada)

## Alcance

§14 (aprox.): retirar los candidatos `DELETE` identificados en BI-0
(motores paralelos, `bi_service.py`, `bi_repository.py`) una vez confirmado
que no tienen consumidores reales.

## Metodología: no confiar en la auditoría vieja sin re-verificar

BI-0 (2026-09-04/05) clasificó 4 archivos como candidatos de eliminación.
Antes de tocar cualquiera, esta fase volvió a buscar **en el repo actual**
(no en la memoria de la auditoría) cada uno de los 4, porque el estado del
repo cambia entre sesiones. El resultado corrigió BI-0 en 2 de los 4 casos.

## Los 4 candidatos, con su estado real verificado hoy

| Archivo | Clasificación BI-0 | Verificación real (esta fase) | Acción |
|---|---|---|---|
| `backend/application/queries/business_intelligence_query_service.py` | `DELETE` candidato, verificar consumidores | Confirmado: cero consumidores reales. Solo 2 tests genéricos de scaffolding (`test_phase0_phase1_scaffolding.py` verifica que el archivo existe; `test_phase5_query_services.py` verifica que `.scope` coincide con un patrón genérico compartido por ~8 clases scaffold similares) — ninguno ejercita lógica de negocio real de BI. | **ELIMINADO.** Editados ambos tests para quitar solo la referencia a esta clase (sin tocar la cobertura de las otras ~8 clases del mismo archivo, que no son parte de esta transformación). |
| `core/services/bi_service.py` | `DELETE` (ya deprecado) | Confirmado: `app_container.py` tiene `self.bi_service = None` con el comentario explícito "BI unificado: no se expone bi_service paralelo". Su único referente, `tests/test_fase2_bi_cajeros.py`, ya tenía sus imports comentados con la nota `# ELIMINADO en v13.4` — **ejecutado, ese archivo de test ya fallaba 13/13 con `NameError`** antes de tocar nada (no es una regresión de esta fase; ya estaba roto). | **ELIMINADO**, junto con el archivo de test ya-roto que lo refería. |
| `repositories/bi_repository.py` | `DELETE` (ya deprecado) | **BI-0 estaba parcialmente equivocado.** `modulos/reportes_bi_v2.py` hoy **no** llama a `BIRepository` (BI-4 ya reemplazó ese camino), y `core/app_container.py` tiene **tres** comentarios independientes (líneas 16, 111, y el docstring de `AnalyticsEngine.get_dashboard_data`) declarando la intención de retirarlo. Pero existe un test real, limpio y **actualmente verde** (`tests/test_bi_reportes_service_reads.py`, 4/4 pasan) que ejercita `BIRepository.get_kpis_dia()` directamente. Verificando cada valor que calcula: `clientes` (clientes únicos del día) **sí** tiene reemplazo real y en vivo — `AnalyticsEngine._get_kpis_generales()` ya calcula `COUNT(DISTINCT cliente_id)`, confirmando que esa parte de la migración se completó. Pero `costo` (costo de ventas del día, vía join `detalles_venta`→`product_cost`, usado para el margen) **no** tiene un reemplazo consolidado en una sola llamada ya existente — `BiSalesQueryService.cost_of_goods(f)` (BI-4) calcula el valor equivalente para cualquier rango de fechas incluido "hoy", pero nadie ha compuesto todavía esa llamada + `AnalyticsEngine` en un reemplazo directo de `get_kpis_dia()`, ni existe un test que confirme esa composición. | **NO eliminado.** Corrección explícita a BI-0 (parcial: la métrica de clientes únicos sí está migrada; el costo del día no está consolidado en un reemplazo probado). Queda como trabajo futuro real y acotado: escribir la composición (`AnalyticsEngine` + `BiSalesQueryService.cost_of_goods`) con su propio test antes de retirar este archivo — no es un caso de "posiblemente perdido", es una migración concreta de una tarde, simplemente no hecha todavía. |
| `core/services/forecast_service.py` | `DELETE` candidato ("huérfano de producción, solo tests") | **BI-0 subestimó el riesgo.** Confirmado sin wiring en `app_container.py` (huérfano de producción, eso sí es cierto) — pero tiene **4 archivos de test reales y aprobados** que ejercitan comportamiento específico y no trivial: publicación del evento `FORECAST_GENERADO`, degradación correcta cuando falta `statsmodels`, y ejecución de `generar_plan_compras` con IDs UUID. "Solo referenciado en tests" no es lo mismo que "sin lógica de negocio validada" — son tests reales protegiendo comportamiento real, no scaffolding genérico. | **NO eliminado.** Corrección explícita a BI-0. Retirarlo requeriría primero migrar la intención de esos 4 tests al `ForecastingPlatform` canónico (BI-7..12) — Holt-Winters ya está portado a `baseline_models.py` (BI-9), pero la degradación sin `statsmodels` y la publicación de eventos no tienen un equivalente confirmado todavía. |

## Componentes tocados

| Archivo | Cambio |
|---|---|
| `backend/application/queries/business_intelligence_query_service.py` | **Eliminado.** |
| `backend/application/queries/__init__.py` | Quitados el import y la entrada de `__all__`. |
| `tests/integration/test_phase0_phase1_scaffolding.py` | Quitada la línea de existencia de archivo para la clase eliminada. |
| `tests/unit/test_phase5_query_services.py` | Quitados el import y la entrada de `expected_scopes`; las ~8 clases restantes del mismo test quedan intactas. |
| `core/services/bi_service.py` | **Eliminado.** |
| `tests/test_fase2_bi_cajeros.py` | **Eliminado** (ya fallaba 13/13, `NameError`, auto-documentado como "ELIMINADO en v13.4" pero nunca completado). |

## Lo que NO se tocó (y por qué es la decisión correcta)

- **Los 3 motores de forecast paralelos en vivo** (`AnalyticsEngine`,
  `ActionableForecastService`→`DemandForecastEngine`,
  `DemandForecastingEngine` como `container.forecast_engine`) — siguen
  siendo la única ruta de producción hasta que exista un corte de UI real
  (BI-23 ya documentó esta decisión explícitamente; no es de esta fase
  revertirla).
- `repositories/bi_repository.py` y `core/services/forecast_service.py` —
  ver tabla arriba.
- `modulos/reportes_bi_v2.py` — sigue siendo la única UI BI en producción;
  BI-23..30 construyeron un módulo nuevo paralelo, no un reemplazo todavía.

## Auditoría REGLA CERO

N/A — solo eliminación de archivos ya huérfanos de producción, sin tocar
identidad ni datos.

## Tests

Después de los cambios: `test_phase5_query_services.py` (3, incl. las ~8
clases scaffold restantes), `test_phase0_phase1_scaffolding.py`,
`test_bi_reportes_service_reads.py` (4, confirmando `BIRepository` sigue
íntegro y verde) — **todos verdes**. Suite curada completa de BI-1..31
(559+ tests previos) re-ejecutada sin regresiones. Sintaxis global limpia
(`ast.parse` en todo el repo).

## Pendiente

- Portar "clientes únicos del día" a un `Bi*QueryService` canónico antes de
  poder retirar `bi_repository.py`.
- Migrar la intención de los 4 tests de `forecast_service.py` (evento
  `FORECAST_GENERADO`, degradación sin `statsmodels`, `generar_plan_compras`
  con UUID) al `ForecastingPlatform` canónico antes de poder retirarlo.
- BI-33 corre la validación final contra el checklist del prompt maestro.
