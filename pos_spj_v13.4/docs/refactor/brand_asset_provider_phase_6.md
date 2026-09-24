# Punto 6 — BrandAssetProvider

Fecha: 2026-09-21. Estado: **recursos incorporados, proveedor integrado y
validación automática completada**. Los originales suministrados se conservan
sin modificaciones de arte; la aceptación visual en la terminal real sigue
siendo una revisión distinta de estas pruebas.

## Contrato y consumidores

`frontend/desktop/components/branding.py` centraliza los seis nombres:

| Recurso | Consumidor |
|---|---|
| `logo_horizontal_light` / `logo_horizontal_dark` | Login y sidebar expandido |
| `isotype_light` / `isotype_dark` | Sidebar colapsado |
| `app_icon` | Icono predeterminado de QApplication, aplicado antes del login |
| `window_icon` | StandardWindow y StandardDialog |

Los recursos se buscan en `AppPaths.resource_root/assets/branding`, en orden
SVG, PNG, ICO. No se depende del directorio de trabajo. En fuente se resuelven
desde el paquete real; en PyInstaller pueden vivir bajo `_MEIPASS`, separado
de la instalación y de los datos persistentes. No existe un pipeline de build
PyInstaller en este repositorio: se prueba la resolución simulada, no un `.exe`.

SVG se renderiza al tamaño físico solicitado. PNG e ICO se escalan conservando
proporción, colores y transparencia; el pixmap conserva su DPR. `BrandLabel`
ajusta la imagen al espacio disponible y sigue cambios de tema, colapso y
monitor. No aplica tintes ni recorta el original.

Un archivo ilegible se registra y permite probar otra extensión del mismo
recurso. Solo `app_icon` y `window_icon` se respaldan entre sí. Si falta un
logo o isotipo, se muestra el texto temporal JUANIS; no se utiliza la variante
del tema contrario ni un símbolo de interfaz como sustituto.

El icono de ventana entregado usa un PNG incrustado mediante `href` de SVG2.
Qt5 aceptaba el documento, pero lo dibujaba transparente. El proveedor adapta
esas referencias **en memoria** a `xlink:href`, con el prefijo literal que Qt5
requiere. Conserva la carpeta base de imágenes locales y no escribe el SVG.
El motor de QIcon vuelve a renderizar el recurso a cada tamaño solicitado,
manteniendo sus colores. Un resultado completamente transparente ahora activa
la búsqueda de otra extensión o del icono de respaldo correspondiente.

`ApplicationWindow` hereda `StandardWindow`. Login, recuperación e instalación
bloqueada heredan `StandardDialog`. Los diálogos operativos usan el icono de
ventana sin añadir un logo grande a cada formulario.

## Recursos suministrados

Los seis roles ya tienen archivos en `assets/branding/`: los cuatro logos e
isotipos y el icono de aplicación en PNG; el icono de ventana en SVG. Se conserva
también `logo_vertical.svg` como original adicional, fuera de los seis roles.
No se generó, recortó, retocó ni reinterpretó arte de JUANIS.

Los horizontales miden 4096×1536; los isotipos 4096×3124; el icono de aplicación
4096×4096; el icono de ventana 512×512. Los márgenes transparentes y bordes blancos
visibles proceden de los archivos originales. El proveedor los conserva, por lo
que el símbolo del icono de aplicación ocupa menos área que el isotipo.

Las instrucciones de entrega están en
[assets/branding/README.md](../../assets/branding/README.md). Se debe completar
la revisión de login, sidebar expandido/colapsado, ambos temas y los iconos del
ejecutable en la terminal real.

## Validación y alcance

**180 PASSED distintos, 0 FAILED, 0 ERRORS, 0 SKIPPED**: 140 pruebas del
segmento principal y 40 casos visuales. Estos últimos generan las 200 capturas
de ventanas compartidas con el punto 4; no se suman de nuevo entre fases.
La compilación de los archivos afectados y `git diff --check` del alcance
terminaron sin errores.

El manifiesto registra el segmento principal (proveedor, originales reales,
rutas, login, geometría e iconos) y la matriz visual compartida con QSS. Esta
continuación añadió 32 casos: 18 de formatos, referencias SVG, transparencia,
DPR y layout/monitor, más 14 que cargan los archivos reales.

Antes del ajuste, los 14 casos reales arrojaron 11 aprobados y 3 fallos por el
icono SVG transparente. Los tres casos sintéticos SVG2 también fallaron antes
de corregir la carga. La revisión protegió además las referencias locales para
evitar que la adaptación perdiera la carpeta base del recurso.

Las pruebas usan figuras geométricas temporales identificadas como fixtures;
no son arte aprobado ni se incorporan a `assets/branding`. Comprueban formatos,
proporción, transparencia, resolución física, tema, colapso, recuperación frente
a un archivo corrupto y ausencia explícita de variantes.

Resultados reproducibles y hashes: [manifiesto](evidence/brand_asset_provider_phase_6/validation.json).
La evidencia de ventanas con los originales suministrados queda en la
[matriz compartida](evidence/qss_global_phase_4/index.html), con ambos temas y
densidades en cinco resoluciones. No se presentan fixtures como marca final.
Se inspeccionaron login en Claro y shell expandido/colapsado en Oscuro,
1280×720 Táctil: el logo horizontal y el isotipo se muestran sin recorte.
Los hashes de los siete originales coinciden con los tomados durante la
auditoría previa a la adaptación SVG.

Se mantiene el fallo del guardrail de overflow en `PricingSettingsPage` y
`MeatProcessingSettingsPage`, ajenas a esta fase. No se amplió el baseline.
No se modificaron reglas de negocio, datos, identidades ni esquema.

## Archivos de esta continuación

- Modificados: `frontend/desktop/components/branding.py`,
  `tests/ui/test_brand_asset_provider.py`, las guías visuales/de adopción,
  `assets/branding/README.md` y documentación de estado.
- Creados: `tests/ui/test_brand_official_assets.py`, este informe y su evidencia.
- Suministrados por el usuario: siete archivos de arte en `assets/branding`.
- Eliminados: ninguno.

El proveedor, `AppPaths.resource_root` y sus consumidores ya estaban presentes.
La auditoría verificó esa integración, corrigió la carga SVG2 y amplió su
protección; no creó otra ruta para cargar marca.

Reproducción desde el paquete interno:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_brand_asset_provider.py tests/ui/test_brand_official_assets.py tests/unit/test_app_paths_resources.py tests/ui/test_login_window.py tests/ui/test_responsive_components.py tests/architecture/test_icon_catalog.py -q -p no:cacheprovider
```

Siguiente punto de la numeración: **7. Density profiles**.
