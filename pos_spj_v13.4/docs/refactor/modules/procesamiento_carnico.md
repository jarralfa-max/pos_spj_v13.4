# Módulo: Procesamiento cárnico (FASE 7)

Estado: **IMPLEMENTATION**

## Alcance

Ciclo de procesamiento cárnico/despiece: ejecución de recetas (subproducto /
combinación / producción) y lotes industriales (abrir → agregar salidas → cerrar)
con rendimiento y costeo.

## Ruta canónica (ya existente)

```
UI modulos/produccion.py (tab cárnico)
  → ExecuteMeatProductionUseCase (backend/application/use_cases/)
    → ProductionApplicationService (facade, core/services/)
      → GestionarProduccionUC (core/use_cases/produccion.py)   [lifecycle + EventBus]
      → ProductionEngine (core/production/production_engine.py)  [batch detail]
      → RecipeEngine (core/services/recipe_engine.py)           [recipe execution]
```

La UI **ya delega** al Use Case con `operation_id` y UUIDs; el command/DTO son
UUID-native. `ProductionApplicationService` es delegación pura (sin lógica).

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `core/use_cases/produccion.py` | limpio (usa `new_uuid`, `operation_id`) | ✅ |
| `ProductionEngine` | batch id = `new_uuid()`; sin `lastrowid` | ✅ |
| `ProductionEngine._generar_folio` | `MAX(SUBSTR(folio,-4))+1` → **folio**, no PK | ✅ (no es identidad) |
| `RecipeEngine.ejecutar_produccion` | **`producciones` AUTOINCREMENT + `last_insert_rowid()`** y `produccion_detalle` AUTOINCREMENT | 🔧 **corregido** → `new_uuid()` |

### Corrección aplicada
`recipe_engine.py`: `producciones.id` y `produccion_detalle.id` se acuñan con
`new_uuid()`; se eliminó `last_insert_rowid()`. Protección:
`tests/integration/test_recipe_engine_uuid_identity.py` (2 tests, esquema
post-corte TEXT). Sin regresiones (15 archivos de tests cárnicos: 0 fallos
nuevos, 2 tests antes rojos ahora pasan).

## Pendiente

- `ProductionApplicationService` y engines: type hints `int` en ids
  (`producto_origen_id: int`, `receta_id: int`, `produccion_id: int`, …) →
  cambiar a `str` por correctness (no son casts, no rompen runtime).
- **Deuda de fixtures pre-existente (no introducida aquí):** ~11 tests de
  producción/receta rojos por drift del costeo (`productos.costo`,
  `inventory_stock` ausentes en fixtures) + ids INTEGER. Modernizar fixtures a
  esquema post-corte para dejar el módulo verde.
- Checklist UI completo (SearchSelector ya usado; revisar números en 0,
  sin defaults arbitrarios, QueryService para lecturas del tab).
