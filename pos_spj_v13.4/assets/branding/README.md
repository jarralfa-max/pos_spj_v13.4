# Recursos oficiales JUANIS

Esta carpeta contiene los recursos de JUANIS entregados el 2026-09-21.
No colocar imágenes de prueba, logos reinterpretados ni iconos genéricos de interfaz.

| Nombre sin extensión | Uso |
|---|---|
| `logo_horizontal_light` | Login y navegación expandida en Claro |
| `logo_horizontal_dark` | Login y navegación expandida en Oscuro |
| `isotype_light` | Navegación colapsada en Claro |
| `isotype_dark` | Navegación colapsada en Oscuro |
| `app_icon` | Icono de aplicación |
| `window_icon` | Icono de ventanas y diálogos |

Formatos admitidos, en orden de preferencia: SVG, PNG, ICO. Los archivos deben
usar exactamente estos nombres en minúsculas. Se prefieren originales SVG
autocontenidos o PNG con transparencia. Un ICO puede conservar sus resoluciones
nativas para el sistema operativo.

Actualmente los cuatro logos/isotipos y `app_icon` están en PNG;
`window_icon` está en SVG. `logo_vertical.svg` se conserva como original
adicional: no sustituye al logo horizontal ni al isotipo de navegación.

El proveedor conserva colores, proporciones y transparencia. No convierte un
logo Claro en Oscuro, ni un logo horizontal en isotipo. Si falta la variante
solicitada, la interfaz muestra JUANIS como texto temporal, sin presentarlo como
un logo aprobado. Los iconos `app_icon` y `window_icon` pueden respaldarse entre
sí; los archivos ilegibles se registran y se intenta otra extensión del mismo recurso.

En fuente: `pos_spj_v13.4/assets/branding/`. En el ejecutable: la misma ruta
relativa a `AppPaths.resource_root`, incluido el directorio de extracción de
PyInstaller. El empaquetado debe incluir esta carpeta como datos; no basta con
copiarla junto a un ejecutable que extrae sus recursos en otra ubicación.
Ver [contrato de instalación](../../docs/architecture/INSTALLER_AND_UPDATER.md).

Con los originales incorporados, revisar las dos variantes y el colapso de navegación
en la terminal real. Las pruebas con figuras sintéticas verifican carga y layout,
pero no aprueban la identidad visual.

Qt5 recibe en memoria las referencias SVG2 `href` adaptadas a `xlink:href`.
El archivo original no se reescribe. Los resultados y capturas están en el
[informe de BrandAssetProvider](../../docs/refactor/brand_asset_provider_phase_6.md).
