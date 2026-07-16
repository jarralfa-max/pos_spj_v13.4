# HR UI/UX Enterprise Audit

## Estado

MIGRATED — primera pasada enterprise aplicada sobre el módulo canónico `frontend/desktop/modules/hr`.

## Componentes globales creados

| Componente | Archivo | Estado |
| --- | --- | --- |
| StandardButton | `frontend/desktop/components/buttons.py` | MIGRATED |
| PageHeader | `frontend/desktop/components/page_header.py` | MIGRATED |
| Icons | `frontend/desktop/components/icons.py` | MIGRATED |
| Tooltip | `frontend/desktop/components/tooltip.py` | MIGRATED |
| KPICard / KPIDTO | `frontend/desktop/components/kpi_card.py` | MIGRATED |
| KPIBar | `frontend/desktop/components/kpi_bar.py` | MIGRATED |
| FilterBar | `frontend/desktop/components/filter_bar.py` | MIGRATED |
| StandardTable | `frontend/desktop/components/tables.py` | MIGRATED |
| StandardCard / SectionCard / SummaryCard / AlertCard / ChartCard | `frontend/desktop/components/cards.py` | MIGRATED |

## Páginas migradas

| Página | Cambios | Estado |
| --- | --- | --- |
| Overview | PageHeader + KPIBar/KPIDTO; sin grid KPI manual. | MIGRATED |
| Employees | PageHeader + FilterBar + StandardTable. | MIGRATED |
| Attendance | PageHeader + acciones estándar + StandardTable. | MIGRATED |
| Leave | PageHeader + StandardTable. | MIGRATED |
| Payroll | PageHeader + StandardTable. | MIGRATED |
| Schedules | PageHeader + StandardTable. | MIGRATED |
| Evaluations | PageHeader + EmptyState. | MIGRATED |
| Settings | PageHeader + EmptyState. | MIGRATED |

## Reporte obligatorio

1. Componentes globales creados: StandardButton, PageHeader, Icons, Tooltip, KPICard, KPIBar, FilterBar, StandardTable y cards base.
2. Componentes globales modificados: `frontend/desktop/components/__init__.py` exporta los componentes enterprise.
3. Páginas migradas: Overview, Employees, Attendance, Leave, Payroll, Schedules, Evaluations y Settings.
4. KPI eliminados: cards KPI manuales de Overview reemplazadas por KPIBar/KPIDTO.
5. Cards eliminadas: QWidgets con `component=kpiCard` reemplazados por KPICard canónica.
6. Gráficas migradas: no aplica en esta pasada; RRHH no tenía gráficas activas.
7. Tooltips añadidos: PageHeader, StandardButton y KPICard usan Tooltip canónico.
8. Tooltips eliminados por uso incorrecto: no se detectaron tooltips críticos mal usados en esta pasada.
9. Estilos inline eliminados: no se introdujo `setStyleSheet` ni colores locales.
10. Imports legacy eliminados: las páginas operativas dejan de construir tablas/botones primarios manuales.
11. Tokens añadidos: no se agregaron tokens nuevos; se reutilizó `DesktopSpacing`.
12. Reglas QSS añadidas: no se agregó QSS local; los componentes exponen objectName/properties.
13. Formatters añadidos: no aplica en esta pasada.
14. Iconos migrados: HR usa `Icons.*` semántico en PageHeader/KPI.
15. Estados de vista añadidos: se preservan LoadingState/EmptyState/PaginationBar existentes.
16. Tests creados: guardrails enterprise en `tests/architecture/test_hr_architecture.py`.
17. Tests ejecutados: HR architecture, HR unit/integration/e2e y compileall frontend HR.
18. Resoluciones verificadas: el módulo mantiene minimum size y componentes sin anchos fijos grandes; validación visual manual pendiente.
19. Temas verificados: no hay QSS local ni colores hardcodeados en páginas HR; queda delegado al tema global.
20. Allowlist reducida: no se amplió allowlist.

## Enterprise UI/UX master prompt follow-up

| Elemento anterior | Reemplazo canónico | Estado |
|-------------------|--------------------|--------|
| QLineEdit horario | TimeInput / TimeRangeInput | MIGRATED |
| combo sin búsqueda | SearchableComboBox | MIGRATED |
| diálogo disperso | StandardDialog | MIGRATED |
| estado de error local | ErrorState | MIGRATED |
| estado sin permiso local | PermissionState | MIGRATED |
| estado offline local | OfflineState | MIGRATED |
| estado stale local | StaleState | MIGRATED |
| decimal libre | DecimalInput | MIGRATED |
| gráfica PyQt | HtmlChartView | MIGRATED |
| grid dashboard manual | DashboardGrid | MIGRATED |

### Reporte adicional obligatorio

1. Componentes globales creados: `TimeInput`, `TimeRangeInput`, `MonthInput`, `SearchInput`, `SearchableComboBox`, `DecimalInput`, `StandardDialog`, estados de vista, `HtmlChartView`, `DashboardGrid`, `FormField` e inline feedback.
2. Componentes globales modificados: `frontend.desktop.components.__init__` exporta los contratos canónicos.
3. Inputs migrados: hora, rango horario, mes contable, decimal y selector searchable quedan disponibles como contratos compartidos.
4. KPI migrados: se conserva `KPICard` y `KPIBar` como única ruta canónica existente.
5. Cards migradas: se conserva `cards.py` como única ruta canónica existente.
6. Charts migradas: se agrega `HtmlChartView` con contrato `renderer=html_js` y resumen accesible.
7. Tablas migradas: se conserva `StandardTable` como contrato canónico para RRHH.
8. Tooltips añadidos: los inputs nuevos usan `Tooltip.attach`.
9. Tooltips corregidos: no se agrega un sistema paralelo.
10. Horarios migrados a TimeInput: el contrato `HH:mm` queda protegido por tests.
11. QLineEdit incorrectos eliminados: los nuevos horarios no usan `QLineEdit` ni `.text().strip()`.
12. Estilos inline eliminados: los componentes nuevos solo asignan `objectName` y propiedades semánticas.
13. Tokens añadidos: no se añadieron nuevos tokens en esta iteración; los componentes quedan listos para QSS global.
14. QSS añadido: no se añadió QSS local por cumplimiento de fuente única visual.
15. Formatters añadidos: no aplica en esta iteración de componentes de captura.
16. Iconos migrados: se mantiene `Icons` como catálogo canónico.
17. Estados añadidos: `ErrorState`, `PermissionState`, `OfflineState`, `StaleState`.
18. Tests creados: tests unitarios de componentes enterprise y tests de arquitectura de contratos UI.
19. Tests ejecutados: compileall, unitarios de componentes, arquitectura HR/UI, suite HR afectada y `git diff --check`.
20. Resoluciones verificadas: no se ejecutó validación visual manual por entorno headless.
21. Temas verificados: contratos sin QSS local; validación visual queda pendiente en entorno interactivo.
22. Allowlists reducidas: no se agregaron allowlists.
23. Archivos legacy eliminados: no se eliminaron archivos legacy en esta iteración incremental.
