# Catálogo funcional completo

**Leyenda:** `D` escritorio, `W` web, `M` móvil, `A` API/canal. El núcleo de negocio es común. Las superficies propuestas no significan que ya existan. Todas las operaciones de escritura deben transportar actor, scope, `operation_id`, versión esperada, motivo cuando corresponda, auditoría y evento.

## Plataforma y maestros

| Módulo | Canales | Funciones y reglas principales | Integraciones |
| --- | --- | --- | --- |
| Identidad, seguridad y permisos | D/W/M/A | Login, MFA web, sesiones revocables, roles/usuarios, excepciones por usuario, alcance sucursal/almacén/estación, delegación temporal y doble autorización | Todas las rutas; misma decisión en backend. |
| Organización y configuración | D/W | Empresa, sucursal, almacén, moneda, impuestos parametrizables, huso horario, periodos, feature flags, parámetros versionados, aprobaciones | Semillas/catálogo y reglas; secretos fuera de config plana. |
| Integraciones y credenciales | D/W | Catálogo de conectores, alta/validación/rotación de API key, webhook, proveedor, endpoint, replay, último error y auditoría | WhatsApp, terminal, mapas, notificaciones, facturación. |
| Dispositivos e impresión | D | Lectores, báscula, impresora, cajón, display; diagnósticos; colas de trabajos; plantillas de ticket/etiqueta y preview | POS, caja, logística, producción; gateway por hardware. |
| Instalación y actualizaciones | D | Perfil POS/ERP/personalizado, dependencias, versiones, backup, migraciones, salud y rollback | Servicio Windows opcional, API, dataset. |
| Productos y catálogo | D/W lectura | Producto base, cortes, subproductos, abarrotes, servicios, variantes, categoría/surtido, imágenes, unidades, barras, lotes, vida útil, receta, BOM, rendimiento y esquema corte versionados | Compras, inventario, producción, precios, POS. |
| Proveedores | D/W | Identidad, contactos, términos, historial, documentos, clasificación y evaluación | Compras, CxP, WhatsApp autorizado. |
| Precios y promociones | D/W control | Listas por sucursal/canal/cliente, vigencia, historial, reglas de precio, descuentos, autorización y simulación de margen | POS, cotización, CRM, costo, BI. |

## Operación y cadena de suministro

| Módulo | Canales | Funciones y reglas principales | Integraciones |
| --- | --- | --- | --- |
| Forecast/planeación | D/W | Demanda histórica, estacionalidad, lead time, existencias, merma, compras pendientes, sugerencia aprobable | BI, inventario, compras. |
| Compras | D/W | Solicitud, RFQ/comparativo, límites, aprobación, OC, directa sin OC, recepción parcial, factura proveedor, diferencia/devolución | Proveedor, logística, inventario, finanzas; no stock en borrador. |
| Logística | D/M | Contenedor reusable, tipo/compatibilidad, QR permanente, unidades temporales, jerarquía, viaje, carga, custodia, sellos, incidencias, temperatura, retorno, impresión | Compras/transferencias/ventas/producción; nunca escribe stock. |
| Inventario/WMS | D/M | Almacén/ubicación, lotes/FEFO, stock por estado, reserva, conteo ciego, ajustes, cuarentena, cadena fría en almacén | Ledger única fuente, transferencias, producción, venta. |
| Transferencias | D/M | Solicitud, autorización, despacho, tránsito, recepción ciega, diferencia, reversa/retorno | Logística/custodia e inventario; no entrada doble. |
| Producción cárnica | D/M | Orden y transformación directa, despiece, cortes, rendimiento, masa, costo, coproductos, merma, retrabajo, reconstrucción física | Receta/catálogo, lotes, calidad, pricing. |
| Calidad/mermas | D/M | Inspecciones, temperatura, bloqueo/liberación, incidente, pérdida y disposición | Inventario y finanzas; sólo autoridad de calidad libera. |
| Costos | D/W | Costo por lote y corte, insumo+mano de obra/indirecto configurable, variaciones, simulación de precio/margen | Producción, inventario, finanzas, precios. |

## Comercial y cliente

| Módulo | Canales | Funciones y reglas principales | Integraciones |
| --- | --- | --- | --- |
| Clientes/CRM | D/W | Persona/empresa, contactos, direcciones, privacidad/consentimiento, duplicados/fusión, cliente 360, lead, oportunidad, actividades, segmentación y servicio | Ventas, crédito, fidelidad, WhatsApp, BI. |
| Cotizaciones y pedidos | D/W/A | Oferta versionada, vigencia, aprobaciones, conversión idempotente, pedido y reserva; programado/WhatsApp | CRM, precios, inventario, delivery, finanzas. |
| POS/Ventas | D | Carrito, báscula, escáner, cliente, stock, lista, impuestos, beneficios, cobro mixto, crédito, suspensión, reversa/devolución, ticket | Caja, inventario, fidelidad, finanzas, cliente. |
| Entregas/Delivery | D/M | Zonas, ruta, repartidor, evidencias, peso variable, cobro contra entrega, devoluciones y liquidación | Pedido, stock, caja, logística, CRM. |
| Fidelidad y campañas | D/W control | Puntos, ledger, niveles, tarjetas, referidos, recompensas, cumpleaños, rifas, segmentación y presupuesto | Cliente, ventas, margen, finanzas y canal. |
| Instrumentos comerciales | D/W control | Lote/plantilla para vales y cupones, token/barra, emisión/activación, validez, reserva/canje/reversa y saldo; vale por porcentaje y uno o varios eventos, cupón una vez | Pago POS y pasivo financiero; bloqueo contra doble canje. |
| Atención y notificaciones | D/W/A | Solicitud/caso/SLA, preferencia de canal, consentimiento, bandeja, plantillas, intentos y entregas | CRM, WhatsApp, email futuro, pedidos. |

## Control financiero, personas y dirección

| Módulo | Canales | Funciones y reglas principales | Integraciones |
| --- | --- | --- | --- |
| Caja | D/W supervisión | Turno, fondos, pago, retiros, arqueo ciego, X/Z, diferencias, custodia, depósitos, reimpresión con auditoría | POS, delivery, RR. HH., finanzas. |
| Finanzas/tesorería | D/W | Plan cuentas, diarios, CxP/CxC, asientos, bancos/conciliación, presupuesto, centros costo, cierre/reversas, vencimientos | Compras, ventas, caja, nómina, activos, inventario. |
| RR. HH./nómina | D/W limitado | Empleado, puesto, asistencia, permisos, turnos, incidencias, préstamos, nómina y pagos; privacidad estricta | Caja turno, finanzas, autorizaciones. |
| Activos | D/W | Alta, ubicación/custodia, mantenimiento, depreciación y baja | Finanzas, logística, RR. HH. |
| BI/alertas/escenarios | D/W | Ventas, margen real por corte, stock, merma, cumplimiento, clientes, caja, finanzas, personal, forecast, alertas y simulación | Proyecciones certificadas; seguridad por fila. |
| Documentos/tributación | D/W | Ticket, comprobante, adjuntos y facturación mediante gateway configurable; control de folio y de versión | Venta, compra, caja y finanzas; reglas fiscales validadas aparte. |
| WhatsApp | A/W consola | Mensajes, conversación, handoff, pedido/cotización en borrador, plantillas, campañas consentidas, webhook, métricas y DLQ | CRM, ventas, delivery, catálogo, configuración. |

## Reglas de coexistencia entre módulos

- Cliente tiene identidad única; lead y contacto se relacionan sin sobrescribir ventas históricas.
- Producto y categoría gobiernan elegibilidad por sucursal; precio y costo se versionan y no sobrescriben snapshots de documentos confirmados.
- Logística posee contenedor y custodia; Inventario lote y saldo; Transferencia documento de movimiento; Producción la genealogía. Cada uno emite hechos sin escribir en tablas de otro contexto.
- Caja conserva efectivo y turnos; Finanzas contabiliza. Un cobro no equivale a depósito ni a conciliación.
- Fidelidad y vales pasan por motor único de beneficios y presupuesto financiero; POS muestra decisión, no la recalcula.
- Reportes nunca alteran contabilidad y no conocen secretos de WhatsApp. Administradores ven métricas agregadas; datos personales/costos requieren permiso explícito.

## Entregables por módulo

Cada módulo se acepta con mapa de estados, casos de uso/consultas, pantalla desktop/web/móvil según tabla, permisos CRUD+acciones, criterios de scope, esquema/migración, eventos, políticas de reversa, pruebas de duplicado/seguridad/offline, métricas, manual operativo y pruebas de aceptación con datos realistas de pollo, otras proteínas y abarrotes.
