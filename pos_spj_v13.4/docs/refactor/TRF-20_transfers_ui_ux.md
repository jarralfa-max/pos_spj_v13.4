# TRF-20 — UI/UX enterprise de Transferencias

## Workspace canónico

`TransfersView` ofrece una sola navegación interna de quince rutas, crea páginas
bajo demanda y conserva una única instancia por ruta. La visibilidad depende del
catálogo granular de permisos y los badges llegan precalculados desde backend.

Todas las páginas usan `PageHeader`, botones factory, `SearchInput`,
`SectionCard` y `StandardTable`. Resumen usa `KPIBar` con máximo seis métricas;
Análisis usa `ChartCard` y `HtmlChartView`. Ninguna pantalla ejecuta SQL, accede a
repositorios, calcula KPIs o define QSS/colores locales.

## Responsive y accesibilidad

- El workspace conserva sidebar acotado y contenido flexible desde 960×600,
  cubriendo la ventana operativa objetivo de 1366×768.
- Headers y mensajes admiten texto multilínea; tablas incluyen tooltips y
  navegación por teclado.
- Sidebar, búsquedas, tablas y gráfica tienen nombres accesibles y tooltips.
- `KPIBar` reorganiza automáticamente sus tarjetas según ancho disponible.
- `HtmlChartView` ofrece alternativa tabular cuando WebEngine no está disponible.

## Diálogos

Solicitud, aprobación, picking y recepción derivan de `FormDialog` y reutilizan
`SearchInput`, `BarcodeInput` y `DecimalInput`. Los demás workflows especializados
usan estas bases sin estilos, SQL ni reglas de dominio dentro del diálogo.
