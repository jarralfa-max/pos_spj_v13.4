# PRD — SPJ ERP/POS desde cero

**Versión de visión: 2.0.** Alcance de producto completo descrito en [plano maestro](MASTER_BLUEPRINT.md), [catálogo de módulos](MODULE_CATALOG.md), [web](WEB_APPS.md) y [WhatsApp](WHATSAPP_SERVICE.md). El código actual es referencia de descubrimiento, no criterio de terminado.

## 1. Visión y alcance

Una plataforma ERP/POS para operar sucursales, almacenes, cajas y canales digitales con conectividad intermitente: desde planeación y compra hasta logística, transformación cárnica, inventario, precio, CRM, pedido, venta, entrega, caja, finanzas y analítica. Incluye fidelidad, instrumentos comerciales, calidad, merma, RR. HH., activos, tickets, dispositivos y notificaciones. El diseño sirve a pollo, otras proteínas, abarrotes y servicios, en pieza, peso y sus conversiones. Integra cuatro aplicaciones web para CRM, Compras, Finanzas y BI, dos PWA operativas y un microservicio WhatsApp oficial.

**Estado de referencia:** la rama contiene contextos y pantallas para la mayoría de estas funciones, pero no se presupone un flujo integrado sin pruebas. El recorrido compra→venta y las brechas comprobadas están en [Appflow](APPFLOW.md).

## 2. Usuarios y trabajos principales

| Usuario | Trabajo | Resultado medible |
| --- | --- | --- |
| Comprador | Crear OC o compra directa, autorizar y conciliar recepción/factura | Origen comercial trazable y costo conocido. |
| Operador de origen / logística | Preparar embarque, registrar contenedor, contenido, peso, sello y custodia | Cadena de custodia verificable. |
| Almacenista / receptor | Contar y pesar por línea y lote; registrar diferencia y cuarentena | Existencia sólo por cantidad aceptada. |
| Operador de producción | Transformar lote base con rendimiento versionado; capturar salidas reales y merma | Cortes vendibles, genealogía y costo reconciliado. |
| Gerente de precios | Administrar listas vigentes por sucursal/canal y margen | Precio aplicable con historial y autorización. |
| Cajero | Buscar o escanear, pesar, asignar cliente, cobrar y entregar comprobante | Venta rápida, reserva consistente y cobro trazable. |
| Supervisor de caja | Abrir turno, autorizar excepciones, corte X/Z y entrega | Diferencia documentada y segregación. |
| Cliente / CRM | Consultar historial, crédito y beneficios | Vista única sin permisos implícitos. |
| Finanzas | Conciliar CxP/CxC, tesorería, costos, nómina y cierres | Asientos balanceados con referencia al hecho origen. |
| Administrador | Configurar sucursales, instalación, dispositivos, permisos y actualizaciones | Estación instalable y operable sin Python. |
| Agente CRM | Convertir lead en oportunidad, cotización y pedido con seguimiento | Funnel medible, actividad siguiente y consentimiento documentado. |
| Analista BI | Investigar margen, merma y ventas entre sucursales | Métrica certificada, corte temporal y scope visibles. |
| Agente WhatsApp | Atender bandeja, escalar y confirmar pedidos | Mensajes entregados, trazados y vinculados sin duplicar órdenes. |

## 3. Requisitos por flujo

| ID | Necesidad | Aceptación |
| --- | --- | --- |
| P01 | Compra con OC y directa | Crear, autorizar y recibir compra directa sin exigir OC; toda recepción comercial conserva `source_document_type/id`. |
| P02 | Recolección en origen | Registrar embarque y contenedor desde flujo guiado; permitir un borrador logístico sin PO conforme a política, con conciliación antes de entrada contable. |
| P03 | Recepción y calidad | Capturar peso/cantidad declarada, real, aceptada, rechazada y diferencia; el stock utilizable sólo crece tras aceptación. |
| P04 | Transformación | Elegir lote fuente y perfil de rendimiento versionado por producto/esquema; validar balance de masa y salidas reales. |
| P05 | Inventario | Disponibilidad por sucursal, almacén, lote y estado; reserva y confirmación idempotentes. |
| P06 | Venta de subproductos | Cada corte tiene precio y stock propios; el POS nunca promete cantidad no disponible. |
| P07 | Combinación / reconstrucción | Distinguir bundle comercial virtual y reconstrucción física; en esta última consumir todos los componentes y crear salida en una transacción. |
| P08 | Pagos y protección financiera | Políticas configurables para margen, descuentos, puntos, vales y crédito; bloquear combinaciones no autorizadas antes del cobro. |
| P09 | Caja / finanzas | Vincular pago, movimiento de caja, asiento, corte y devoluciones por referencias independientes e idempotentes. |
| P10 | Identidad y permisos | Un vocabulario otorgable; asignación por rol y usuario con alcance sucursal/almacén; backend deniega sin sesión/checker. |
| P11 | UX | Búsqueda canónica, IDs internos ocultos, folios comerciales visibles; claros estados sin conexión, error, permiso y sincronización. |
| P12 | Instalación | Perfil completo/POS/personalizado, dependencias, migraciones y respaldo previo a actualización; habilitar sólo capacidades instaladas y autorizadas. |
| P13 | Web CRM | Pipeline, cliente 360, tareas, cotizaciones, servicio, campaña consentida y bandeja WhatsApp con la misma identidad/permiso de escritorio. |
| P14 | Web Compras | Requisición, RFQ, comparativo, OC, directa, recepción/diferencia, factura y aprobaciones; sin duplicar inventario. |
| P15 | Web Finanzas | Mayor, CxP/CxC, tesorería, conciliación, presupuestos, cierre y excepciones con fuente operativa trazable. |
| P16 | Web BI | Métricas únicas, filtros por scope, latencia de sincronización, drill-down protegido y exportación auditada. |
| P17 | WhatsApp | Servicio independiente con webhook firmado, plantillas, consentimiento, bandeja, handoff, borradores de pedido/cotización, métricas, DLQ y credenciales administrables. |
| P18 | Entrega/servicio | Pedido, reserva, picking, ruta, peso variable, evidencia, cobro contra entrega, devolución y liquidación. |
| P19 | Activos/RR. HH. | Custodia/mantenimiento/depreciación; empleado/turno/asistencia/nómina/préstamo con segregación y privacidad. |

## 4. Reglas comerciales clave

1. **Propiedad del dato:** Compras posee OC, compra directa y recepción comercial; Logística el movimiento físico y contenedores; Inventario las existencias/lotes; Producción la transformación y rendimiento; Precios las listas; Ventas la venta; Caja la custodia monetaria; Finanzas la contabilidad.
2. **Costo y margen:** usar `Decimal`, costo asignado por salida real y política de piso de margen; una desviación de rendimiento se aprueba con motivo y queda auditable.
3. **Fidelidad:** créditos, puntos, vales, cupones y descuentos pasan por una evaluación conjunta configurable. Evitar puntos en ventas pagadas con vales si esa regla está activa; no superar margen habilitado.
4. **Vales y cupones:** lote y plantilla identificables; credencial escaneable con token verificable; el vale puede tener varios canjes sujetos al límite porcentual configurado y saldo; el cupón se usa una sola vez. La confirmación y el pago deben ser atómicos e idempotentes.
5. **Trazabilidad:** folios legibles para personas, UUIDv7 para identidad; lote de producto y documentos conectados por referencias explícitas y eventos.
6. **Offline:** operaciones locales pendientes se distinguen de confirmadas; el conflicto de custodia, saldo, stock o pago exige resolución, no sobrescritura automática.

## 5. Alcance de entrega y prioridades

| Prioridad | Entrega | Dependencia |
| --- | --- | --- |
| 0 | Comprobar ruta real compra→recepción→inventario→producción→POS→caja→finanzas; fijar pruebas de contrato y fallos actuales. | Código existente. |
| 1 | Resolver selección de producto en orden; recepción/producción directa; cableado de logística; fuente única de stock; reconstrucción atómica. | P0. |
| 2 | Pantallas autónomas de contenedores y embarque provisional; estándar de permisos/UX; políticas financieras integradas. | P1. |
| 3 | PWA offline, transporte/cadena fría, analítica operativa, instalador y actualización para capacidades nuevas. | P1–P2. |

## 6. Indicadores y salida a producción

- 100 % de ventas completadas tienen pago, inventario, caja y evento contable reconciliables; pendientes y excepciones visibles.
- 0 ingresos de inventario por recepción rechazada y 0 doble consumo por reintentos o por doble handler.
- 100 % de salidas de producción enlazadas con lote origen, versión del perfil, consumo y costo; balance de masa dentro de tolerancia o aprobado.
- 0 operaciones sensibles aprobadas por UI sin verificación backend; menú y checker usan mismo catálogo.
- Instalación limpia en Windows sin Python, perfiles verificados y actualización con respaldo/restauración probados.

La liberación requiere pruebas integradas con DB limpia, pruebas de duplicado/reintento, corte de red, permisos negativos, pruebas de hardware o simuladores y validación de operadores en 1366×768 y 1920×1080.

## 7. Experiencias y límites del lanzamiento

El producto no se lanza como «ERP completo» por tener navegación o entidades vacías. La primera entrega utilizable exige ciclo mínimo de compra, stock, venta, caja y asiento balanceado; web y WhatsApp sólo se activan cuando cuentan con API, sesión, permisos y métricas reales. El [plan](DELIVERY_PLAN.md) ordena módulos sin eliminar el alcance integral. La sincronización local/central y la autoridad de pagos/beneficios requieren definición antes del primer despliegue multi sucursal.

**Indicadores de negocio adicionales:** tiempo desde recepción a venta, precisión inventario por lote, diferencia caja por turno, cumplimiento de rendimiento, tasa de reabasto, abandono de carrito, conversión CRM, entregas puntuales, conversión WhatsApp y frescura de BI. Cada indicador debe declarar fuente, fórmula, horario de corte y regla de devoluciones.

## 8. Evidencia de código y límites

- `backend/application/procurement/use_cases/purchase_order_use_cases.py`, `direct_purchase_use_cases.py`; `backend/application/logistics/origin_purchase_workspace.py`.
- `backend/application/meat_processing/use_cases/order_execution_use_cases.py`; `backend/application/inventory/use_cases/reconstruction_use_cases.py`; `backend/application/sales/use_cases/payment_use_cases.py`.
- `backend/bootstrap/wiring/event_wiring.py`, `backend/application/security/permission_catalog.py`, `backend/domain/software_distribution/install_profile.py`.
- La compra directa existe como documento propio; la creación actual del embarque requiere documento. No confundir el flujo de compra directa con embarque sin documento.
