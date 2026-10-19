# Validación visual del POS

## Método
`tests/visual/capture_sales_recovery.py` crea ApplicationWindow, GlobalSidebar,
ContentHost y SalesPosWorkspace reales. Las ventas y descuentos pasan por casos
de uso con SQLite en memoria. Se conservan cinco líneas cuya suma es 6.500 kg;
el indicador recibe una lectura simulada independiente de 0.850 kg.

Qt usa offscreen. Se cargan fuentes Segoe UI de Windows para que las capturas
incluyan texto real. Se simula únicamente el área disponible del monitor, porque
offscreen informa 800×600. No se sustituye la distribución ni los widgets.
Las dimensiones indicadas son área cliente lógica, sin marco nativo/taskbar.
Esto verifica geometría del shell; no equivale a aceptación en monitores físicos.

## Matriz
1280×720, 1366×768, 1600×900 y 1920×1080; claro y oscuro; comfortable y touch.
16 combinaciones por factor DPI. Los JSON registran tamaño solicitado/real,
área del módulo, altura de tres filas, viewport, scroll externo y posición de
los botones respecto al área visible del ContentHost.

La aserción exige: tamaño real igual al solicitado; tres filas completas;
sin scroll vertical del módulo o shell ni horizontal del shell; Cobrar, Suspender,
Reanudar y Cancelar completamente dentro del viewport.
El catálogo y el carrito conservan su propio scroll, necesario para más artículos.

## Evidencias
En `docs/refactor/evidence/sales_recovery/dpi_1/`:
- pos_empty.png: vacío.
- pos_{tema}_{densidad}_{resolución}.png: cinco líneas, descuento y báscula simulada.
- inventory_states.png: tarjetas con estados de inventario de presentación.
- customer_cart.png, customer_payment.png, customer_thanks.png, customer_ad.png.
- geometry.json: mediciones reproducibles.

`dpi_1.5/` repite la matriz con QT_SCALE_FACTOR=1.5.
Las fixtures de inventario y agradecimiento están identificadas en el script:
son widgets de producción con datos de prueba, no un mockup de diseño.

## Hallazgos
La primera captura sin fuentes resultó ilegible y mostró medidas de texto
incorrectas: se corrigió el entorno de captura y se regeneró la evidencia.
El primer intento también quedó limitado por la pantalla virtual 800×600;
la simulación de área de pantalla corrigió ese límite del harness.
La evidencia vigente incluye texto y geometría del shell completo.
Se revisó visualmente el caso 1280×720 táctil: tres filas completas y acciones
de cobro/suspensión/reanudación/cancelación visibles, sin desplazar la página.

La comprobación de los botones detectó un recorte en oscuro/táctil a 1280×720,
incluido DPI 1.5: Qt conservaba geometría anterior al cambiar las métricas del
tema. Se invalidan y activan los layouts, y se aplica el rectángulo actual del
checkout tras actualizar el splitter. La captura DPI 1.5 corregida se revisó
visualmente; los cuatro botones quedan completos y se conservan tres filas.
Los resultados reproducibles están en `sales_recovery_visual_dpi100_results.txt`
y `sales_recovery_visual_dpi150_results.txt`.

El monitor público presenta importes con dos decimales y tipografía del tema;
al cobrar o agradecer se oculta la región del carrito para evitar espacio vacío.

La comparación con main es funcional/estructural (auditoría adjunta); no se afirma
comparación pixel a pixel contra una aplicación legacy ejecutada.

## Reproducción
Desde el paquete real, con el Python del entorno:
`../.venv/Scripts/python.exe -m tests.visual.capture_sales_recovery`.
Para alta densidad, establecer QT_SCALE_FACTOR=1.5 antes de iniciar otro proceso.
Las pruebas no leen datos operativos.

## Referencias del usuario — seguimiento 2026-10-18
Las capturas finales del monitor están en `evidence/customer_display_followup/`:
carrito e indicadores a la izquierda, medio a la derecha y finalización verde
bosque. Se revisaron ambas imágenes renderizadas, incluido el icono vectorial
de confirmación y el orden pago/puntos/despedida. Son fixtures de presentación.
La integración con los archivos de Configuración se verifica por separado.

Se regeneró también la matriz de 16 geometrías del shell a DPI 1.5, con sus
aserciones aprobadas (`customer_display_followup_visual150.txt`).
`pos_sale_discount.png` documenta el descuento de venta dentro del carrito.
