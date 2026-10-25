# PROD-23 — Códigos automáticos de catálogo y código de barras en el alta

Fecha: 2026-10-22. Sin migración.

## Lo que se reportó

1. En «Nuevo producto» no se podía capturar el código de barras: había que crear
   el producto, cerrarlo y entrar a Más acciones → Códigos de barras.
2. Los códigos de categorías, marcas, atributos, etc. se tecleaban a mano siempre.

## Qué quedó

| Tema | Comportamiento |
|---|---|
| Código de barras en el alta | Sección «Lleva código de barras» (opcional, visible con `PRODUCTOS.codigo_barras.gestionar`): escanear/teclear (Enter del lector no guarda el formulario), tipo autodetectado por longitud (13 → EAN-13, 12 → UPC-A) y botón **Generar interno**. Se asigna como **principal** en la MISMA transacción del alta: dígito verificador malo o código de otro producto → no se crea nada. Exige el permiso de códigos de barras además del de alta. |
| Código de barras interno | EAN-13 con prefijo GS1 **04** (circulación restringida dentro de la empresa; no choca con báscula 2x ni con fabricante) y consecutivo propio (`product_code_sequences`, clave `BARCODE-EAN13-04`). La vista previa no consume; asignar cualquier EAN interno — generado o tecleado — adelanta el consecutivo, así no se repite. También en el diálogo «Códigos de barras». |
| Edición | El formulario de edición tiene botón «Códigos de barras…». |
| Códigos de catálogo | Categoría, marca, atributo, opción de atributo, especie, región anatómica y corte: el campo «Código» se llena solo desde el nombre (sin acentos, mayúsculas, palabras con `_`, ≤ 24 sin partir palabras, `_2`, `_3`… si ya existe en su ámbito). Si se reescribe se respeta; si se borra vuelve a generarse. El alta lo resuelve otra vez dentro de su transacción (la vista previa no aparta). En edición el código sigue siendo explícito. |

Ámbitos de unicidad: opciones por atributo; regiones y cortes por especie; el resto
global en su catálogo.

## Dónde

- Dominio: `backend/domain/products/policies/catalog_code_policy.py`;
  `internal_ean13` / `internal_ean_sequence` en `value_objects/barcode.py`.
- Aplicación: `backend/application/products/catalog_codes.py` (regla única para
  vista previa y alta), `queries/internal_barcode.py`,
  `stage_barcode_assignment` (asignación sin commit, reutilizada por el alta).
- Comandos de alta de los 7 catálogos: el código deja de ser obligatorio.
- UI: `dialogs/auto_code.py` (`AutoCodeBinder`), formularios de categoría, marca,
  atributo/opción, especie/región/corte y producto.

## Verificación

`tests/integration/products/test_prod23_auto_codes_and_barcode.py` (12). Suite de
Productos: 622 pasan; las 19 que fallan importan paquetes legacy ya borrados
(`modulos`, `core`, `repositories`) y fallan igual sin este cambio.
`tests/ui/test_products_standard_dialog_adoption.py` (60) en verde.
