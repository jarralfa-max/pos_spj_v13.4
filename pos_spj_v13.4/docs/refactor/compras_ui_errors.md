# FASE 0 — Inventario de errores UI en Compras

**Fecha:** 2026-05-17
**Regla de esta entrega:** documentar y agregar smoke tests; no rediseñar todavía.

---

## 1. Errores UI activos

| ID | Severidad | Archivo/área | Hallazgo | Riesgo | Fase de corrección |
|---|---|---|---|---|---|
| UI-01 | ALTO | `compras_pro.py` KPI/tabla/cards | Uso extensivo de `setStyleSheet()` con colores principales y bordes. | Tema oscuro/claro inconsistente; difícil aplicar QSS global. | Fases 3-4 |
| UI-02 | ALTO | `recepcion_qr_widget.py` sidebars | Uso de `Colors.NEUTRAL.SLATE_50` como fondo fijo en paneles de recepción. | Paneles claros dentro de tema oscuro. | Fase 4, sin tocar lógica QR |
| UI-03 | RESUELTO | `recepcion_qr_widget.py` | La tab interna `🧾 Recepción PO` fue eliminada. | PO vive como submodo/panel interno de `📦 3. Recepcionar`. | Fase 2 completada |
| UI-04 | RESUELTO | `_build_documental_toolbar()` | La columna documental usa mínimo/máximo 260–320 px en lugar de ancho fijo rígido. | Mantiene densidad documental sin bloquear el splitter. | Fase 3 completada |
| UI-05 | RESUELTO PARCIAL | `_build_summary_panel()` | Panel derecho sube a mínimo 480 px y crece con el splitter. | Queda limpieza fina de estilos para Fase 4. | Fase 3/Fase 4 |
| UI-06 | MEDIO | `_build_purchase_items_panel()` | Header de tabla fuerza `Colors.NEUTRAL.SLATE_100`. | Header claro fijo en dark mode. | Fase 4 |
| UI-07 | MEDIO | botones rápidos/dinámicos | Algunos botones tienen `QPushButton{...}` inline. | Se apartan de `primaryBtn`, `secondaryBtn`, `successBtn`. | Fases 3-4 |
| UI-08 | MEDIO | badges/chips documentales | Chips usan styles manuales. | Badges no heredan estándar global. | Fase 4 |
| UI-09 | BAJO | `_PurchaseKPICard` | Es hermano de Inventario, pero todavía define color/size inline. | Aceptable temporalmente; requiere limpieza futura. | Fase 3 |

---

## 2. Estado del layout de Compra Tradicional

El código actual sí crea un `QSplitter` horizontal con tres áreas: toolbar documental, captura central y panel derecho. La tabla de partidas está dentro del panel derecho actual. La deuda visual no es crear una cuarta área ni otra pantalla, sino estabilizar estas tres columnas con componentes estándar y tema global.

### Distribución actual

```text
Compra Tradicional
├── left_col  = _build_documental_toolbar()
├── center    = _build_center_column()
└── right_col = _build_summary_panel()
    ├── _build_purchase_items_panel()  ← tabla de partidas
    ├── totales/pago
    └── acción dinámica
```

---

## 3. Hardcodes detectados por búsqueda

Búsquedas ejecutadas:

```bash
rg -n "background:white|background: white|SLATE_50|#fff|#ffffff|WHITE|setFixedWidth\(230\)|setStyleSheet|QPushButton\{" pos_spj_v13.4/modulos/compras_pro.py pos_spj_v13.4/modulos/recepcion_qr_widget.py
```

Resultado resumido:

- No se encontró `panel.setFixedWidth(230)` exacto en los archivos auditados.
- Sí existen múltiples `setStyleSheet()` manuales en Compras y Recepción QR.
- Sí existen `Colors.NEUTRAL.SLATE_50` en Recepción QR.
- Sí existen `#ffffff`, `#fff` y fondos claros en HTML/renderizado de historial/impresión.
- Los botones principales nuevos no deben copiar estos patrones.

---

## 4. Estándar visual a reutilizar

| Elemento | Estándar |
|---|---|
| Cards | `create_card()` o `QFrame` con objectName estándar y QSS global. |
| KPI | Patrón `_InvKPICard`: `#kpiCard`, `#kpiValue`, barra de acento mínima. |
| Inputs | `create_input()` / `create_combo()` / `objectName="inputField"`. |
| Tabla | `QTableWidget#tableView`, sin QSS inline claro. |
| Badges | `create_badge()` o variante con objectName/propiedades. |
| Botones | `create_primary_button`, `create_secondary_button`, `create_success_button`, `create_danger_button`, o objectName semántico. |
| Tabs | `create_standard_tabs()`. |
| Tema | `ThemeManager`/QSS global; no hardcodear fondos blancos. |

---

## 5. No cambios aplicados en Fase 0/Fase 1

- No se rediseñó la pantalla.
- No se cambió el layout funcional existente.
- No se modificaron reglas de inventario/CXP/finanzas.
- No se tocó el motor QR.
- La tab interna de PO fue eliminada en Fase 2; queda pendiente limpiar estilos generales en Fase 4.
