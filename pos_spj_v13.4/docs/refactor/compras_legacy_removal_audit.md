# Auditoría de Legacy — compras_pro.py
_Generado: 2026-05-17 | v13.4 | Fase 0_

## Resumen ejecutivo

`modulos/compras_pro.py` contiene **3 393 líneas** y **92 métodos** dentro de
`ModuloComprasPro`.  El módulo mezcla presentación, lógica de negocio y acceso
a datos directamente, violando la arquitectura objetivo del ERP.

---

## 1. SQL directo en UI (violación de arquitectura)

| Línea | Método | Descripción |
|-------|--------|-------------|
| 1276 | `_cargar_info_proveedor` | SELECT a tabla `proveedores` |
| 1407 | `_cargar_recientes_proveedor` | SELECT a `compras` |
| 1455 | `_abrir_reciente_sidebar` | SELECT a `detalles_compra` |
| 1481 | `_cargar_alertas_cxp` | SELECT a `cuentas_por_pagar` |
| 1506 | `_cargar_plantillas_sidebar` | SELECT a `plantillas_compra` |
| 1601 | `_cargar_sucursales_compra` | SELECT a `sucursales` |
| 1624 | (provider search init) | SELECT a `proveedores` |
| 2259 | `_procesar_compra` | (inner) SELECT saldo proveedor |
| 2407 | `_detectar_recetas` | SELECT a `product_recipes` |
| 2440 | `_procesar_recetas` | SELECT a `product_recipes` |
| 2451 | `_procesar_recetas` | SELECT a `product_recipe_items` |
| 2472 | `_procesar_recetas` | UPDATE `kardex_production` |
| 3366–3392 | `_fallback_compra_directa` | INSERT compras + UPDATE inventario (**MUERTO**) |

**Total: 13 llamadas SQL directas** en capa UI (sin contar la función muerta).

---

## 2. Widgets con estado oculto / lógica interna

Ningún widget se oculta como hack de compatibilidad.  Los tres tabs son visibles
y funcionales.  Sin embargo, la `_build_provider_sidebar` construye UI dinámica
con lógica de negocio embebida (carga alertas CxP, recientes, plantillas, etc.)
que debe moverse a `application/`.

---

## 3. Estilos hardcodeados (prohibidos por reglas del proyecto)

| Línea | Fragmento prohibido |
|-------|---------------------|
| 918 | `background:white;font-size:11px;` |
| 924 | `background:#F8FAFC;` (QListWidget hover) |
| 1080 | `color:white;` (chip info) |
| 1351 | `color:white;` (botón primary) |
| 2371 | `color:#fff;` (header tabla HTML) |
| 3301 | `color:#fff;` (header tabla HTML historial) |
| 891 | `Colors.NEUTRAL.SLATE_50` como fondo sidebar |
| 2756 | `Colors.NEUTRAL.SLATE_50` como fondo card |
| 3274 | `Colors.NEUTRAL.SLATE_50` fila par en historial |

Colores vía `Colors.*` están permitidos; strings crudos `background:white` y
`#F8FAFC` / `#fff` están prohibidos.

---

## 4. Métodos sin use-case (lógica de negocio en UI)

Los siguientes métodos contienen reglas de negocio que pertenecen a `application/`:

- `_detectar_recetas` — lógica de qué productos tienen receta
- `_procesar_recetas` — aplica consumo de ingredientes (escribe kardex)
- `_cargar_alertas_cxp` — decide si mostrar alertas de saldo vencido
- `_on_condicion_changed` / `_on_plazo_changed` — calcula fecha vencimiento

---

## 5. Código muerto

| Método | Línea | Razón |
|--------|-------|-------|
| `_fallback_compra_directa` | 3353–3393 | Nunca llamado; 0 referencias en el archivo |

Este método contiene `UPDATE productos SET existencia=existencia+?` — modificación
directa de inventario desde UI, violando dos reglas a la vez (SQL en UI +
inventario fuera de `RegistrarCompraUC`).

---

## 6. Dependencias externas directas en UI

- `from core.db.connection import transaction` — importado dentro de `_fallback_compra_directa` (código muerto)
- `QThread` / `QRunnable` para carga asíncrona de historial — aceptable
- `QCompleter` — OK pero `setCompletionMode(InlineCompletion)` ya corregido

---

## 7. Estado de arquitectura por capa

| Capa | Estado |
|------|--------|
| Domain (`domain/`) | ❌ No existe para compras |
| Application (`application/purchases/`) | ✅ `PurchaseRequestUC` presente; `RegistrarCompraUC` en `use_cases/` |
| Repository (`repositories/`) | ✅ `PurchaseRequestRepository` presente |
| UI (`modulos/compras_pro.py`) | ⚠️ 13 SQL directos + 1 método muerto peligroso |

---

## 8. Prioridad de limpieza

1. **INMEDIATO** — Eliminar `_fallback_compra_directa` (muerto + peligroso)
2. **FASE 2** — Extraer `_cargar_info_proveedor`, `_cargar_recientes_proveedor`, `_cargar_alertas_cxp` a `ProveedorRepository`
3. **FASE 2** — Extraer `_detectar_recetas` + `_procesar_recetas` a `RecetasUC`
4. **FASE 3** — Extraer `_cargar_sucursales_compra` a `SucursalRepository`
5. **FASE 4** — Reemplazar hardcoded CSS con tokens de diseño
