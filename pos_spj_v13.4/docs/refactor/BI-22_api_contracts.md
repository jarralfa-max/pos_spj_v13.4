# BI-22 — API Contracts futuros

Estado: **DONE** (endpoints reales registrados en la app FastAPI ya
existente, respaldados por el pronóstico real de BI-11; recomendaciones/
alertas sirven listas vacías hasta que exista su persistencia — BI-18/20)

## Alcance

§56-59: preparar una capa API reutilizable por una futura app web, sin
implementar esa app web todavía; read-only por defecto (§59); auth
compartida, nunca un token estático (§58).

## Hallazgo que cambió el plan original

BI-22 se planeaba como una nueva carpeta `backend/api/analytics/` desde
cero. **`backend/api/` ya existe** — una app FastAPI real
(`backend/api/main.py::create_app()`), con `routers/`+`schemas/` (ya sirve
2 PWAs móviles de Compras/Logística y Pedidos/Delivery,
`mobile_logistics.py`/`driver_logistics.py`) y una sesión firmada
compartida (`backend/api/mobile_session.py::MobileSessionTokenService`/
`mobile_identity`). Se siguió esa convención real en vez de inventar una
estructura paralela — mismo criterio aplicado en toda esta transformación
(p. ej. BI-8 con `infrastructure/db/repositories/<contexto>/`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/analytics/integrations/serializers.py` | 3 funciones puras `ForecastRun+ForecastResult`/`BusinessRecommendation`/`AnalyticalAlert` → `dict` JSON-seguro. `Decimal` serializa como **string** (nunca `float` — mismo criterio de precisión que `DecimalText` ya usa en requests, `backend/api/schemas/mobile_common.py`), enums a `.value`, fechas a ISO 8601. |
| `backend/application/analytics/integrations/analytics_api_workflow.py` | `AnalyticsApiWorkflow` — mismo molde que `OrdersDeliveryDriverWorkflow` (ORD-25): recibe la identidad del llamador primero, devuelve `dict`s listos. Los métodos de forecast usan el `ForecastRunRepositoryPort` **real** (BI-11, persistencia SQLite genuina); recomendaciones/alertas usan puertos `RecommendationProvider`/`AlertProvider` simples porque `BusinessRecommendation`/`AnalyticalAlert` (BI-18/BI-20) no tienen persistencia todavía — documentado ahí, no oculto aquí. |
| `backend/api/routers/analytics.py` | 4 endpoints GET: `/bi/forecasts/{series_key}`, `/bi/forecasts/{series_key}/{run_id}`, `/bi/recommendations`, `/bi/alerts`. Reutiliza `Depends(mobile_identity)` (la MISMA sesión firmada de cualquier otro router — §58, nunca un mecanismo de auth propio) + una verificación de permiso explícita contra `AnalyticsPermissions` (BI-2) antes de cada lectura. Sin ningún endpoint de mutación — §59, read-only por defecto. |
| `backend/api/main.py` (ampliado) | Registra `analytics_router` bajo el mismo prefijo `/api` que los routers móviles existentes. |

## Por qué "servir listas vacías" para recomendaciones/alertas, no fallar

`AnalyticsApiWorkflow` no tiene forma de mentir sobre datos que no existen
todavía — `BusinessRecommendation`/`AnalyticalAlert` viven solo en memoria
(BI-18/20 lo documentaron explícitamente). En vez de no exponer el
endpoint, o inventar datos falsos, los `Provider` ports simplemente
devuelven lo que tengan (vacío hoy, real cuando exista persistencia) — el
contrato de la API (forma de la respuesta, autenticación, permisos, scope
por sucursal) queda fijo y probado desde ahora, sin esperar a que exista el
backend completo detrás.

## Validación end-to-end real

`tests/integration/test_analytics_api.py` usa un `TestClient` de FastAPI
real contra la app real (`create_app()`), con
`SqliteForecastRunRepository` (BI-11) sembrando una corrida real en SQLite
— no hay ningún mock del pronóstico, es el mismo repositorio que ya usa el
resto del pipeline. Verifica: 401 sin autenticar, 503 si el workflow no está
configurado (mismo patrón que ya usa `driver_logistics.py` sin wiring de
producción), 403 sin el permiso `INTELIGENCIA_BI.forecast.ver`, y 200 con
el resultado exacto sembrado.

## Auditoría REGLA CERO

Los serializadores no generan identidad; todos los ids que aparecen ya
fueron validados en su bounded context de origen. N/A.

## Tests

`test_serializers.py` (3), `test_analytics_api_workflow.py` (4, con fakes
para los 3 puertos), `test_analytics_api.py` (6, FastAPI `TestClient` real
+ SQLite real). **13 tests nuevos, todos verdes** — más los 17 tests
preexistentes de `tests/integration/logistics/` reconfirmados verdes tras
registrar el router nuevo en `main.py`.

## Pendiente

- `RecommendationProvider`/`AlertProvider` no tienen implementación de
  infraestructura real — se construyen cuando `BusinessRecommendation`/
  `AnalyticalAlert` tengan persistencia (fase futura, no en el alcance de
  BI-18/20).
- Sin endpoints de charts/kpis/scenarios dedicados (§57 los menciona) — el
  dashboard ejecutivo (`BiDashboardService`, ya movido en BI-4) y los
  what-ifs (BI-19) no tienen todavía un caller de producción que justifique
  exponerlos por API; se agregan cuando lo tengan.
- Sin rate limiting explícito (§58) — hereda lo que la app FastAPI
  compartida ya tenga configurado (ninguno todavía, mismo estado que
  `driver_logistics`/`mobile_logistics`).
