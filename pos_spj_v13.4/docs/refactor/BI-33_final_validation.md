# BI-33 — Validación final

Estado: **DONE**. Última fase del roadmap BI-0..BI-33; cierra la
transformación de Business Intelligence / Analytics / Forecasting /
Decision Intelligence / Scenario Planning / Alerting de pos_spj_v13.4.

## Resultado global

- **BI-0..BI-32: todos DONE.** 33 fases (34 documentos, incluyendo esta).
- **593/593 tests verdes** en la suite curada completa (BI-1..32 + los
  archivos de scaffolding/legacy tocados en BI-32), **cero regresiones**.
- **Cero errores de sintaxis** en todo el repositorio (`ast.parse` sobre
  cada `.py`, verificado al cierre de esta fase).
- Backend completo y real: `ForecastingPlatform` (BI-7..12), 5 tipos de
  recomendación (BI-13..17), Decision Intelligence + Scenario Planning +
  Alerting (BI-18..20), notificaciones + API + primera UI (BI-21..24), 10
  páginas reales de UI (BI-24..30) sobre 13 secciones de navegación.
- El módulo nuevo (`frontend/desktop/modules/business_intelligence/`)
  **sigue sin estar cableado a `interfaz/main_window.py`** — decisión
  deliberada de BI-23, protegida por guardrail
  (`test_module_not_yet_wired_into_main_window`). El botón
  `"INTELIGENCIA_BI"` sigue apuntando a `modulos/reportes_bi_v2.py` (la
  única ruta de producción hasta que exista una decisión explícita de
  corte).

## Checklist obligatorio por módulo (skill de refactor)

| Punto | Estado | Evidencia |
|---|---|---|
| Backend en inglés | ✅ | Todo `backend/{domain,application,infrastructure}/{analytics,forecasting,decision_intelligence,scenario_planning}` en inglés desde BI-1. |
| UI en español | ✅ | Todos los textos visibles (títulos, subtítulos, botones, mensajes) en español en las 10 páginas nuevas. |
| Sin SQL en UI | ✅ | Guardrail `test_pages_do_not_access_database_or_repositories` (BI-23) escanea todo `frontend/desktop/modules/business_intelligence/` — verde. |
| Sin commit/rollback en UI | ✅ | Mismo guardrail (`.commit(` prohibido). |
| Sin schema changes fuera de migrations | ✅ | Ninguna fase BI tocó `migrations/` salvo BI-11 (migración `254_forecasting_schema.py`, la única con persistencia nueva real). |
| Sin `AppContainer` completo en servicios | ✅ | Cada presenter recibe una `connection` cruda o un servicio ya construido — nunca un contenedor. |
| Sin listas largas para entidades | ✅ | `ProductSearchBox`/`BranchSearchBox` (BI-26/27/29) en vez de combos de cientos de filas. |
| Usa `SearchSelector` donde aplica | ✅ | BI-26/27/29 — ver también la brecha documentada de altura táctil en BI-31 (`SearchSelector`, fuera del alcance de este módulo). |
| Campos numéricos en 0 o vacío | ✅ | `IntegerInput`/`NumericInput`/`PercentInput` arrancan en 0 por construcción; ningún valor por defecto hardcodeado arbitrario (BI-26 horizonte y BI-27 umbral de margen vienen de `BiSettingsService`, no de literales). |
| Usa QueryService para lecturas | ✅ | Todas las 10 páginas reales delegan a `Bi*QueryService`/servicios de aplicación reales. |
| Usa UseCase/ApplicationService para mutaciones | ⚠️ Parcial | Las transiciones de ciclo de vida (BI-27/28) llaman funciones puras de dominio directamente desde el presenter — no hay una capa `UseCase` intermedia todavía porque no hay persistencia que orquestar (documentado, no una omisión). |
| Emite eventos con `operation_id` | ❌ No aplica todavía | Sin persistencia de `BusinessRecommendation`/`AnalyticalAlert`, no hay mutación real que emitir como evento — brecha honesta documentada desde BI-22. |
| Compatible con SQLite/PostgreSQL | ✅ | Sin SQL específico de SQLite nuevo (BI-11's schema usa tipos portables). |
| Preparado para API futura | ✅ | BI-22 ya expone 4 endpoints reales sobre `backend/api/` existente. |
| Tests unitarios/integración/arquitectura | ✅ | 593 tests, incl. 6 guardrails de arquitectura específicos de BI. |
| Validación manual documentada | ⚠️ Parcial | Cada fase documentó verificación vía tests reales contra SQLite (no mocks) — sin checklist manual de un humano operando la UI, ya que el módulo no está cableado a producción todavía. |
| Código legacy eliminado | ⚠️ Parcial | 2 de 4 candidatos reales eliminados (BI-32); los otros 2 corrigen la auditoría original con evidencia concreta de por qué NO deben eliminarse todavía. |
| Todas las entidades usan UUIDv7 | ✅ | Auditoría REGLA CERO en cada fase — cero excepciones nuevas introducidas. |
| Sin PK `INTEGER AUTOINCREMENT` nueva | ✅ | La única tabla nueva (`forecast_*`, BI-11) usa `TEXT PRIMARY KEY`. |
| Sin `lastrowid` para identidad | ✅ | N/A — nada de esta transformación usa `lastrowid`. |
| Sin casts `int(..._id)` | ✅ | Confirmado en cada fase. |

## Brechas honestas consolidadas (no fabricadas, documentadas fase por fase)

1. **Producción/Precios/Sucursales** (secciones de nav) sin página propia —
   BI-14/15/17 solo calculan por producto/sucursal individual, no hay
   agregado tipo dashboard (BI-25).
2. **Purchase/Production/Branch recommendations** sin UI — mismo motivo
   (BI-27).
3. **Inventory what-if** sin UI — mismo motivo (BI-29).
4. **14 de 16 `AlertType`** sin regla wireada — necesitan fuentes de métrica
   que hoy son listas, no escalares (BI-28).
5. **Reportes programados** — sin infraestructura de scheduler en todo el
   repo (BI-30).
6. **Sin persistencia** de `BusinessRecommendation`/`AnalyticalAlert` — cada
   generación/transición vive solo en memoria de la página (BI-22/27/28).
7. **`repositories/bi_repository.py`/`core/services/forecast_service.py`**
   siguen existiendo — huérfanos de producción pero con tests reales que
   requieren migración explícita antes de retirarlos (BI-32).
8. **El módulo nuevo no está cableado a `main_window.py`** — coexiste con
   `modulos/reportes_bi_v2.py` hasta una decisión explícita de corte
   (BI-23).
9. **`SearchSelector`** (componente compartido, no exclusivo de BI) no fija
   altura táctil mínima — hallazgo real, fuera del alcance de esta
   transformación (BI-31).

## Recomendación para la siguiente sesión

Ninguna de las 9 brechas de arriba bloquea el uso del módulo tal como está
— todas son extensiones incrementales o decisiones de corte que requieren
juicio de negocio, no código faltante crítico. Las tres acciones de mayor
valor si se retoma este trabajo, en orden sugerido:

1. **Decisión de corte**: reemplazar `_conectar("INTELIGENCIA_BI", ...)` en
   `main_window.py`/`menu_lateral.py` por el módulo nuevo — requiere
   aceptar que Producción/Precios/Sucursales/9 de 12 secciones originales
   quedan con menos profundidad que `reportes_bi_v2.py` por ahora.
2. **Persistencia de `BusinessRecommendation`/`AnalyticalAlert`** —
   desbloquea historial real, dedup/cooldown funcional (BI-20 ya lo
   implementa, solo falta el repositorio), y endpoints de API no-vacíos
   (BI-22).
3. **Migrar `bi_repository.py`/`forecast_service.py`** — trabajo acotado y
   ya identificado con precisión en BI-32, no una investigación nueva.

## Auditoría REGLA CERO

Confirmada limpia en las 33 fases — cero IDs enteros nuevos, cero
`AUTOINCREMENT` nuevo, cero `legacy_id`, cero conversión `int(..._id)`.

## Tests

593/593 verdes (suite curada BI-1..32 completa), 0 fallos, 0 errores de
sintaxis en todo el repositorio.
