# Punto 7 — Density profiles

Fecha: 2026-09-23. Implementación y validación automática completadas.

## Contrato

La terminal ofrece Compacta, Cómoda y Táctil en **Configuración → Apariencia →
Apariencia de esta terminal**. El cambio se aplica inmediatamente mediante
`ThemeManager`, se persiste en `QSettings` y se restaura antes del login.
Conserva el tema, valores, UUID, selección y navegación sin reconstruir páginas
ni consultar de nuevo al presentador. El catálogo administrativo sigue separado.
Táctil se recomienda para POS, Inventario, Recepción y Producción; navegar no
reemplaza la elección global del puesto. `NORMAL` se normaliza a Cómoda.

| Control | Compacta | Cómoda | Táctil |
|---|---:|---:|---:|
| Campo / botón | 34 | 42 | 52 |
| Fila de tabla | 32 | 42 | 52 |
| Opción lateral | 36 | 44 | 52 |
| Pestaña | 36 | 42 | 48 |
| Botón de icono | 32 | 42 | 48 |

Son píxeles lógicos Qt y mínimos canónicos; el contenido accesible puede requerir
más espacio. `themes/tokens.py` conserva la fuente única de estas medidas.

## Correcciones

- El toggle de `SideNav`, posicionado sin layout, reduce su geometría efectiva
  al volver de Táctil a Compacta y deja libre la primera opción.
- `StandardComboBox` aplica la densidad también a las filas de su popup mediante
  un delegate compartido; `StandardCheckBox` usa toda su superficie clicable.
- El QSS reserva el borde de selección de pestañas y el de foco de botones y
  booleanos. Los campos compensan el padding del borde de foco/error. Reaplicar
  el tema mientras hay foco ya no aumenta las alturas en dos o cuatro píxeles.
- El teclado integrado usa `IconButton` con la medida del perfil conservando
  su `QAction`. En campos numéricos vive sobre el control exterior para evitar
  recortes. Respeta RTL, botón de borrado, cursor, selección, validador y márgenes;
  desactivar o retirar el teclado restituye los márgenes originales.

No se modificaron reglas de negocio, schema, identidades, datos ni recursos de
marca. No se eliminaron archivos. Los cambios productivos de esta fase están en
`apariencia_page.py`, `selection_controls.py`, `side_nav.py`,
`virtual_keyboard.py` y `qss_builder.py`; se actualizaron las guías de adopción.

## Validación

**483 PASSED distintos, 1 FAILED, 0 ERRORS, 0 SKIPPED**. El manifiesto elimina
solapamientos entre segmentos; no suma resultados históricos de otras fases.

| Segmento | Passed | Failed |
|---|---:|---:|
| Regresión de apariencia, QSS y arquitectura | 271 | 1 |
| Densidad, selección, foco y regresión de controles | 175 | 0 |
| Teclado, campos especializados y búsqueda | 42 | 0 |
| Matrices visuales | 70 | 0 |

Se añadieron cinco archivos `test_density_*.py`,
`test_terminal_density_selector.py` y `test_keyboard_density_target.py`.
La protección reproduce cambios en vivo, restauración, clics en bordes,
teclado físico, perfiles sucesivos y reaplicación con foco. Los XML previos
documentan los defectos antes de corregirlos. `git diff --check` del alcance
terminó sin errores.

El fallo de `test_desktop_visual_debt_does_not_grow` ya existía: las páginas
`MeatProcessingSettingsPage` y `PricingSettingsPage` carecen de política explícita
de overflow. La auditoría conserva 622 archivos, 161 ocurrencias, 159 permitidas
y esas dos fuera del baseline. **Cero infracciones nuevas desde el inicio**;
no se amplió la allowlist.

Las 250 capturas cubren Claro/Oscuro a 1280×720, 1366×768, 1440×900, 1600×900 y
1920×1080: 30 de la misma página cambiando entre los tres perfiles y 220 de
galería, navegación, login, teclado y estados en Cómoda/Táctil. Se usan fuentes
reales de Windows y Qt offscreen. No hay baseline de píxeles aprobado ni prueba
física de pantalla táctil/multimonitor. El test del botón de teclado comprueba
la petición de apertura con `show()` interceptado porque offscreen activa las
ventanas Tool pese a `WindowDoesNotAcceptFocus`; la integración con el gestor de
ventanas del puesto queda para la validación física.

- [Visor de capturas](evidence/density_profiles_phase_7/index.html)
- [Resultados, auditoría y hashes](evidence/density_profiles_phase_7/validation.json)

Siguiente punto elegido por el usuario: **8. StandardWindow**.
