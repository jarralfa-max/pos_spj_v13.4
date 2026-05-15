# Política QR NO-TOUCH — Módulo Compras
> Versión: 2026-05-15 | Permanente hasta Fase 9 explícita

---

## Definición

**QR NO-TOUCH** significa que el código de la pestaña *Recepción QR / Flujo con QR* y su motor subyacente **NO SE MODIFICA** salvo lo mínimo indispensable para aceptar PO.

---

## Archivos Protegidos

| Archivo | Política |
|---------|---------|
| `modulos/recepcion_qr_widget.py` | Solo UI/UX + Tab PO (ya agregada en Fase 6). Sin cambiar lógica QR existente. |
| `services/qr_service.py` | No modificar. No reimportar desde código nuevo de compras. |
| `core/events/wiring.py` handlers QR | No agregar handlers que dupliquen movimientos QR. |
| Tablas `trazabilidad_qr`, `contenedores_qr` | No alterar esquema sin migración documentada. |

---

## Qué NO se permite hacer

1. Reescribir el motor QR existente
2. Crear un segundo motor QR
3. Duplicar lógica de contenedores
4. Duplicar lógica de transferencias QR
5. Duplicar inventario desde compras_pro.py
6. Duplicar kardex desde compras_pro.py
7. Duplicar lotes desde compras_pro.py
8. Modificar `_build_tab_generar()` — la lógica de generación QR es inalterable
9. Modificar `_build_tab_recepcionar()` — la recepción QR es inalterable
10. Modificar `_build_tab_asignar()` — la asignación QR es inalterable
11. Importar `qr_service` desde código nuevo de compras
12. Referenciar `_hist_timeline` ni `tipo_doc` desde `recepcion_qr_widget.py`

---

## Qué SÍ se permite

1. Mejorar UI/UX en tabs QR existentes (solo estilos, layout, no lógica)
2. Agregar tab PO recepción (ya hecho en Fase 6 como `_tab_po_recv`)
3. Mostrar comparación esperado vs recibido cuando recepción viene de PO
4. Conectar visualmente PO con recepción
5. Usar `ReceivePOAdapter` (creado en Fase 4) como único punto de entrada PO
6. Agregar filtros en el tab Histórico QR (solo UI/UX)

---

## Verificación Automática

Los siguientes tests garantizan cumplimiento de la política:

```
tests/purchases/test_qr_flow_no_regression.py
  - test_qr_service_imports_without_error
  - test_qr_tipos_soportados_unchanged
  - test_qr_and_traditional_purchase_are_independent
  - test_no_new_qr_engine_module_created
  - test_compras_pro_module_has_no_syntax_error
  - test_qr_service_module_has_no_syntax_error

tests/purchases/test_phase7_historial_timeline.py
  - test_qr_widget_not_modified_for_phase7
    (verifica: _hist_timeline NOT IN recepcion_qr_widget.py)
    (verifica: tipo_doc NOT IN recepcion_qr_widget.py)

tests/purchases/test_phase6_reception_po_ui.py
  - test_does_not_reimport_qr_service
  - test_build_tab_generar_unchanged
  - test_build_tab_recepcionar_unchanged
```

---

## Riesgo de Doble Inventario

Si se llama `add_stock()` desde:
- `recepcion_qr_widget.py` (UPSERT inventario_actual) → ruta QR original
- `ReceivePOAdapter.register_partial_receipt()` → ruta PO

Ambas rutas son **mutuamente excluyentes**:
- Recepción QR: usuario escanea contenedor → flujo QR
- Recepción PO: usuario selecciona PO en tab "🧾 Recepción PO" → flujo PO adapter

No existe código que llame ambas rutas para el mismo artículo.

---

## Excepción Documentada

`recepcion_qr_widget.py` contiene SQL directo de mutación (inventario, kardex, trazabilidad).
Este SQL es la lógica QR existente y **no se toca**.

Si en Fase 9 se decide moverlo a un servicio, se hará con tests de caracterización primero.
