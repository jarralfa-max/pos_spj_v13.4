# Guía de adopción del Design System

Antes de intervenir, leer `docs/skills/SPJ_REFACTOR_SKILL.md` y
`docs/refactor/module_ui_ux_migration_template.md`. Mantener el trabajo dentro del
paquete real `pos_spj_v13.4/`; no crear otro frontend en la raíz externa.

## Ruta de adopción

1. Inventariar páginas, diálogos, acciones, captura, permisos y fuentes de datos
   de una ruta real. Consultar las infracciones exactas de
   `tests/architecture/design_system_debt_baseline.json`.
2. Proteger navegación, señales, validación y operaciones antes de cambiar una
   estructura. Las lecturas pertenecen a QueryService y las mutaciones a UseCase.
3. Elegir un layout canónico. Conservar una frontera de desplazamiento del
   cuerpo y acciones alcanzables. Revisar el padre antes de anidar scroll.
4. Reemplazar controles locales por `frontend.desktop.components`, conservando
   los contratos del presentador. Eliminar el código sustituido cuando su ruta
   nueva esté probada; no duplicar componentes.
5. Pasar apariencia a tokens y QSS central. Aplicar iconos con
   `IconProvider.bind(widget, Icons.…)`, texto de estado y nombres accesibles.
6. Validar Claro/Oscuro y las tres densidades. Probar la matriz Cómoda/Táctil de
   cinco resoluciones, Tab, Escape, formularios extensos, tablas y hardware.
7. Retirar únicamente las huellas resueltas y ejecutar guardrails. No ampliar el
   baseline para ocultar infracciones nuevas.
8. Documentar resultados y pendientes. Marcar `MIGRATED` solo cuando la ruta
   productiva complete el checklist funcional y visual.

## Catálogo disponible

El inventario verificable está en `component_contracts.py`; la galería permite
cambiar tema y densidad en ejecución.

| Necesidad | Componentes |
|---|---|
| Shell | `StandardWindow`; `ApplicationWindow`, `TopBar`, `ContentHost`, `NotificationDrawer`, `StatusBar` en `shell/` |
| Página | `StandardPage`, `ScrollablePage`, `WorklistPage`, `DashboardPage`, `FormPage`, `TabbedPage`, `SplitPage`, `MasterDetailPage`, `POSPage`, `WizardPage`, `PageViewport` |
| Jerarquía | `PageHeader`, `Breadcrumbs`, `ContextBar`, `Toolbar`, `FilterBar`, `Tabs`, `TabBar` |
| Navegación | `GlobalSidebar`/`AppSidebar`, `SideNav`/`ModuleSidebar`, `NavGroup`, `NavItem` |
| Datos | `KPIBar`, `KPICard`, `KPIDTO`, `StandardCard`, `ChartCard`, `DashboardGrid`, `StandardTable`, `ColumnSpec` |
| Acciones | `PrimaryButton`, `SecondaryButton`, `GhostButton`, `DangerButton`, `IconButton` |
| Captura | `StandardLineEdit`, `SearchInput`, `PasswordInput`, `MoneyInput`, `IntegerInput`, `DecimalInput`, `WeightInput`, `PhoneInput`, `EmailInput`, `DateInput` |
| Selección | `StandardComboBox`, `StandardCheckBox`, `StandardRadioButton`; búsqueda especializada de entidades |
| Feedback | `StatusBadge`, `StateWidget`, `LoadingState`, `EmptyState`, `ErrorState`, `Toast` |
| Diálogo | `StandardDialog`, `ConfirmationDialog`, `DestructiveConfirmationDialog`, `FormDialog` |
| Recursos | `IconProvider`, `BrandAssetProvider`, `VirtualKeyboard`, `KeyboardAwareInput` |

No cambiar dinero a float para ordenar una tabla. `StandardTable` usa Decimal al
ordenar números y conserva el UUID en todas las celdas de cada fila.
Persistir anchos/visibilidad con `settings` y `settings_key` del usuario/terminal.

### Iconos en controles existentes

```python
from frontend.desktop.components.icons import IconProvider, Icons

IconProvider.bind(button, Icons.PRINT)  # QPushButton o QToolButton
IconProvider.bind(action, Icons.EXPORT)  # QAction, también dentro de un menú
IconProvider.bind(status_label, Icons.WARNING, state="warning", size=24)
```

El binding mantiene tema, modo deshabilitado y DPI de las etiquetas; conserva
los nombres accesibles personalizados y actualiza los que generó al cambiar el
icono. También sigue el monitor al enlazar de nuevo un control ya visible, por
ejemplo al refrescar un KPI. En botones `primary` y `danger`, el estado
normal se adapta al color inverso del relleno. No copiar un QIcon a una acción
de un menú cuando se necesita actualizarlo en caliente: enlazar esa acción.

`IconProvider.icon()` devuelve un QIcon vectorial del tema solicitado/actual;
se usa para las filas cuyos hosts ya actualizan iconos al cambiar tema.
`IconProvider.pixmap()` genera una imagen con tamaño lógico y DPR explícito.
Ambos son instantáneas; para widgets vivos se prefiere `bind()`.

Usar identificadores del catálogo para navegación, cabeceras y KPIs. Añadir un
concepto nuevo exige su nombre español y un vector; el guardrail
`test_icon_catalog.py` impide referencias desconocidas. Los identificadores
externos desconocidos producen aviso en el log y un símbolo de archivo de
respaldo; no deben utilizarse como contrato de un módulo.

Cada opción del sidebar debe transmitir el icono de su definición de ruta:

```python
nav.add_group(group, icon=GROUP_ICONS[group])
nav.add_section(route.label, icon=route.icon)
```

Tener el identificador en el catálogo no basta: omitirlo al construir la fila
repite el icono de inicio. Las listas especializadas de navegación reutilizan
`SideNav` para refrescar sus iconos al cambiar de tema. El guardrail comprueba
también las llamadas heredadas y rechaza iconos omitidos, nulos o vacíos.

```python
from frontend.desktop.components import FormPage, MoneyInput, PrimaryButton

page = FormPage(title="Capturar importe")
amount = MoneyInput()
page.add_content(amount)
save = PrimaryButton("Guardar")
page.add_action(save)
# Conectar save al presentador existente; no ejecutar SQL en el callback.
```

## Verificación reproducible

Desde el paquete interno en PowerShell, usando el entorno de la raíz externa:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& '..\.venv\Scripts\python.exe' -m pytest tests/architecture/test_design_system_guardrails.py tests/architecture/test_theme_contrast.py -q -p no:cacheprovider
& '..\.venv\Scripts\python.exe' -m pytest tests/ui/shell tests/ui/test_theme_density_icons.py tests/ui/test_responsive_components.py -q -p no:cacheprovider
$env:SPJ_UI_VISUAL_ARTIFACTS = Join-Path (Get-Location) 'docs/refactor/evidence/design_system_ui'
& '..\.venv\Scripts\python.exe' -m pytest tests/ui/test_design_system_visual_matrix.py tests/ui/test_design_system_navigation_visuals.py -q -p no:cacheprovider
```

Para la galería interactiva, usar una terminal sin `QT_QPA_PLATFORM=offscreen` y
ejecutar `python -m frontend.desktop.design_system.component_gallery` desde el
paquete interno. El backend offscreen no muestra una ventana de usuario.

Ejecutar además `tests/architecture`, `tests/unit` y `tests/integration` según el
skill. Registrar los fallos y errores de colección; los segmentos UI aprobados
no equivalen a una suite global verde.

## Pendientes de integración global

Quedan pantallas y diálogos por adoptar. El drawer presenta notificaciones
mediante su contrato UI; falta conectarlo a la fuente productiva. Los estados
visuales de bloqueo/vencimiento no implementan por sí solos esos flujos de sesión.
Faltan los archivos oficiales de branding. Consultar el
[informe vigente](../../../docs/refactor/global_ui_ux_design_system_audit.md)
antes de declarar la estandarización terminada.
