# Punto 8 — StandardWindow

Fecha: 2026-09-23. Política canónica de ventanas y validación automática
completadas, continuando tras [Density profiles](density_profiles_phase_7.md).

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

## Validación

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

- [Visor de capturas](evidence/standard_window_phase_8/index.html)
- [Resultados, auditoría y hashes](evidence/standard_window_phase_8/validation.json)

Siguiente punto: **9. StandardDialog**.
