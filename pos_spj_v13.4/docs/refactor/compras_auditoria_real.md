# FASE 0 — Auditoría real del módulo Compras ERP

**Fecha:** 2026-05-17
**Alcance:** auditoría sin cambio funcional de `modulos/compras_pro.py`, `modulos/recepcion_qr_widget.py`, componentes visuales, servicios de compras, repositorios y casos de uso relacionados.
**Decisión base:** detener la ejecución en Fase 0 + Fase 1. No se rediseña UI, no se implementa PR/PO nuevo, no se toca el motor QR y no se migran datos.

---

## 1. Mapa actual de pestañas

### 1.1 Pestañas principales de `ModuloComprasPro`

`_build_ui()` crea exactamente tres tabs externas:

| Índice | Tab actual | Constructor | Evaluación |
|---:|---|---|---|
| 0 | `🛒 Compra Tradicional` | `_build_tab_tradicional()` | Cumple contrato de 3 tabs principales. |
| 1 | `📦 Recepción con QR` | `_build_tab_qr()` | Cumple como contenedor de recepción física. |
| 2 | `📋 Historial de Compras` | `_build_tab_historial()` | Cumple estructura principal ligera. |

Evidencia: `compras_pro.py` agrega las tres tabs principales en `_build_ui()` y no agrega una cuarta pestaña externa para PO.

### 1.2 Pestañas internas actuales de `RecepcionQRWidget`

`RecepcionQRWidget._build_ui()` crea cuatro tabs internas y la recepción contra PO vive como submodo dentro de `📦 3. Recepcionar`:

| Índice | Tab interna actual | Evaluación Fase 2 |
|---:|---|---|
| 0 | `🏷️ 1. Generar Etiqueta QR` | Lógica QR existente: no tocada. |
| 1 | `📋 2. Asignar Compra` | Lógica QR existente: no tocada. |
| 2 | `📦 3. Recepcionar` | Contiene selector interno `QR / Contenedor` y `Orden de Compra / PO`. |
| 3 | `📜 Historial` | Historial QR existente: no tocado. |

**Conclusión Fase 2:** el nivel principal conserva tres tabs y el widget QR ya no expone una pestaña separada para recepción PO; el contenido útil se mantiene dentro de Recepcionar como panel/submodo.

---

## 2. Mapa actual de UI en Compra Tradicional

| Zona | Estado actual | Severidad |
|---|---|---|
| Header | Usa `PageHeader` y KPI bar fuera de tabs. | BAJO |
| KPI bar | Usa `_PurchaseKPICard`, muy similar a `_InvKPICard` de Inventario, pero con estilos inline para bordes/divisores. | MEDIO |
| Layout principal | Usa `QSplitter` horizontal con izquierda, centro y derecha. | MEDIO |
| Columna izquierda | `_build_documental_toolbar()` mezcla flujo documental con accesos secundarios; ancho fijo 260 px. | ALTO |
| Columna central | `_build_center_column()` contiene selector tipo documento, stepper, proveedor, documento, búsqueda y productos rápidos. | MEDIO |
| Columna derecha | `_build_summary_panel()` contiene tabla de partidas + totales + pago + acción dinámica, con mínimo 400 px. | MEDIO |
| Tabla de partidas | Está en la derecha, dentro de `_build_purchase_items_panel()`. | BAJO |
| Historial | Tiene filtros, tabla y panel KPI derecho; no es BI pesado. | BAJO |

**Hallazgo importante:** el layout actual ya intenta tres columnas y la tabla está en derecha. La deuda no es crear otro layout desde cero, sino limpiar visualmente el layout, eliminar estilos claros fijos, normalizar objectNames/QSS y separar responsabilidades de UI/negocio.

---

## 3. Patrón visual real del módulo Inventario

Inventario (`modulos/inventario_local.py`) define el estándar a reutilizar:

| Elemento | Patrón Inventario | Implicación para Compras |
|---|---|---|
| KPI card | `_InvKPICard` con `objectName="kpiCard"`, altura mínima 86, barra superior de acento y valor `#kpiValue`. | `_PurchaseKPICard` debe mantenerse hermano y reducir estilos inline no semánticos. |
| KPI row | `_build_kpi_row()` agrega cinco cards con `Spacing.MD` y sin tabs intermedias. | Compras debe mantener KPI bar fuera de tabs y con densidad equivalente. |
| Tablas | `QTableWidget#tableView`, no editables, selección por filas, grid oculto, colores por QSS global. | Compras debe evitar headers hardcodeados claros y delegar a QSS global. |
| Inputs | `objectName="inputField"`. | Compras debe usar `create_input`, `create_combo` u objectName equivalente. |
| Botones | `objectName` semántico (`successBtn`, `warningBtn`, `secondaryBtn`). | Compras debe evitar `QPushButton{background:...}` inline. |
| Header | `PageHeader`. | Compras ya lo reutiliza. |

---

## 4. Componentes estándar disponibles

| Archivo | Componentes útiles identificados |
|---|---|
| `modulos/ui_components.py` | `PageHeader`, `Toast`, `create_card`, `create_kpi_card`, `create_badge`, `create_input`, `create_combo`, `create_standard_tabs`, `wrap_in_scroll_area`, `LoadingIndicator`, `EmptyStateWidget`. |
| `modulos/design_tokens.py` | `Colors`, `Spacing`, `Typography`, `Borders`. |
| `modulos/spj_styles.py` | `apply_spj_buttons` para asignación de objectNames estándar. |
| `modulos/qss_builder.py` | QSS global para `#kpiCard`, `#pageHeader`, `#tableView`, botones e inputs. |
| `ui/themes/theme_engine.py` | `ThemeManager` / `ThemeEngine` como punto de aplicación de QSS global. |

---

## 5. Mapa backend y side effects actuales

### 5.1 Ruta de compra directa actual

`RegistrarCompraUC.execute()` invoca `PurchaseService.register_purchase()` con items, proveedor, sucursal, forma de pago y metadatos de documento. Después procesa recetas y escribe auditoría.

`PurchaseService.register_purchase()` actualmente hace demasiado en una sola ruta:

| Efecto | Ubicación actual | Evaluación |
|---|---|---|
| Crear cabecera de compra | `purchase_repo.create_purchase()` llamado desde `register_purchase()` | Válido para compra directa. |
| Guardar partidas | `purchase_repo.save_purchase_items()` | Válido para compra directa. |
| Afectar inventario | EventBus `PURCHASE_ITEMS_PROCESS` o fallback `inventory_service.add_stock()` | **Crítico si se reutiliza para PR/PO.** |
| Generar CXP | `finance_service.crear_cxp()` cuando hay deuda | **Crítico si PR/PO llaman esta ruta.** |
| Registrar caja/asiento | `registrar_movimiento_manual()` y `registrar_asiento()` | Riesgo de duplicidad con otras rutas financieras. |
| Crear lotes | `_crear_lotes_compra()` inserta `lotes` y `movimientos_lote` | **Crítico si PR/PO llaman esta ruta.** |
| Publicar evento de inventario | EventBus `PURCHASE_ITEMS_PROCESS` | Correcto para compra directa/recepción; prohibido para PR/PO documental. |

### 5.2 Ruta legacy adicional con riesgo de doble asiento

`core/use_cases/compra.py` declara `ProcesarCompraUC` como deprecado y advierte que puede duplicar asientos si se combina con handlers financieros. Además registra asientos y CXP después de llamar a `PurchaseService.register_purchase()`.

### 5.3 SQL directo en UI

`compras_pro.py` contiene SQL directo y fallbacks de BD dentro de widgets/métodos UI. Ejemplos auditados:

| Uso | Líneas/área | Riesgo |
|---|---|---|
| Carga documental PR/PO en toolbar | `_load_documental_docs()` con `container.db.execute()` | UI conoce tablas/estados. |
| Carga proveedores/sucursales/plantillas | métodos de carga en UI | Acoplamiento UI-BD. |
| Procesamiento de recetas | consulta recetas y actualiza `productos.existencia` | Riesgo alto de side effects fuera de servicios. |
| Fallback compra directa | `_fallback_compra_directa()` inserta compra, detalles y actualiza inventario | Riesgo crítico: bypass de servicios canónicos. |

**Decisión Fase 0:** no borrar ni mover aún. Documentar y proteger con tests. Cualquier refactor debe envolver primero para compatibilidad.

---

## 6. Tabla de severidad consolidada

| Severidad | Hallazgo | Acción posterior |
|---|---|---|
| CRÍTICO | `register_purchase()` afecta inventario, CXP, caja/asientos y lotes; PR/PO no pueden usar esta ruta. | Fases 5-7: separar DIRECT/PR/PO/recepción. |
| CRÍTICO | `_fallback_compra_directa()` en UI puede insertar compra y actualizar stock directamente. | Fase 5: estabilizar compra directa y retirar fallback solo con wrapper seguro. |
| RESUELTO | `RecepcionQRWidget` ya no contiene pestaña interna explícita `Recepción PO`; PO vive como submodo de `Recepcionar`. | Fase 3+: limpiar visualmente sin tocar motor QR. |
| ALTO | SQL directo y side effects en `compras_pro.py`. | Fases 6-8: mover a use cases/adapters. |
| ALTO | Colores claros fijos y estilos inline abundantes en Compra Tradicional/QR. | Fases 3-4: normalizar con tokens/QSS global. |
| MEDIO | KPI de Compras parece hermano de Inventario pero aún mezcla styles inline y divisores propios. | Fase 3: alinear con patrón Inventario. |
| MEDIO | Toolbar documental mezcla flujo con elementos secundarios y usa ancho fijo. | Fase 3: reorganizar sin cambio negocio. |
| BAJO | Imports críticos `QInputDialog` y `QScrollArea` ya están presentes. | Fase 1: smoke tests para prevenir regresión. |

---

## 7. Límites de esta fase

- No se modificó comportamiento funcional.
- No se rediseñó Compra Tradicional.
- No se tocó `RecepcionQRWidget` ni motor QR.
- No se separaron todavía rutas PR/PO/DIRECT.
- No se corrigió aún la pestaña interna PO: queda documentada para Fase 2.
