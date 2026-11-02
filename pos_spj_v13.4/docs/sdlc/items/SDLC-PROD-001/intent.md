# SDLC-PROD-001 — Ficha de producto sin flujo guiado ni camino a capturar su precio

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `inputs/correcciones.md` C-11 (oleada 5); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P2 — La UI de Productos separa reglas operativas y no indica ruta de precio»
- **Estado:** borrador
- **Depende de:** SDLC-PRICE-001

## Problema
Dar de alta un producto se hace en un diálogo con cuatro pestañas sueltas; al terminar no hay ninguna indicación de que el producto todavía no tiene precio ni un enlace para capturarlo en la lista vigente o en un borrador. El usuario descubre en el POS que el producto no se puede cobrar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `frontend/desktop/modules/products/dialogs/product_form_dialog.py:95-98` — pestañas `General`, `Operación`, `Inventario`, `Imágenes`; sin paso de comercialización.
- `frontend/desktop/modules/products/dialogs/product_form_dialog.py:5` — «El precio permanece bajo Precios» (correcto como dueño del dato; falta el camino).
- `frontend/desktop/modules/products/dialogs/product_form_dialog.py:67` — ya hereda de `StandardDialog`.

## Impacto
Altas incompletas; productos sin precio que fallan en caja.

## Objetivo
- Ficha guiada «Datos → Operación/almacenes → Imagen → Comercialización».
- El paso de comercialización muestra si hay precio en la lista vigente y enlaza a capturarlo (lista vigente vía revisión de SDLC-PRICE-001, o borrador), sin que Productos escriba precios.
- Reutiliza `StandardDialog`, `SearchInput`, `StandardTable` y tokens.

## Alcance
- **Incluye:** reorganización de la ficha y enlace a Precios.
- **No incluye:** migrar los 57 `QPushButton`/18 `QLineEdit` de Productos (SDLC-UI-023); escritura de precios desde Productos.

## Restricciones
Precios es el único dueño del precio (no duplicar captura); CLAUDE.md regla 7; sistema de diseño JUANIS; presupuesto $0; Windows. Nivel T2: plan corto, pruebas afectadas.

## Trabajo previo relacionado
SDLC-UI-023, SDLC-UI-011 (`WizardPage` duplicado), SDLC-UI-002 (secciones de Productos); memoria PROD-21/22 (activación de producto con requisitos, migr. 324).

## Preguntas abiertas
- ¿«Comercialización» debe bloquear la activación del producto si no tiene precio (requisito de activación, migr. 324) o solo avisar? · bloquea `/sdlc-design SDLC-PROD-001`
