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

## Diagnóstico de la instalación real — 2026-10-19
Tras el nuevo reporte se abrió la base fuente mediante SQLite `mode=ro` y se
consultaron únicamente configuración de campañas, asignaciones y medios.
La causa efectiva no era la carga ni el escalado de imágenes:

- Los contenidos «Prom», «venta» y «22» tienen archivo gestionado existente;
  Qt QImage abre los tres correctamente.
- «Dic» figura ACTIVE, pero terminó el 2026-09-25 y está asignada a un slot
  THANK_YOU. No es elegible para venta/reposo.
- «mon» está DRAFT y sin asignación.
- «venta» no tiene campaña. Resolver IDLE o CART devuelve una tupla vacía.
- No hay override guardado de `customer_display.ads_during_sale`.

La prueba anterior con una campaña artificial correctamente configurada no
reproducía estos datos. Se añadió una regresión de campaña vencida/modo incorrecto
y borrador sin asignación; falló antes de implementar el diagnóstico.
Configuración ahora muestra por campaña los impedimentos y los pasos necesarios,
mediante AdvertisingQueryService, sin SQL en widgets ni activaciones automáticas.
La ventana pública no expone detalles internos de configuración.

La base operativa sigue sin modificaciones. Publicar requiere elegir el contenido
y completar su vigencia, aprobación/activación y asignación mediante los casos
de uso existentes. La elección de contenido se consultó al usuario.
Resultados: `customer_display_config_diagnostic_results.txt` y
`customer_display_config_diagnostic_ui_results.txt`.

## Preparación del contenido elegido — 2026-10-20
El usuario eligió «22», de la campaña «mon». Se verificó que su vigencia había
terminado el 2026-10-19. Mediante los casos de uso existentes se conservó su
inicio, se eliminó el término vencido (sin fecha de finalización), se creó el
slot activo `PUBLICIDAD-CARRITO` en modo CART y se envió «mon» a aprobación.
La campaña está PENDING_APPROVAL; no se ha publicado ni asignado.

La política de dominio exige un segundo revisor distinto del creador y el
presenter exige sesión autenticada para aprobar/activar. No se suplantaron
usuarios ni se modificó esa política. Paso pendiente en Configuración >
Pantalla del cliente: un segundo usuario autorizado selecciona «mon», pulsa
Aprobar y Activar; después, en Asignaciones, vincula «mon» con
`PUBLICIDAD-CARRITO`.

Evidencia anterior/posterior en
`evidence/customer_display_followup/mon_before_preparation.json` y
`mon_after_preparation.json`. Sólo se modificaron la programación/estado de
«mon» y el nuevo slot; los medios y otras campañas no se modificaron.
Una lectura posterior mediante AdvertisingQueryService confirma que los únicos
impedimentos de «mon» son NOT_ACTIVE y UNASSIGNED; CART aún devuelve cero anuncios.

`mon_22_preview.png` en esa carpeta muestra el archivo real seleccionado
(logotipo JUANIS) con el widget de producción y datos de carrito de demostración.
Es una vista previa local, no una campaña publicada ni una venta real.
Validación del ciclo de campañas y resolución: 32 passed, 0 failed, 0 skipped,
en `mon_publication_preparation_tests.txt`. No se modificó código de aplicación
en esta preparación ni se certificó el monitor físico.

## Reproducción MP4 en Windows — 2026-10-21

Se reprodujo el error reportado `DirectShowPlayerService::doRender` con
`0x80040266` sobre el archivo real gestionado
`01a15cfa-f7de-7ad4-ad3a-2cafbaa335f1.mp4` (6 201 045 bytes).
Microsoft identifica el código como `VFW_E_NO_TRANSPORT`: los filtros no pueden
conectarse por incompatibilidad de transporte
([documentación](https://learn.microsoft.com/en-us/windows/win32/directshow/error-and-success-codes)).

La ventana construía `QMediaPlayer` con el requisito `VideoSurface`, aunque su
salida es `QVideoWidget`. En este entorno, ese requisito seleccionaba
`DirectShowPlayerService` incluso al preferir Media Foundation. La comparación
en procesos separados verificó cero fotogramas y el error original con DirectShow;
sin el requisito de superficie y con Media Foundation, el mismo archivo produjo
fotogramas de 720 × 1280 sin errores (duración detectada: 20 011 ms).

La ventana ahora prefiere `windowsmediafoundation` en Windows, respetando una
preferencia explícita de entorno, y construye el reproductor sin `VideoSurface`.
Se conservan QVideoWidget, reproducción silenciada, playlist en bucle y parada
al entrar al cobro. No se instalaron códecs ni se convirtió o sustituyó el video.
Se corrigió además el comentario de formatos admitidos: una extensión admitida
no garantiza disponibilidad de todos sus códecs.

Dos regresiones fallaron antes del cambio; después pasaron 23 pruebas, incluidas
ventana, integración del monitor y restricciones de SQL/transacciones en UI.
El script manual `tests/visual/probe_customer_display_video.py` compara motores
y también permite probar el widget de producción sin acceder a la base.
La prueba de producción registró `MFPlayerService`, 141 fotogramas, cero errores,
audio silenciado, playlist Loop y parada efectiva al pasar a PAYMENT_PENDING.
La prueba usa plataforma offscreen: verifica decodificación y ciclo del widget,
no certifica presentación en el segundo monitor físico ni todos los formatos.

Evidencias en `docs/refactor/evidence/customer_display_video/`:
`directshow_no_surface.json`, `wmf_python_environment.json`,
`production_window.json`, `regression_before.txt` y `regression_after.txt`.
Los ensayos iniciales con VideoSurface no seleccionaron WMF; los JSON finales
incluyen el nombre real del servicio para evitar confundir preferencia y motor.
No se modificaron datos operativos. Para cargar el cambio, reiniciar SPJ.
