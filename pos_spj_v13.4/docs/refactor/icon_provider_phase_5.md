# Punto 5 — IconProvider

Fecha: **2026-09-13**. Estado: **IMPLEMENTADO; validación automática completada**.
El usuario eligió este punto después de Light/Dark; este informe no declara una
auditoría adicional del punto 4 ni la migración completa de todos los módulos.

## Resultado

`frontend/desktop/components/icons.py` sigue siendo el proveedor canónico.
Su catálogo contiene **138 identificadores semánticos y 99 vectores** con nombre
accesible en español. Los sinónimos comparten un símbolo cuando representan el
mismo concepto; no se incorporaron logos ni fuentes de iconos.

Se incorporaron 93 identificadores solicitados por los módulos. Antes, 135 de
las 159 declaraciones de navegación examinadas acababan mostrando el símbolo
genérico de archivo. Ahora todos sus identificadores existen en el catálogo.
También existen `CATALOG`, `PRICE`, `AUDIT` y `COST`, solicitados por 12 cabeceras
que anteriormente omitían el icono mediante `getattr(..., None)`.

## Comportamiento del proveedor

- El SVG se dibuja mediante un `QIconEngine` al tamaño solicitado. Se elimina
  el límite del render anterior, que precalculaba solamente 20 y 40 píxeles.
- Se prueban tamaños de 16 a 128 px y rasterización con DPR 1, 1.25, 1.5, 2 y 3.
  `pixmap()` conserva el tamaño lógico para etiquetas e imágenes exportadas.
- Se conservan los modos nativos Normal, Active, Selected y Disabled; el estado
  On de un control seleccionable utiliza el color seleccionado. Disabled prevalece.
- Peligro, éxito, advertencia, información e inverso conservan su significado
  durante hover/selección. Se añadió el estado `info` que antes caía al neutro.
- `bind()` adapta los iconos normales de botones `primary`/`danger` al color
  inverso, conserva nombres accesibles personalizados y completa los ausentes.
- Las etiquetas reaccionan a deshabilitación y al cambio de pantalla de su ventana.
  Los bindings se desconectan del emisor original al reemplazarse y se destruyen
  junto con el control; la prueba verifica que no quedan observadores adicionales.
- Las acciones del flyout de `SideNav` también usan bindings. Un menú abierto
  cambia sus iconos con el tema sin alterar sus destinos ni habilitar filas inactivas.

La separación entre modo y estado y la rasterización según el dispositivo sigue
el contrato nativo de [QIcon de Qt 5.15](https://raw.githubusercontent.com/qt/qtbase/5.15/src/gui/image/qicon.cpp).
El SVG continúa siendo código de infraestructura del Design System; los módulos
no pintan glifos, no definen colores y no crean otro proveedor.

## Uso canónico

```python
from frontend.desktop.components.icons import IconProvider, Icons

IconProvider.bind(button, Icons.PRINT)
IconProvider.bind(menu_action, Icons.EXPORT)
IconProvider.bind(label, Icons.WARNING, state="warning", size=24)
```

`icon()` y `pixmap()` son instantáneas del tema solicitado/actual. Los hosts de
filas que usan `icon()` deben refrescarlas al cambiar el tema; los controles
vivos deben preferir `bind()`.

El guardrail `test_icon_catalog.py` comprueba constantes, vectores y nombres,
argumentos de navegación/cabeceras/KPIs y llamadas directas al proveedor. Un
identificador externo desconocido conserva un respaldo de archivo y genera un
aviso en el log; no se acepta como contrato de un módulo registrado.

## Validación y evidencia

Los nombres de cada caso, resultados y hashes están en el
[manifiesto](evidence/icon_provider_phase_5/validation.json).

| Segmento | PASSED | FAILED / ERROR / SKIPPED |
|---|---:|---:|
| Proveedor, estados, DPR, bindings, menús, tema y catálogo | 65 | 0 |
| Shell, componentes, arquitectura, Apariencia y su integración | 270 | 0 |
| Matriz visual y láminas del catálogo | 50 | 0 |
| Revalidación de las dos láminas con nombre accesible corregido | 2 | 0 |
| Guardrail ampliado para llamadas directas y aliases | 11 | 0 |

**385 casos distintos aprobados**: las últimas dos filas solapan 13 casos
anteriores. Antes de la corrección se reprodujeron 14 fallos del proveedor y
otro del flyout abierto. La ejecución intermedia detectó que PyQt5 no expone
`ScreenChangeInternal`; se sustituyó por la señal pública `QWindow.screenChanged`
y se probó ese recorrido.

El auditor conserva **0 infracciones nuevas**, **0 huellas obsoletas** y
**159 ocurrencias preexistentes**. Compilación de los archivos afectados y
`git diff --check` completados sin errores. Las suites completas mantienen sus
fallos previos registrados en la [auditoría general](global_ui_ux_design_system_audit.md);
estos resultados corresponden a los segmentos afectados.

[Abrir el visor](evidence/icon_provider_phase_5/index.html): diez láminas del
catálogo en Claro/Oscuro y ocho estados, más 200 capturas del shell y componentes
en las cinco resoluciones, dos temas y densidades Cómoda/Táctil solicitadas.
Se inspeccionaron láminas representativas de ambos temas. Las capturas anteriores
de la base visual y de Light/Dark permanecen intactas en sus propios directorios.

## Archivos de esta fase

Modificados: `frontend/desktop/components/icons.py`, `side_nav.py`,
`frontend/desktop/design_system/component_contracts.py`, `migration_guide.md`,
`visual_guidelines.md` y `docs/refactor/global_ui_ux_design_system_audit.md`.

Creados: `tests/architecture/test_icon_catalog.py`,
`tests/ui/test_icon_provider_runtime.py`, `test_side_nav_icon_binding.py`,
`test_icon_catalog_visuals.py`, este informe y su directorio de evidencia.
Archivos eliminados: ninguno. Sin cambios de lógica de negocio, SQL, identidad
UUID, permisos o servicios de aplicación.

## Límites y siguiente paso

- La revisión offscreen no sustituye aceptación en monitores físicos, distintos
  DPI y pantalla táctil, ni comparación contra una referencia visual aprobada.
- Los 14 literales Unicode preexistentes en 7 archivos siguen inventariados.
  Incluyen prefijos decorativos y símbolos de datos/estado; su adopción debe
  proteger las interacciones del módulo correspondiente. No se declara eliminada
  toda la iconografía legacy del ERP.
- La marca oficial corresponde a `BrandAssetProvider`; siguen faltando sus recursos.

Siguiente punto elegido por la numeración del documento: **6. BrandAssetProvider**.

## Revisión al retomar el punto 5 — 2026-09-13

La nueva selección de IconProvider detectó y corrigió dos fallos del binding:

- Al sustituir un icono, el nombre accesible generado quedaba asociado al anterior:
  `Contraer` seguía anunciado después de cambiar a `Expandir`. Ahora se actualiza
  cuando sigue siendo el nombre generado; los nombres personalizados antes o
  después del primer enlace se conservan.
- Un enlace creado o reemplazado sobre una etiqueta ya visible no seguía los
  cambios de pantalla hasta otro evento Show/ParentChange. Esto afecta al refresco
  de `KPICard.update()`. Ahora se conecta también al crear el binding y vuelve a
  rasterizar al cambiar el DPI del monitor.

Se agregaron **6 casos de prueba**. Antes de corregir, 4 fallaron y 2 aprobaron;
la ejecución final obtuvo **195 PASSED, 0 FAILED, 0 ERROR y 0 SKIPPED** en los
segmentos del proveedor, menús, tema, densidad, catálogo, guardrails, contratos
del shell y pruebas unitarias/de integración de Apariencia. La evidencia antes
y después está en el [manifiesto de esta revisión](evidence/icon_provider_phase_5/followup-validation.json).
Este resultado no se suma a los 385 casos históricos: existe solapamiento.

El auditor sigue registrando **0 infracciones nuevas, 0 huellas obsoletas y 159
ocurrencias preexistentes**. Compilación y `git diff --check` sin errores. No se
detectaron regresiones en los segmentos ejecutados. Los 210 PNG anteriores
conservan su condición de evidencia histórica; esta revisión no generó capturas
nuevas porque corrigió accesibilidad y ciclo de vida del binding. El cambio de
monitor se simuló con Qt real offscreen; falta aceptación con monitores físicos.

Archivos modificados en esta revisión: `frontend/desktop/components/icons.py`,
`tests/ui/test_icon_provider_runtime.py`,
`frontend/desktop/design_system/migration_guide.md`, este informe y la auditoría
general. Creados: manifiesto, logs y XML de la revisión en su directorio de
evidencia. Archivos eliminados: ninguno. La revisión permanece dentro del punto 5;
el siguiente punto de implementación continúa siendo BrandAssetProvider.

## Corrección de consumidores — 2026-09-14

El reporte del usuario sobre iconos repetidos reveló una omisión que la
validación del catálogo no cubría: los módulos declaraban identificadores
válidos pero no los pasaban al construir sus barras laterales. Se corrigieron
los 17 consumidores afectados y se agregó una protección contra esa omisión.
El [informe de iconos de módulos](module_sidebar_icons_fix.md) contiene el alcance,
las pruebas de rutas reales, la evidencia visual y el fallo legacy preexistente.
