# ORD-27 — Analytics: KPI / Charts / SLA / Driver performance

Fecha: 2026-09-01. Alcance: master prompt ORD-27 ("1. KPI. 2. Charts. 3. SLA.
4. Driver performance. 5. Tests.").

## Qué se construyó

- `backend/application/orders_delivery/queries/analytics_query_service.py` —
  `OrdersDeliveryAnalyticsQueryService`, un read-model puro sobre las tablas ya
  construidas (`customer_orders`/`delivery_jobs`/`driver_cash_collections`), sin ninguna
  mutación de dominio nueva:
  - `kpi_summary(branch_id, date_from, date_to)` — pedidos creados/completados/
    cancelados/reversados e ingreso total (solo de pedidos `COMPLETED`).
  - `sla_breakdown(...)` — tasa a tiempo entre entregas `DELIVERED`/`CLOSED` que
    tenían una ventana prometida (`scheduled_window_end`); una entrega sin ventana
    prometida se EXCLUYE del denominador en vez de contarse silenciosamente como éxito
    o falla.
  - `driver_performance(...)` — por repartidor: entregas completadas/fallidas, minutos
    promedio de despacho a entrega, y exactitud de cobro (`cash_variance` =
    cobrado - esperado, vía `driver_cash_collections`).
  - Toda suma de dinero/duración se hace en **Python con `Decimal`**, nunca con
    `SUM()`/`AVG()` de SQL sobre las columnas TEXT-decimal — SQLite convierte esas
    columnas a REAL (float) al agregarlas, justo lo que REGLA CERO prohíbe.
  - Defensivo como `OrdersDeliveryBadgeQueryService` (ORD-4): un esquema faltante o
    antiguo degrada a resultados vacíos/cero, nunca lanza hacia un dashboard.

## Hallazgo y corrección: dos placeholders obsoletos en el badge service de ORD-4

`OrdersDeliveryBadgeQueryService.get_badge_counts()` (ORD-4) tenía
`"settlements_pending_review": 0` y `"critical_alerts": 0` con comentarios explícitos
`# ORD-21: no settlement table yet` / `# ORD-26: no alerts source yet` — ambas fases YA
se construyeron en esta misma sesión (`driver_settlements` en ORD-21, `notification_inbox`
con `tipo='entrega_fallida'` en ORD-26), así que los placeholders quedaron obsoletos y
silenciosamente incorrectos (el badge del sidebar nunca mostraría liquidaciones
pendientes de revisión ni alertas críticas reales, aunque los datos ya existieran).
Corregido con las mismas consultas defensivas (`_safe_count`) que el resto del servicio
ya usa. 2 tests nuevos confirman que ahora cuentan valores reales, no solo que no
truenan.

## "2. Charts" deliberadamente NO construido

Este servicio devuelve exactamente los datos estructurados que un gráfico necesitaría
(series con etiquetas, no una imagen) — pero dibujar un widget de gráfico PyQt5 real es
tarea de frontend, fuera de lo que un servicio de consulta de backend puede entregar
honestamente. Mismo criterio de "backend real, frontend señalado como pendiente" que
ORD-25 (PWA) ya usó para el mismo tipo de límite.

## Decisiones

- **Sin verificación de permiso dentro del servicio** — mismo patrón que
  `OrdersDeliveryBadgeQueryService` (ORD-4): los query services de este bounded context
  no revalidan `ANALYTICS_VIEW` internamente, es responsabilidad de quien lo invoque
  (UI/API) verificarlo antes de llamar, igual que cualquier otro query service existente.
- **Ingreso solo de pedidos `COMPLETED`** — un pedido cancelado o reversado nunca fue
  ingreso realmente realizado.
- **SLA excluye, no asume** — una entrega sin ventana prometida no tiene SLA que medir;
  incluirla como éxito infla la métrica, incluirla como falla castiga entregas que nunca
  prometieron un horario.

## Tests

9 tests nuevos: 7 de `OrdersDeliveryAnalyticsQueryService` (KPI, SLA, rendimiento por
repartidor, degradación en esquema faltante) + 2 que cierran el gap de badges obsoletos.
Suite combinada `orders_delivery` + `logistics`: **403/403 pasando**.

## Pendiente

- Widgets de gráficos reales en el frontend PyQt5 (ver arriba).
- ORD-28 (UI/UX: Sidebar/Páginas/Diálogos/Tema JUANIS/Responsive/Accesibilidad) — este sí
  es trabajo genuino de frontend PyQt5 de escritorio, distinto de la PWA web de ORD-25.
