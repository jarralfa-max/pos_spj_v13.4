# PROD-21 — Imagen de producto sin fondo, visible en las tarjetas del POS

Fecha: 2026-10-09 · Migración: 323 · Rama: `claude/erp-financial-bounded-context-uqxz6b`

## Qué había (auditoría)

| Pieza | Estado encontrado |
|---|---|
| `product_images` + galería (agregar / principal / eliminar) | Existía (P1). Sólo alcanzable desde la ficha en edición → «Imágenes…». |
| Archivo de la imagen | **Se guardaba la ruta que elegía el usuario** (escritorio, USB). Al mover o borrar el archivo, la imagen desaparecía. |
| `ProductImageService` (copiaba a `AppPaths.product_images_dir`) | Código muerto: cero consumidores. |
| Catálogo del POS | `SalesCatalogQueryService` ya traía `image_reference` (imagen principal) en `ProductCatalogEntryDTO`… |
| Tarjeta del POS (`ProductGrid`) | …pero **nadie la dibujaba**: las tarjetas no mostraban imagen. |
| Quitar fondo | No existía para productos. Había un `quitar_fondo` para el logo del ticket en `frontend/desktop/components/logo_utils.py` (Pillow en la capa UI), sin ningún llamador fuera de su test. |
| Auditoría de imágenes | Las 3 mutaciones de imagen no escribían en `product_audit_log`. |

## Qué quedó

**Flujo para el usuario:** Productos → editar producto → «Imágenes…» → «Agregar…» →
«Quitar fondo» (vista previa inmediata) → si no convence, «Restaurar original».
La imagen **principal** es la que aparece en la tarjeta del POS. Sin imagen, la
tarjeta muestra las iniciales del producto con la misma altura.

| Capa | Archivo | Cambio |
|---|---|---|
| Dominio | `domain/products/entities/product_image.py` | `source_uri`, `background_removed`, `mark_background_removed()`, `restore_original()` (no se quita el fondo dos veces; una imagen sin fondo siempre conserva su original). |
| Dominio | `domain/products/exceptions.py` | `ProductImageProcessingError`. |
| Dominio | `domain/products/events.py` | `PRODUCT_IMAGE_BACKGROUND_REMOVED`, `PRODUCT_IMAGE_BACKGROUND_RESTORED`. |
| Aplicación | `application/products/media/ports.py` | Puertos `ProductImageStorage` y `BackgroundRemover`. |
| Aplicación | `application/products/use_cases/product_image_use_cases.py` | Agregar copia el archivo; nuevos `RemoveImageBackgroundUseCase` y `RestoreImageBackgroundUseCase`; las 5 mutaciones auditan y publican al outbox; los archivos se borran sólo después del commit y sólo dentro de la carpeta administrada. |
| Infraestructura | `infrastructure/media/local_product_image_storage.py` | Copia a `AppPaths.product_images_dir` con nombre UUIDv7, gira según EXIF, reduce a 1600 px. |
| Infraestructura | `infrastructure/media/background_removal.py` | `EdgeConnectedBackgroundRemover`: local, sin internet (Pillow + numpy + scipy). |
| Esquema | `products_schema.py` + `323_product_image_background_removal.py` | Columnas nuevas, idempotente. |
| UI | `components/image_thumbnail.py` | `ImageThumbnail` con caché (ruta + fecha de modificación) e iniciales de respaldo. |
| UI | `sales_pos/components/product_grid.py` | La tarjeta dibuja la imagen (143×85, contrato visual 175×85). |
| UI | `products/dialogs/image_gallery_dialog.py` | Ahora `StandardDialog`; botones de factory; «Quitar fondo» / «Restaurar original»; columna «Fondo»; error en banner. |
| Tema | `themes/qss_builder.py` | Rol `imageThumbnail` (vacío → `SURFACE_MUTED`); sin colores en módulos. |

## Cómo quita el fondo

1. El fondo se modela con los colores del **borde** de la foto, partido en tramos;
   se descartan los tramos disparejos y los que forman un grupo de color
   minoritario (el producto que toca la orilla no se toma como fondo).
2. Es fondo sólo lo parecido a esos colores **y conectado con el borde**: una
   etiqueta blanca dentro del producto se conserva.
3. Limpieza de motas, contorno suavizado y recorte al producto con margen.
4. Si la foto no tiene fondo distinguible, falla con un mensaje para el usuario
   («Toma la foto sobre un fondo liso…»); la imagen no se modifica.

**Límite conocido:** fotos con fondo muy cargado (producto sobre una tabla con
vetas, varios objetos) no se recortan bien. El puerto `BackgroundRemover`
permite enchufar un removedor con IA (p. ej. `rembg`) sin tocar casos de uso ni
pantallas; no se incluyó porque descarga un modelo de ~170 MB en el primer uso.

## Verificación

- `tests/unit/products/test_background_removal.py` — 8 tests (fondo liso, degradado,
  etiqueta interior, producto en la orilla, recorte, fondo caótico, no-imagen,
  archivo ausente).
- `tests/integration/products/test_product_image_background.py` — 15 tests: agregar
  copia el archivo; quitar fondo → `SalesCatalogQueryService` → `ProductGrid` dibuja
  la imagen; restaurar; doble proceso; fallo sin archivos huérfanos; original ausente;
  eliminar borra ambos archivos administrados (nunca el del usuario); auditoría y
  outbox; permiso; migración 323 sobre la tabla anterior; galería con los botones.
- Galería P1 existente (`test_product_images.py`, `test_image_ui_flow.py`) sin cambios, verde.
- Migración 323 sobre copia de la base real: aplicada, 0 pendientes.
- Capturas sobre la copia de la base real (11 productos activos), tema claro y oscuro:
  tarjeta con imagen sin fondo, tarjeta con foto original, tarjetas con iniciales.

## Eliminado (cero consumidores verificados)

| Elemento | Motivo |
|---|---|
| `backend/application/services/product_image_service.py` | Duplicaba el almacenamiento; nadie lo llamaba. |
| `frontend/desktop/components/logo_utils.py` + `tests/test_logo_quitar_fondo.py` | Segundo removedor de fondo, en la capa UI, sin llamadores en producción. |
