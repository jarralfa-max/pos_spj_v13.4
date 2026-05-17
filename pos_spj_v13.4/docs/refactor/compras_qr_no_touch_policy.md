# Política QR NO-TOUCH — Módulo Compras
> Versión: 2026-05-17 | Reemplaza: versión 2026-05-15 | Permanente hasta Fase 9 explícita

---

## Definición

**QR NO-TOUCH** significa que el código de `RecepcionQRWidget` y su motor QR subyacente **NO SE MODIFICA** salvo lo mínimo indispensable para:
1. Aceptar recepción de PO (ya implementado en Fase 6 como `_tab_po_recv`)
2. Correcciones de bugs de arranque (syntax errors, import errors)

---

## Archivos Protegidos

| Archivo | Política |
|---------|---------|
| `modulos/recepcion_qr_widget.py` | Solo UI/UX estética + Tab PO (ya en Fase 6). Sin tocar lógica QR. |
| `services/qr_service.py` | No modificar. No reimportar desde código nuevo de compras. |
| `core/events/wiring.py` — handlers QR | No agregar handlers que dupliquen movimientos QR. |
| Tablas `trazabilidad_qr`, `contenedores_qr` | No alterar esquema sin migración documentada. |

---

## Estructura actual de RecepcionQRWidget (CONGELAR)

```python
class RecepcionQRWidget(QWidget):
    def _build_ui(self):
        # 5 tabs internas — NO CAMBIAR ORDEN
        self._tab_generar     → "🏷️ 1. Generar Etiqueta QR"
        self._tab_asignar     → "📋 2. Asignar Compra"
        self._tab_recepcionar → "📦 3. Recepcionar"
        self._tab_historial   → "📜 Historial"
        self._tab_po_recv     → "🧾 Recepción PO"   ← Fase 6, YA IMPLEMENTADO
```

**El número de tabs internas es 5. No se agregan más.**

---

## Qué NO se permite hacer

1. ❌ Reescribir el motor QR existente
2. ❌ Crear un segundo motor QR fuera de `recepcion_qr_widget.py`
3. ❌ Duplicar lógica de contenedores (`contenedores_qr`)
4. ❌ Duplicar lógica de transferencias QR
5. ❌ Duplicar actualización de inventario desde `compras_pro.py` para artículos QR
6. ❌ Duplicar kardex desde `compras_pro.py` para artículos QR
7. ❌ Duplicar lotes desde `compras_pro.py` para artículos QR
8. ❌ Modificar `_build_tab_generar()` — lógica de generación QR inalterable
9. ❌ Modificar `_build_tab_recepcionar()` — recepción QR inalterable
10. ❌ Modificar `_build_tab_asignar()` — asignación QR inalterable
11. ❌ Importar `qr_service` desde código nuevo de compras
12. ❌ Referenciar `_hist_timeline` ni `tipo_doc` desde `recepcion_qr_widget.py` (Fase 7)
13. ❌ Agregar una 4ª tab EXTERNA de PO reception en `ModuloComprasPro._build_ui`
14. ❌ Cambiar el nombre o el ícono de los 3 tabs externos de ModuloComprasPro

---

## Qué SÍ se permite

1. ✅ Mejorar UI/UX estética en tabs QR (solo estilos, colores de tokens, layout)
2. ✅ El tab `_tab_po_recv` ya fue agregado en Fase 6 — está permitido
3. ✅ Mostrar comparación esperado vs recibido cuando recepción viene de PO
4. ✅ Conectar visualmente PO con recepción (solo display, no lógica duplicada)
5. ✅ Usar `ReceivePOAdapter` como único punto de entrada PO
6. ✅ Agregar filtros en el tab Histórico QR (solo UI/UX)
7. ✅ Corregir bugs de UI en `_tab_po_recv` (Fase 6 puede recibir fixes)

---

## Separación de rutas de recepción

Las dos rutas son **mutuamente excluyentes**:

| Ruta | Activador | Código |
|------|-----------|--------|
| QR | Usuario escanea contenedor | `recepcion_qr_widget.py` → motor QR existente |
| PO | Usuario selecciona PO en `_tab_po_recv` | `ReceivePOAdapter.register_partial_receipt()` |

**No existe ni debe existir código que llame ambas rutas para el mismo artículo.**

---

## Excepción documentada — SQL en recepcion_qr_widget.py

`recepcion_qr_widget.py` contiene SQL directo de mutación (inventario, kardex, trazabilidad).  
Este SQL ES la lógica QR existente y **no se toca hasta Fase 9**.

Si en Fase 9 se decide moverlo a un servicio, se hará con:
1. Tests de caracterización completos primero
2. Migración paso a paso
3. Documentación en `MIGRATION_LOG.md`

---

## Verificación automática (tests activos)

```
tests/purchases/test_qr_flow_no_regression.py
  - test_qr_service_imports_without_error
  - test_qr_tipos_soportados_unchanged
  - test_qr_and_traditional_purchase_are_independent
  - test_no_new_qr_engine_module_created
  - test_compras_pro_module_has_no_syntax_error
  - test_qr_service_module_has_no_syntax_error

tests/purchases/test_qr_no_extra_po_tab.py  ← NUEVO (Fase 1)
  - test_outer_tabs_count_is_exactly_3
  - test_qr_widget_has_5_internal_tabs
  - test_no_fourth_po_tab_in_outer_module
  - test_po_reception_tab_is_inside_qr_widget

tests/purchases/test_phase6_reception_po_ui.py
  - test_does_not_reimport_qr_service
  - test_build_tab_generar_unchanged
  - test_build_tab_recepcionar_unchanged
```

---

## Historial de cambios a esta política

| Fecha | Cambio |
|-------|--------|
| 2026-05-15 | Versión inicial — política QR NO-TOUCH |
| 2026-05-17 | Clarificación: 5 tabs internas QR (no 4). Agregado test `test_qr_no_extra_po_tab.py`. |
