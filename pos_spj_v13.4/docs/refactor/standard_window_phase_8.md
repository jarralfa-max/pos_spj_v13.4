# Punto 8 — StandardWindow

Implementación inicial: 2026-09-23. Revisión y correcciones: 2026-10-05.
Política canónica de ventanas, continuando tras
[Density profiles](density_profiles_phase_7.md).

## Revalidación del 4–5 de octubre de 2026

**105 PASSED distintos, 0 FAILED, 0 ERRORS, 0 SKIPPED** en el segmento
afectado. Se corrigieron dos problemas de geometría en `StandardWindow`:

- Al cambiar de monitor y reducir el área disponible, el marco podía quedar
  dos píxeles fuera del escritorio. El ajuste usa `resize()` y `move()` para
  posicionar el marco, sin sumar manualmente un desplazamiento de decoraciones.
- Los movimientos incrementales hacia otro monitor se devolvían al borde del
  anterior antes de cambiar de pantalla. Un marco de tamaño válido puede ahora
  repartirse entre monitores conectados durante el traslado. Se mantiene la
  recuperación de ventanas demasiado grandes o completamente fuera del escritorio.

La reproducción con dos monitores contiguos y 120 movimientos de 10 px terminaba
antes en x=476, dentro del monitor izquierdo; después termina en x=1690, en el
derecho. Es una simulación de movimientos incrementales, no una certificación
de arrastre nativo ni de hardware multimonitor.

Las cinco pruebas nuevas cubren cruces por los cuatro bordes y recuperación con
dos monitores. La primera ejecución reprodujo cuatro fallos. El segmento
completo terminó inicialmente con 103 aprobadas y dos comprobaciones demasiado
estrictas de coordenadas negativas: Qt ajusta algunos píxeles de borde. Esas
pruebas ahora verifican el comportamiento requerido —marco repartido entre
pantallas y centro todavía en la anterior— sin exigir coordenadas de plataforma
idénticas. Las 18 pruebas finales de geometría pasan; las otras 87 pruebas
aprobadas conservan el mismo código de producción. El informe consolida cada
caso por su última ejecución, sin contar repeticiones.

Se verificaron ventanas del shell, navegación, carga, servicios, mensajes de
estado, cierre coordinado, composición con módulos reales, arquitectura y la
matriz visual de cinco áreas disponibles, Claro/Oscuro y tres densidades.
Hay **30 capturas nuevas**, con fuentes reales y configuraciones aisladas.
Se inspeccionaron muestras; no son una comparación con píxeles aprobados.
Para la aceptación en equipo real queda comprobar el arrastre entre monitores
con distinto DPI, la desconexión del segundo monitor y maximizar/restaurar
conservando una captura pendiente y el mensaje de estado.

El arranque real (`frontend/desktop/app.py`) y la galería usan `StandardWindow`.
`CustomerDisplayWindow` mantiene su ventana especializada para el monitor del
cliente; `VirtualKeyboard` pertenece al contrato de diálogos y herramientas.
Esta revisión no modifica esos consumidores ni reglas de negocio.

La auditoría global registra 132 ocurrencias: 128 permitidas y cuatro fuera del
baseline, ya presentes antes de esta revisión (tabla nativa en `dialogs_plan`,
overflow de configuración de Producción y Pricing, y `PurchaseUnitsDialog`).
**Cero infracciones nuevas en el componente modificado**. La allowlist no se
amplió. Estos resultados no declaran verde la suite completa del repositorio.

Archivos modificados en esta revisión: `components/standard_window.py`,
`tests/ui/test_standard_window_geometry.py`, este informe y las guías de
adopción/visuales. Archivos eliminados: ninguno. Compilación y `git diff --check`
del alcance sin errores. Se conservó el trabajo previo del punto 11 y los
cambios de otros módulos que ya estaban en el árbol.

- [Capturas de esta revisión](evidence/standard_window_phase_8/revalidation_20261004/index.html)
- [Resultados por ejecución, auditoría y hashes](evidence/standard_window_phase_8/revalidation_20261004/validation.json)
- [JUnit final de geometría](evidence/standard_window_phase_8/revalidation_20261004/geometry-final.xml)

Comando para repetir el segmento desde el paquete interno:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_standard_window_geometry.py tests/ui/test_standard_window_visuals.py tests/ui/shell/test_application_window.py tests/ui/shell/test_application_window_sidebar.py tests/ui/shell/test_application_window_loading.py tests/ui/shell/test_application_window_shutdown.py tests/ui/shell/test_application_window_background.py tests/ui/shell/test_status_bar.py tests/architecture/test_standard_window_ownership.py tests/unit/shell/shutdown/test_shutdown_coordinator.py tests/integration/shell/test_desktop_shell_window_composition.py -q -p no:cacheprovider
```

## Comportamiento

`StandardWindow` es el único propietario de `QMainWindow` en el frontend.
`ApplicationWindow` hereda esa política y mantiene sus componentes de shell,
rutas, contexto, servicios y cierre coordinado.

- Título predeterminado: JUANIS · SPJ ERP / POS; el constructor admite un título.
- Icono oficial mediante `BrandAssetProvider`, sin modificar recursos de marca.
- Tamaño inicial de hasta 1440×900 y mínimo nominal de 640×480. Una pantalla
  menor reduce el mínimo al espacio real y una mayor recupera el mínimo nominal.
- El límite usa `availableGeometry()` del monitor actual, descontando bordes y
  barra de título. Ajusta tamaño y posición, incluso con coordenadas negativas.
- Sigue `screenChanged` y `availableGeometryChanged`, desconectando el monitor
  anterior. Comprueba otra vez la geometría una vez que Qt termina de mostrar
  o restaurar la ventana y estabiliza sus decoraciones nativas.
- Maximizar, minimizar y pantalla completa conservan el estado administrado
  por Qt; al restaurar se vuelve a comprobar el área disponible.
- Tema y densidad provienen del `QApplication`. Conserva estado y contenido sin
  aplicar QSS local ni restablecer geometría válida al cambiar apariencia.
- Conserva la barra de estado instalada por el shell. Un mensaje previo a la
  primera apertura ya no se superpone con el indicador de conectividad; este
  reaparece al limpiar el mensaje y conserva su estado.

No se añadió persistencia de geometría ni se alteraron reglas de negocio,
permisos, SQL, schema, navegación, procesos de cierre o identidad UUID.

## Archivos y protección

Producción: `components/standard_window.py` y
`shell/application_shell/status_bar.py`. Se actualizó la descripción del
contrato en `component_contracts.py` y las guías visuales/de adopción.

Tests nuevos: `test_standard_window_geometry.py`,
`test_standard_window_visuals.py` y `test_standard_window_ownership.py`.
El guardrail impide crear o heredar `QMainWindow` fuera del propietario y
configurar iconos de ventana dentro de módulos.

Se amplió `test_status_bar.py` y se ajustaron las cuatro matrices compartidas
de galería, navegación y selectores de tema/densidad. Ahora modelan el área disponible
de cada monitor: antes redimensionaban la ventana por encima del monitor
sintético de 800×600 de offscreen. El marco completo forma parte de la resolución
comprobada. No se eliminaron archivos ni se amplió la allowlist.

## Validación inicial del 23 de septiembre

**292 PASSED distintos, 1 FAILED, 0 ERRORS, 0 SKIPPED**.

| Segmento | Passed | Failed |
|---|---:|---:|
| Geometría, branding, shell, contratos y arquitectura | 202 | 1 |
| StandardWindow en cinco áreas, dos temas y tres perfiles | 30 | 0 |
| Matrices compartidas con la política de monitor actualizada | 60 | 0 |

Los siete casos iniciales reprodujeron seis fallos antes del cambio. La
protección final incluye trece casos de geometría, reapertura, cambio de monitor,
desconexión del anterior, estados de ventana, mensajes y apariencia en vivo.
La superposición de estado también tiene un fallo previo reproducido.

El único fallo final es el guardrail ya existente por
`MeatProcessingSettingsPage` y `PricingSettingsPage`, sin overflow explícito.
La auditoría mantiene 622 archivos y 161 ocurrencias: 159 permitidas y esas
dos fuera del baseline. **Cero infracciones nuevas** durante esta fase.

Hay **280 capturas**: 30 de la ventana/shell en Compacta, Cómoda y Táctil;
200 compartidas de galería y navegación; 30 del selector de densidad y 20 del
selector de tema. Cubren
Claro/Oscuro y áreas disponibles de 1280×720, 1366×768, 1440×900, 1600×900 y
1920×1080. Las imágenes muestran el contenido; las aserciones incluyen también
el marco nativo. Se inspeccionaron capturas representativas, sin aprobación
individual ni comparación con un baseline de píxeles aprobado.

Las pruebas usan Qt offscreen, fuentes reales de Windows, presentadores de
prueba y configuraciones aisladas. Los monitores y sus cambios de área se
simulan; no se certifica aquí hardware multimonitor ni cambios físicos de DPI.
La compilación y `git diff --check` del alcance terminaron sin errores.

Los enlaces reproducibles vigentes están en la revalidación al inicio de este
informe. Los totales de esta sección describen la ejecución histórica.

Siguiente punto: **9. StandardDialog**.
