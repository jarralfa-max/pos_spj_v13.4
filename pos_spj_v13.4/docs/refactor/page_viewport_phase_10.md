# 10. PageViewport

Validación completada el **20 de octubre de 2026**. Alcance: infraestructura de
overflow y composición de páginas del shell. No acredita una migración funcional
completa de cada módulo ni una suite global sin fallos.

## Resultado

La cadena es `ApplicationWindow → ContentHost → PageViewport → PageStack → página
activa`. El cuerpo se expande al área disponible y ofrece scroll en ambos ejes
cuando su mínimo real no cabe. La cabecera, navegación y acciones permanecen
fuera del cuerpo desplazable mediante `ModuleLayout`, `StandardPage` y
`StandardDialog`.

Se corrigieron tres comportamientos reproducidos antes de modificar el código:

1. **Páginas ocultas agrandaban otras páginas.** En Precios, visitar una pestaña
   con mínimo 1800×1200 dejaba las barras activas al volver a una pestaña pequeña.
   `PageStack` calcula mínimos y altura dependiente del ancho exclusivamente con
   la página activa. Conserva la API, propiedad, índices y señales de Qt.
2. **El scroll se compartía entre rutas.** Una página nueva heredaba la posición
   de la anterior; regresar desde una página pequeña perdía la posición original.
   `PageViewport` recuerda los dos ejes por instancia en caché. Una instancia
   nueva comienza en el origen; la restauración espera el layout y respeta el
   nuevo rango si el contenido se redujo. Las referencias de la caché son débiles.
3. **Un formulario con scroll interno añadía 16 px de scroll externo.** Ocurría
   a 1280×720 en Cómoda/Táctil, en ambos temas. `StandardPage.heightForWidth()`
   reserva el mínimo real de cabecera y acciones, sin imponer la altura preferida
   del cuerpo que ya tiene desplazamiento.

El shell utiliza ahora el mismo `PageStack` público que los módulos; se retiró
su implementación privada duplicada. `WizardPage` también utiliza la política
de tamaño de la página activa.

## Archivos y adopción

Componentes: `frontend/desktop/components/page_viewport.py`, `page_stack.py`,
`pages.py` y `__init__.py`. Integración del shell:
`frontend/desktop/shell/application_shell/content_host.py`.

La adopción de `PageStack` comprende **17 módulos**: Activos, BI, Caja,
Configuración, CRM, Fidelidad, Finanzas, RR. HH., Inventario, Logística, Merma,
Procesamiento cárnico, Delivery, Precios, Productos, Compras y Transferencias.
Los cambios de adopción corresponden al contenedor de páginas; mantienen las
rutas y la carga existente. POS utiliza un cuerpo `QWidget` y conserva su
composición propia.

Se actualizaron los contratos del catálogo, la guía de migración y las guías
visuales. Se añadieron tres archivos de pruebas:

- `tests/ui/test_page_viewport.py`: navegación, posiciones independientes,
  navegación rápida, recreación, reducción de mínimos, crecimiento y eliminación
  de campos, acceso por Tab/Home/End y propiedad Qt al reemplazar/retirar contenido.
- `tests/ui/test_page_stack.py`: caché de Precios, mínimos activos e inactivos,
  contenido dinámico, eliminación de páginas, texto envuelto y pasos del wizard.
- `tests/ui/test_page_viewport_visuals.py`: formulario largo y tabla con scroll
  propio en cinco resoluciones, dos temas y tres densidades, incluidos cambios
  de apariencia sobre los mismos widgets.

No se eliminaron archivos de código por esta fase. No se cambiaron reglas de
negocio, consultas, esquema ni datos. El inventario exacto de fuentes y sus hashes
está en el [manifiesto](evidence/page_viewport_phase_10/validation.json).

## Verificación

| Segmento | Aprobadas | Fallos | Errores iniciales |
|---|---:|---:|---:|
| PageViewport, PageStack, matriz y ContentHost | 96 | 0 | 0 |
| Layouts, responsive, diálogos y shell UI | 213 | 20 | 0 |
| Workspaces e integración del shell | 219 | 2 | 12 |
| Guardrails visuales y separación de datos/UI | 28 | 2 | 0 |
| Revisión con temporales Qt y catálogo | 18 | 0 | 0 |

Resultados únicos, sustituyendo los errores de temporales por su repetición
exitosa: **550 PASSED, 24 FAILED, 0 ERROR y 0 SKIPPED**. Las filas de la tabla
incluyen pruebas repetidas; no deben sumarse como casos distintos.

Los **96 casos específicos pasan**. Las pruebas de protección iniciales
reprodujeron tres fallos de posición, dos de mínimos de páginas ocultas y cuatro
variantes visuales de scroll externo. Sus XML anteriores se conservan junto con
los posteriores.

### Fallos ajenos al componente y limitaciones

- **20 casos POS:** el test anterior espera cabecera visible y márgenes 20/16.
  La implementación actual oculta esa cabecera duplicada y usa márgenes de 4 px.
  No se alteró esa decisión ni se debilitó la expectativa del test en esta fase.
- **2 casos de rutas:** Productos contiene 14 opciones donde el test espera 7;
  Producción ya construye una página de resumen donde el test espera un placeholder.
- Estos **22 fallos** se reprodujeron cargando en memoria `PageViewport`, `pages`
  y `ContentHost` anteriores a la fase, desde `cebf67a7`, sin sobrescribir fuentes.
  Véase `viewport-20261020-prior-components.xml` en la evidencia.
- **2 guardrails globales:** hay 13 hallazgos fuera del baseline y una referencia
  obsoleta a `customers_crm/pages/_directory_base.py`. El análisis registra 104
  hallazgos totales y **cero en los archivos de alcance de esta fase**. No se amplió
  la allowlist. El detalle está en [audit.json](evidence/page_viewport_phase_10/audit.json).
- Los 12 errores de integración eran `PermissionError` al crear/listar temporales.
  Reaparecieron con `--basetemp` dentro del proyecto. Se resolvieron ejecutando
  esas pruebas con fixtures temporales respaldadas por `QTemporaryDir`, que
  heredan los permisos del workspace. Las pruebas y componentes productivos
  permanecieron iguales; la revisión aprobó los 14 casos de esos archivos y los
  4 del catálogo. Se conservan los logs de los intentos y el runner utilizado.

No se ejecutó toda la suite de backend: se seleccionaron los segmentos afectados
de UI, unitarios, integración y arquitectura. La suite global sigue teniendo
los fallos descritos.

## Evidencia visual y reproducción

[Galería de 30 capturas](evidence/page_viewport_phase_10/index.html): 1280×720,
1366×768, 1440×900, 1600×900 y 1920×1080, en Claro/Oscuro y Compacta/Cómoda/Táctil.
Se revisaron visualmente muestras de los extremos 1280×720 Táctil Claro y
1920×1080 Compacta Oscuro. Las aserciones geométricas cubren los 60 escenarios de
formulario y tabla, incluida la accesibilidad del último campo/celda y del pie.

Las capturas son de Qt **offscreen**, con fuentes reales y áreas de trabajo
simuladas. No son una comparación de píxeles con una referencia aprobada ni
sustituyen validación física de monitores, escalado DPI o gestos táctiles.

Desde el paquete interno, en PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:SPJ_PAGE_VIEWPORT_ARTIFACTS = Join-Path (Get-Location) 'docs/refactor/evidence/page_viewport_phase_10/visuals'
& '..\.venv\Scripts\python.exe' -m pytest tests/ui/test_page_stack.py tests/ui/test_page_viewport.py tests/ui/test_page_viewport_visuals.py tests/ui/shell/test_content_host.py tests/ui/shell/test_content_host_loading.py -q -p no:cacheprovider
```

Los XML, logs, auditoría, copias de los runners de contraste y hashes de fuentes
y capturas están en `docs/refactor/evidence/page_viewport_phase_10/`.
Las copias de runners `.py.txt` documentan las ejecuciones desde `.test_tmp/`.

Siguiente punto del orden solicitado: **11. Layout system**, conservando la
referencia de Precios para título y sidebar y revisando las diferencias
deliberadas del POS antes de modificar esa composición.
