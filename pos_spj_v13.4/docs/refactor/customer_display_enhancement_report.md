# Monitor del cliente — recuperación

## Proyección
CustomerDisplayQueryService conserva autorización y obtiene la venta canónica.
El cliente de integración aplica preferencias y layout antes de entregar datos
a QtCustomerDisplayGateway. No se replica el diálogo privado del cajero.
El contenido público sólo contiene artículos, cantidades/unidades, precios,
descuentos, subtotal/impuestos/total, nombre del cliente, puntos, báscula,
mensajes públicos y recursos de marca. No incluye PIN, autorización, CVV ni logs.

## Flujo
CART muestra la compra. Al iniciar pago se proyecta PAYMENT_PENDING; un fallo
muestra un mensaje público genérico. THANK_YOU sólo procede del estado COMPLETED
consultado después del caso de uso. El cambio se muestra si Configuración lo permite.
Se abre una nueva venta antes del aviso modal de ticket, manteniendo el agradecimiento
durante el intervalo configurado. Al vencer éste, o iniciar otro carrito, se retira.
La venta vacía se presenta como IDLE.

Cerrar la ventana pública detiene su temporizador, libera el gateway y actualiza
el botón del POS; volver a abrirla crea una ventana funcional. El ciclo está
cubierto por las pruebas de workspace. Los importes se formatean con dos
decimales en presentación y se conservan como Decimal en los contratos.

Puntos estimados usan el evaluador existente. Acreditados se consultan en
loyalty_transactions, EARN/BONUS disponibles de esa venta. Sin asiento confirmado
se muestra “Puntos pendientes”; durante agradecimiento se vuelve a consultar
a través del presentador. No se calculan puntos a partir del texto del total.

## Multimedia y marca
La publicidad configurada por AdvertisingQueryService puede ocupar una región
lateral durante CART sin sustituir importes. Cada cambio de artículo conserva
el medio actual. PAYMENT_PENDING y THANK_YOU suspenden esa región.
Imágenes se ajustan preservando proporción; video usa QtMultimedia en silencio
y playlist. Un error de medio muestra una indicación sin interrumpir el POS.
La configuración y el registro de impresiones siguen las rutas existentes.

TicketDesignQueryService resuelve la marca oficial de sucursal/empresa. Actualmente
se reutiliza su recurso de impresión; no se crea otro logo. Falta de archivo no
impide mostrar el agradecimiento. La captura de demostración usa un recurso del
repositorio y no prueba la configuración de marca en la base operativa.

## Configuración y migración
Preferencias de habilitación, pantalla física, fullscreen, detalles visibles,
publicidad durante venta, cambio y duración/mensajes viven en el catálogo gobernado.
Se pasan los ámbitos sucursal, empresa y estación disponibles en sesión.
Migración 344 añade TAX/POINTS/SCALE/PAYMENT/BRANDING a layouts existentes sólo si
faltan. Una sección desactivada sigue desactivada. El bootstrap se restringe a la
sucursal y utiliza códigos de estación únicos.

## Comprobaciones y límites
Pruebas de repositorios y gateway, filtrado por layout, aislamiento de sucursales,
migración repetible, contenido público, conservación de publicidad y peso actual.
Capturas de widgets reales: carrito, publicidad con imagen, pago, agradecimiento.
La captura de agradecimiento es una fixture de presentación; la confirmación
transaccional se verifica separadamente por integración.

No se ha probado reproducción de video con los codecs del equipo ni conexión/
desconexión física de un segundo monitor. Qt reubica la ventana ante cambios de
pantalla, y sin secundaria permite ventana normal. No se declara certificada
esa aceptación física.

## Corrección según referencias del usuario — 2026-10-18
El carrito, sus importes y las tarjetas de lectura actual/puntos se agrupan en la
columna izquierda; el medio publicitario ocupa la derecha. La finalización usa
`BrandColors.FOREST_GREEN`, icono vectorial del proveedor estándar, texto blanco
y puntos en dorado. El orden es agradecimiento, marca, pago confirmado, puntos
y despedida. Los estilos viven en el QSS global, no en el widget.

Se detectó que sólo se consultaban slots CART durante la venta. Ahora
`AdvertisingQueryService.resolve_display_ads` prioriza campañas CART activas y,
si no hay ninguna, reutiliza las campañas IDLE configuradas. Se conserva el
filtro de activación/vigencia/placement y la opción `ads_during_sale`; no se
habilitan campañas inactivas ni se reproducen anuncios durante el pago.
El inicio de cobro invalida la rotación para que pueda recargarse al regresar.

La integración verifica el archivo importado mediante Configuración, campaña
activa, asignación, resolución del archivo gestionado y render junto al carrito.
La decodificación de video con los codecs de producción sigue sin certificarse.

Validación: cuatro regresiones nuevas fallaron antes de corregirlas. La suite
ampliada obtuvo 159 passed y ocho errores de preparación por permisos de la
carpeta temporal de pytest. La repetición con permisos de ejecución adecuados
obtuvo 25 passed, incluyendo esos ocho casos. Presentación y reglas de ausencia
de SQL/commit en frontend: 33 passed. Los grupos se superponen.
Registros: `customer_display_followup_final.txt`,
`customer_display_followup_media_final.txt`, `customer_display_followup_layout_final.txt`.

Capturas finales: `evidence/customer_display_followup/cart_with_ad.png` y
`completion_forest.png`, generadas por `tests/visual/capture_customer_display_followup.py`.
Usan widgets reales con datos explícitos de presentación; el logo es un medio
de prueba, y el pago/puntos de esa captura no representan una operación real.
