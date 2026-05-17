# Código a Eliminar — compras_pro.py
_Generado: 2026-05-17 | v13.4 | Fase 0_

## ELIMINACIÓN INMEDIATA (FASE 1)

### `_fallback_compra_directa` — líneas 3353–3393

**Razón**: Código muerto (0 llamadas), contiene SQL directo modificando inventario.

```python
# ELIMINAR COMPLETO — nunca es llamado
def _fallback_compra_directa(self, proveedor_id, doc_ref, pago, total, items) -> str:
    ...
    db.execute("UPDATE productos SET existencia=existencia+?, precio_compra=? WHERE id=?", ...)
```

**Acción**: Borrar las 41 líneas (3353–3393).

---

## LIMPIEZA DE ESTILOS (FASE 2)

### CSS hardcodeado a reemplazar con tokens

| Línea | Antes | Después |
|-------|-------|---------|
| 918 | `background:white;` | `background:{Colors.NEUTRAL.WHITE};` |
| 924 | `background:#F8FAFC;` | `background:{Colors.NEUTRAL.SLATE_50};` |
| 1080 | `color:white;` | `color:{Colors.NEUTRAL.WHITE};` |
| 1351 | `color:white;` | `color:{Colors.NEUTRAL.WHITE};` |
| 2371 | `color:#fff;` | `color:{Colors.NEUTRAL.WHITE};` |
| 3301 | `color:#fff;` | `color:{Colors.NEUTRAL.WHITE};` |

---

## EXTRACCIÓN A REPOSITORIO (FASE 2)

### SQL directo a mover a `ProveedorRepository`

| Método | Línea | Query |
|--------|-------|-------|
| `_cargar_info_proveedor` | 1276 | `SELECT * FROM proveedores WHERE id=?` |
| `_cargar_recientes_proveedor` | 1407 | `SELECT ... FROM compras WHERE proveedor_id=?` |
| `_abrir_reciente_sidebar` | 1455 | `SELECT ... FROM detalles_compra WHERE compra_id=?` |
| `_cargar_alertas_cxp` | 1481 | `SELECT saldo_pendiente FROM cuentas_por_pagar WHERE proveedor_id=?` |
| `_cargar_plantillas_sidebar` | 1506 | `SELECT * FROM plantillas_compra WHERE ...` |
| `_cargar_sucursales_compra` | 1601 | `SELECT id, nombre FROM sucursales` |

### SQL directo a mover a `RecetasRepository` / `RecetasUC`

| Método | Línea | Query |
|--------|-------|-------|
| `_detectar_recetas` | 2407 | `SELECT ... FROM product_recipes` |
| `_procesar_recetas` | 2440–2451 | `SELECT ... FROM product_recipe_items` |
| `_procesar_recetas` | 2472 | `UPDATE kardex_production ...` |

---

## EXTRACCIÓN DE LÓGICA DE NEGOCIO (FASE 3)

### Lógica de negocio embebida en UI que necesita use-case

| Método | Lógica a extraer | Destino |
|--------|-----------------|---------|
| `_on_condicion_changed` | Calcula fecha vencimiento según condición | `CompraUC.calcular_vencimiento()` |
| `_on_plazo_changed` | Recalcula fecha límite de pago | `CompraUC.calcular_vencimiento()` |
| `_detectar_recetas` | Determina qué productos tienen receta | `RecetasDomainService` |
| `_procesar_recetas` | Aplica consumo de insumos al kardex | `RecetasUC.aplicar_consumo()` |
| `_cargar_alertas_cxp` | Decide si proveedor tiene deuda vencida | `ProveedorUC.alertas_cxp()` |

---

## NO ELIMINAR (preservar intacto)

- `_procesar_compra` — usa `RegistrarCompraUC` correctamente
- `_build_tab_qr` — lógica QR (NO tocar)
- `_cargar_historial_compras` / `_poblar_historial` — historial funcional
- Todo el módulo de impresión (`_ofrecer_impresion_recepcion`, `_generar_html_*`)
- `_auto_save_draft` / `_check_pending_draft` — draft funcional con repository
- `_seleccionar_proveedor` — recién corregido, correcto

---

## Resumen de impacto

| Categoría | Líneas afectadas | Riesgo |
|-----------|-----------------|--------|
| Eliminación inmediata | 41 (3353–3393) | Cero — código muerto |
| CSS hardcodeado | ~6 líneas | Bajo — visual only |
| SQL a repositorios | ~60 líneas de queries | Medio — requiere tests |
| Lógica a use-cases | ~100 líneas | Alto — requiere tests primero |
