# Compras Enterprise — baseline de Fase 0

**Fecha de captura:** 2026-08-01  
**Commit observado:** `e5d1e02`  
**Estado:** rechazado para validación visual/operativa; esta fase no modifica lógica.

## 1. Ruta realmente ejecutada

El registro `compras` apunta a `ModuloComprasEnterprise` en
`modulos.compras_enterprise`. Ese wrapper delega en
`create_enterprise_purchasing_view`, que construye el shell enterprise. No se
encontró otra vista activa detrás de la entrada principal de Compras.

## 2. Intento de ejecución y limitación del entorno

Se ejecutó:

```bash
QT_QPA_PLATFORM=offscreen python -c "from frontend.desktop.modules.purchasing.enterprise_view import EnterprisePurchasingView"
```

Resultado reproducible en el contenedor:

```text
ImportError: libGL.so.1: cannot open shared object file: No such file or directory
```

También se intentó instalar `libgl1` y `xvfb`; los repositorios Ubuntu fueron
rechazados por el proxy con HTTP 403. Por tanto, **no se generaron capturas
visuales falsas** y no se afirma validación a 1366×768 o 1920×1080. La
evidencia automatizada disponible es estructural y está almacenada en
`docs/architecture/evidence/procurement_phase0_audit.json`.

## 3. Permisos: reproducción de botones faltantes

El backend define permisos canónicos `PURCHASES_*` mediante
`PurchasePermissions`, pero la UI consulta literales incompatibles
`procurement.*`. Para un comprador con `PURCHASES_REQUISITION_CREATE`, la
consulta UI `procurement.requisition.create` devuelve falso; por eso el botón
**Nueva solicitud** se oculta aunque el backend reconozca el permiso.

Se encontraron 12 literales UI incompatibles, incluidos permisos de solicitud,
orden, factura, costo y recepción logística. La lista exacta está en el JSON de
evidencia.

## 4. Compra directa a 1366×768

La inspección reproducible confirma que una sola página contiene a la vez:

1. encabezado propio dentro del shell;
2. formulario de captura;
3. tabla de carrito;
4. cuatro acciones documentales simultáneas;
5. filtros de historial;
6. segunda tabla de compras recientes.

Las acciones simultáneas son **Guardar compra**, **Autorizar en caliente**,
**Confirmar y recibir** y **Reversar**. Esta composición reproduce la causa
estructural de saturación y doble encabezado señalada para 1366×768. La
confirmación visual queda pendiente hasta disponer de Qt/libGL.

## 5. Rutas placeholder expuestas

El sidebar expone cinco rutas construidas con `_PendingPage`:

| Ruta | Estado observado |
|---|---|
| Cotizaciones | Placeholder |
| Adjudicaciones | Placeholder |
| Compras móviles | Placeholder/enlace informativo |
| Contenedores asignados | Placeholder |
| Políticas y tolerancias | Placeholder |

Esto incumple la regla de ocultar mediante feature flags toda función no
operativa.

## 6. Dictamen baseline

| Verificación | Resultado |
|---|---|
| Ruta enterprise real | Confirmada |
| Sesión sin almacén inventado | Corregida previamente; cubierta por tests |
| Namespace único de permisos | **No cumple** |
| Botones por permiso canónico | **No cumple** |
| Compra directa separada de historial | **No cumple** |
| Acción primaria única | **No cumple** |
| Placeholders ocultos | **No cumple** |
| Captura 1366×768 claro/oscuro | Bloqueada por `libGL.so.1` |
| Captura 1920×1080 claro/oscuro | Bloqueada por `libGL.so.1` |

## 7. Comando de inventario reproducible

```bash
python tests/architecture/procurement_phase0_audit.py
```

La siguiente fase debe comenzar por unificar capacidades UI con
`PurchasePermissions`, antes de rediseñar navegación o flujos.
