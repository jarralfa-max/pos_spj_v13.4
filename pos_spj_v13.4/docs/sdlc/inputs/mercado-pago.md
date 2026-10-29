PROMPT MAESTRO — INTEGRACIÓN ENTERPRISE DE MERCADO PAGO EN SPJ ERP v13.4

0. ROL Y MISIÓN

Actúa como Principal Software Architect, Senior Python Engineer, Payment Systems Architect, FinTech Security Engineer, ERP Domain Architect y Senior QA Engineer.

Trabajarás en el repositorio:

jarralfa-max/pos_spj_v13.4

Rama de trabajo obligatoria:

claude/erp-financial-bounded-context-uqxz6b

Debes desarrollar la integración empresarial de Mercado Pago para:

* Terminales Point Smart.
* Checkout Pro.
* Órdenes digitales y enlaces de pago.
* QR dinámicos asociados a órdenes de pago.
* Ventas presenciales.
* Ventas remotas.
* Pagos mixtos.
* Devoluciones y reembolsos.
* Conciliación de cobros.
* Tesorería y Finanzas.
* Caja y cierres de turno.
* CRM, pedidos y WhatsApp.
* Business Intelligence.
* Operación offline-first con SQLite.
* Coordinación central con PostgreSQL, de acuerdo con la arquitectura realmente disponible.

NO desarrolles una aplicación paralela.

NO dupliques módulos, bases de datos, servicios, casos de uso, repositorios, componentes UI, migraciones ni entidades existentes.

LA AUDITORÍA DEL CÓDIGO REAL ES OBLIGATORIA Y PRECEDE A CUALQUIER MODIFICACIÓN FUNCIONAL.

Está prohibido comenzar implementando carpetas o clases nuevas basándose solamente en este prompt.

El código existente prevalece sobre cualquier ruta o nombre propuesto en este documento.

⸻

1. PRINCIPIOS NO NEGOCIABLES

La solución debe cumplir los principios arquitectónicos vigentes de SPJ ERP:

1. DDD y bounded contexts coherentes.
2. Separación estricta de presentación, aplicación, dominio e infraestructura.
3. Arquitectura orientada a eventos cuando el proyecto ya lo contemple.
4. Offline-first con recuperación transaccional.
5. UUIDv7 para nuevas identidades internas.
6. Decimal para todos los importes financieros.
7. Idempotencia en solicitudes externas y efectos internos.
8. Permisos centralizados.
9. Auditoría de operaciones sensibles.
10. UI/UX integrada al Design System.
11. Migraciones idempotentes, reversibles cuando sea viable y compatibles.
12. No introducir dependencias innecesarias.
13. No almacenar secretos en código ni en configuración local insegura.
14. No romper el empaquetado Windows.
15. No utilizar SQLite como fuente compartida de coordinación entre varias estaciones.
16. No realizar operaciones financieras directamente desde widgets.
17. No ejecutar SQL desde el frontend.
18. No utilizar nombres de roles como mecanismos de autorización.
19. No introducir UUIDv4 como identificador de dominio; los identificadores exigidos por proveedores externos se adaptarán a sus requisitos.
20. No reinventar funciones ya implementadas.

Toda nueva integración debe respetar las fronteras de los bounded contexts existentes.

⸻

FASE 0 — RECONOCIMIENTO DEL REPOSITORIO

Antes de escribir código:

1. Confirmar el directorio raíz.
2. Ejecutar git status.
3. Confirmar rama actual.
4. Obtener el SHA de HEAD.
5. Revisar archivos modificados y cambios sin confirmar.
6. No sobrescribir cambios del usuario.
7. No efectuar reset, force push ni merge automático.
8. Verificar si la rama local y remota divergen.
9. Identificar estructura actual del proyecto.
10. Identificar pruebas, documentación y herramientas existentes.

Si la rama indicada no está activa, informar la discrepancia y trabajar únicamente con las condiciones de seguridad permitidas por el entorno.

No cambiar silenciosamente a main.

No tomar código de main como fuente canónica sin analizar compatibilidad.

Comparar con main exclusivamente cuando resulte útil para detectar regresiones o funcionalidad perdida.

Entregable 0

Registrar:

* Branch.
* Commit SHA.
* Estado del working tree.
* Estado de dependencias.
* Versiones efectivas.
* Limitaciones del entorno de auditoría.

⸻

FASE 1 — AUDITORÍA OBLIGATORIA DEL CÓDIGO REAL

Antes de implementar, examinar exhaustivamente los componentes relacionados con pagos.

1.1 Ventas y POS

Investigar:

* Ventas.
* Sale Aggregate.
* SalePaymentReference.
* SaleTotals.
* PaymentIntent existente.
* ConfirmSalePaymentUseCase.
* CreatePaymentIntentUseCase.
* PaymentMethod.
* PaymentAllocation.
* Checkout policies.
* Cancelación.
* Suspensión y recuperación.
* Devoluciones.
* Reversiones.
* Impresión de tickets.
* Monitor del cliente.
* Lectura de báscula.
* Descuentos.
* Fidelización.
* Autorización de supervisor.

Los nombres anteriores son referencias conceptuales. Localizar las implementaciones reales antes de asumir su existencia.

1.2 Caja

Examinar:

* Apertura y cierre de sesión de caja.
* Arqueo.
* Corte X y Z.
* Movimientos de caja.
* Métodos de pago.
* Venta a crédito.
* Pagos mixtos.
* Transacciones externas.
* Asientos asociados.
* Reversión de movimientos.
* Conciliación.
* Reimpresión de comprobantes.
* Reportes por cajero, estación y sucursal.

Determinar cómo registrar un cobro electrónico sin incrementar indebidamente el efectivo disponible.

1.3 Finanzas y Tesorería

Examinar:

* Cuentas contables.
* Cuentas por cobrar.
* Cuentas puente.
* Bancos.
* Comisiones.
* Gastos financieros.
* IVA de comisiones.
* Conciliación bancaria.
* Depósitos de procesadores.
* Libro mayor.
* Centros de costo.
* Reglas de consolidación.
* Monedas y redondeos.
* Idempotencia contable.

No crear un segundo libro contable.

No utilizar el total neto depositado como valor bruto de venta.

1.4 Configuración y seguridad

Auditar:

* Módulo de Configuración.
* Secret managers existentes.
* Credenciales cifradas.
* RBAC.
* PermissionRegistry.
* AuthorizationService.
* Ámbitos empresa/sucursal/estación.
* Políticas por usuario y rol.
* Auditoría.
* Gestión de dispositivos.
* Sesiones autenticadas.
* Protección de endpoints.
* Gestión de ambientes de prueba y producción.

No introducir permisos desconectados del registro central.

1.5 Integraciones

Localizar:

* Conectores de pago existentes.
* Abstracciones de terminal bancaria.
* PaymentGateway.
* DeviceGateway.
* EventBus.
* Outbox.
* Inbox.
* Retry policies.
* HTTP clients.
* Webhook handlers.
* Task workers.
* Sincronización SQLite/PostgreSQL.
* API FastAPI.
* Adaptadores de WhatsApp.
* Integraciones CRM.
* Servicios de pedidos web.
* Servicio de impresión.

Verificar importaciones hacia módulos legacy o eliminados.

No recuperar código eliminado por suposición.

1.6 UI/UX

Inspeccionar:

* Design System.
* Componentes compartidos.
* Diálogo de pago actual.
* Estado de checkout.
* Botones de cobro.
* Gestión de errores.
* Indicadores de hardware.
* Monitor del cliente.
* Notificaciones in-app.
* Preferencias visuales.
* Light/dark mode.
* Layout en 1366×768 y 1920×1080.

No sustituir el layout actual del POS.

1.7 Instalador

Revisar:

* PyInstaller.
* Archivos .spec.
* Inno Setup.
* Dependencias release.
* Servicios opcionales.
* Configuración por equipo.
* Migraciones.
* Actualizador.
* Política de conservación de datos.

La integración debe funcionar después de instalar SPJ ERP en otra computadora Windows sin Python instalado.

1.8 Auditoría transversal

Realizar búsquedas en todo el repositorio de:

* mercadopago
* mercado_pago
* payment
* payment_intent
* checkout
* card_terminal
* point
* webhook
* outbox
* inbox
* reconciliation
* settlement
* refund
* cash
* loyalty
* voucher
* credit

No limitarse a estas palabras.

Seguir consumidores, imports, pruebas y dependencias reales.

Entregable 1

Crear:

docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md

Incluir una matriz:

Capacidad	Estado actual	Evidencia	Reutilizar / Extender / Corregir / Crear	Riesgo

La evidencia debe contener archivo, símbolo y líneas cuando corresponda.

Clasificar hallazgos:

* CRITICAL
* HIGH
* MEDIUM
* LOW

Distinguir entre:

* Implementado y funcional.
* Implementado parcialmente.
* Implementado pero defectuoso.
* Legacy.
* Duplicado.
* Ausente.
* No verificable.

No afirmar que algo falta sin buscarlo en todo el repositorio.

Registrar diagramas de dependencias y flujos de pago actuales.

⸻

FASE 2 — PLAN DE IMPLEMENTACIÓN BASADO EN LA AUDITORÍA

Crear un plan real, no genérico, apoyado en los hallazgos anteriores.

Prioridad:

A. Reutilizar contratos y servicios.

B. Extender componentes existentes.

C. Corregir problemas de arquitectura encontrados.

D. Crear únicamente las capacidades justificadamente ausentes.

E. Eliminar duplicaciones solo cuando sus consumidores hayan migrado y las pruebas lo demuestren.

Crear:

docs/architecture/MERCADO_PAGO_INTEGRATION_TRD.md

docs/architecture/MERCADO_PAGO_INTEGRATION_APPFLOW.md

docs/architecture/MERCADO_PAGO_INTEGRATION_DATA_MODEL.md

docs/architecture/MERCADO_PAGO_INTEGRATION_SECURITY.md

docs/architecture/MERCADO_PAGO_INTEGRATION_UX.md

docs/architecture/MERCADO_PAGO_INTEGRATION_TEST_PLAN.md

Documentar decisiones técnicas mediante ADR si el proyecto ya utiliza ese estándar.

No duplicar documentos equivalentes existentes: actualizarlos cuando corresponda.

Definir dependencias, entregables, riesgos y criterios de aceptación por fase.

⸻

FASE 3 — INTEGRACIÓN CANÓNICA DE PAYMENTS

Inspeccionar primero el bounded context o servicio de pagos existente.

La arquitectura conceptual requerida es:

POS / CRM / Web / WhatsApp
→ Application Use Cases
→ Payments Domain
→ PaymentProviderPort
→ MercadoPagoAdapter
→ API Mercado Pago

El proveedor NO es propietario de:

* Sale Aggregate.
* Inventario.
* Cuentas contables.
* Reglas de fidelidad.
* Descuentos.
* Crédito.
* Caja.
* Configuración de usuarios.

Crear o extender, según auditoría, contratos equivalentes a:

* CreatePaymentIntent.
* CreateProviderOrder.
* GetPaymentStatus.
* ConfirmPayment.
* CancelPayment.
* RefundPayment.
* ReconcilePayment.
* LinkTerminal.
* ListAvailableTerminals.
* VerifyWebhook.
* ProcessProviderEvent.

Evitar que el POS conozca endpoints, tokens o esquemas HTTP internos de Mercado Pago.

Se requiere un adaptador anticorrupción entre los modelos internos y los estados externos del proveedor.

No asumir que un estado externo se corresponde directamente con un estado del dominio.

⸻

FASE 4 — MERCADO PAGO POINT SMART

Utilizar preferentemente la integración vigente de Mercado Pago Point mediante Orders API.

Consultar la documentación oficial actual antes de implementar:

https://www.mercadopago.com.mx/developers/es/docs/mp-point/configure-terminal

https://www.mercadopago.com.mx/developers/es/docs/mp-point/payment-processing

https://www.mercadopago.com.mx/developers/es/reference/in-person-payments/point/orders/create-order/post

4.1 Configuración de terminal

Implementar o extender:

* Descubrimiento de terminales autorizadas.
* Vinculación a una cuenta cobradora.
* Mapeo de sucursal Mercado Pago.
* Mapeo de caja Mercado Pago.
* Mapeo de sucursal SPJ.
* Mapeo de estación de trabajo SPJ.
* Validación de estado operativo.
* Configuración y verificación del modo PDV, con autorización administrativa.
* Revocación y reasignación controlada.
* Detección de terminal ocupada o no disponible.

No confundir la caja de Mercado Pago con la sesión de caja contable de SPJ.

4.2 Crear orden

Antes de invocar la API:

1. Validar permisos.
2. Validar sesión de caja.
3. Validar saldo pendiente.
4. Validar descuentos y puntos.
5. Validar moneda.
6. Congelar un snapshot verificable del importe.
7. Crear intención interna idempotente.
8. Reservar la asignación de pago.
9. Identificar la terminal.
10. Construir la petición externa.

Para Point utilizar la Orders API vigente, cuyo recurso de creación es:

POST https://api.mercadopago.com/v1/orders

El payload deberá validarse contra la versión actual de la documentación; usar type=point, referencia externa estable, importe decimal expresado conforme a la API y configuración de terminal.

El encabezado X-Idempotency-Key debe ser estable por operación lógica. No generar otra clave para reintentar exactamente la misma operación.

Cumplir los requisitos de longitud y formato del proveedor.

Una misma terminal no podrá recibir simultáneamente dos órdenes incompatibles desde diferentes estaciones.

4.3 Estados

El POS mostrará:

* Preparando cobro.
* Esperando terminal.
* Esperando tarjeta.
* Procesando.
* Verificando.
* Aprobado.
* Rechazado.
* Cancelado.
* Expirado.
* Estado desconocido: requiere consulta.
* Error de comunicación.

No asignar APPROVED únicamente por recibir HTTP 201 de creación de orden.

Antes de completar la venta, verificar el resultado real de la operación.

4.4 Cancelaciones y timeouts

Si existe timeout:

* Mantener el mismo identificador lógico.
* Consultar la orden remota.
* No generar otro cobro automáticamente.
* Bloquear reintentos incompatibles.
* Mostrar opción de recuperar estado.
* Permitir cancelación únicamente cuando corresponda.
* Gestionar resultados tardíos.

Si el cliente fue cobrado pero se perdió la respuesta, la operación debe poder recuperarse sin cobrarle nuevamente.

⸻

FASE 5 — CHECKOUT DIGITAL Y ENLACES DE PAGO

Implementar Checkout Pro mediante el flujo oficial vigente, preferentemente Orders API cuando sea compatible con los requerimientos.

Documentación:

https://www.mercadopago.com.mx/developers/es/docs/checkout-pro-orders/create-order

Diseñar soporte para:

* Generación de orden digital.
* Checkout URL.
* Referencia externa.
* Vigencia.
* Identificación del cliente cuando proceda.
* Confirmación asíncrona.
* Cancelación.
* Recuperación de estado.
* Pago de pedidos externos.
* Consulta desde CRM.
* Envío de enlace por WhatsApp.

Cada enlace debe vincularse con una venta o pedido concreto.

No utilizar enlaces genéricos del panel de Mercado Pago cuando se requiera conciliación automática por operación.

El sistema debe controlar el vencimiento del enlace y los cambios de estado.

Si una orden expiró, la recreación debe ser explícita, trazable e idempotente.

Las URLs deben generarse en el backend y devolverse al cliente autorizado.

No exponer tokens privados en URLs.

⸻

FASE 6 — QR DINÁMICO

Para SPJ ERP, el QR de pago podrá codificar la URL segura de un Checkout generado específicamente para la operación.

Distinguir entre:

1. QR dinámico que dirige al Checkout de una orden SPJ.
2. QR nativo de Mercado Pago sujeto a las capacidades y requisitos específicos de su API.

No presentar ambas opciones como equivalentes sin validarlas.

El QR debe:

* Corresponder a una única intención activa.
* Mostrar importe y referencia.
* Tener vencimiento controlado.
* Poder visualizarse en el monitor del cliente.
* Permitir regeneración controlada de la vista sin duplicar órdenes.
* Refrescar automáticamente el estado desde el backend.
* Invalidarse en la interfaz después de pago, cancelación o expiración.

Escanear el QR no significa que el pago esté aprobado.

La confirmación debe provenir de una consulta autorizada al proveedor.

⸻

FASE 7 — WEBHOOKS, INBOX E IDEMPOTENCIA

Crear o reutilizar un endpoint HTTPS central para Webhooks.

Ejemplo conceptual:

POST /api/v1/integrations/mercadopago/webhooks

Antes de crear esa ruta, comprobar los estándares reales de routing y versionado del backend.

Implementar:

* Verificación de firma.
* Validación temporal cuando aplique.
* Validación de ambiente y aplicación.
* Validación de cuenta receptora.
* Parsing estricto.
* Límite de tamaño.
* Registro seguro del evento.
* Deduplicación.
* Persistencia duradera.
* Procesamiento asíncrono recuperable.
* Consulta del recurso remoto.
* Comparación de monto y moneda.
* Verificación de referencia y cuenta cobradora.
* Reintentos con backoff.
* Dead-letter/revisión manual.
* Métricas de errores.
* Auditoría.

Un Webhook es una señal para recuperar y verificar información, no una autorización para modificar directamente una venta.

El efecto de un evento duplicado debe ser idempotente.

Un evento tardío nunca debe hacer retroceder indebidamente un estado financiero confirmado.

Si falla el procesamiento, la notificación debe permanecer recuperable.

No devolver una confirmación HTTP exitosa si el evento todavía no ha sido almacenado de forma duradera, salvo que exista otra garantía de recuperación equivalente.

Implementar una tarea de reconciliación que consulte órdenes pendientes o inciertas incluso cuando nunca llegue un Webhook.

⸻

FASE 8 — OFFLINE-FIRST Y SINCRONIZACIÓN

Respetar la arquitectura existente y la evolución prevista:

SQLite local + PostgreSQL central.

No asumir que la migración híbrida ya está implementada.

Auditar su estado y establecer dependencias reales.

8.1 Sin internet

Permitir únicamente operaciones que sean compatibles con las políticas offline vigentes.

Para pagos Mercado Pago:

* No inventar aprobaciones.
* No usar credenciales privadas en SQLite.
* No confirmar cobros remotos no verificables.
* Mantener estado incierto cuando sea necesario.
* No generar nuevas órdenes si no existe comunicación con el backend autorizado.
* Evitar bloqueos permanentes de la interfaz.

La venta en efectivo debe continuar funcionando según las reglas offline existentes.

8.2 Recuperación

Al restablecer comunicación:

1. Sincronizar operaciones pendientes.
2. Identificar las intenciones de pago existentes.
3. Consultar estado remoto.
4. Deduplicar.
5. Confirmar efectos financieros una sola vez.
6. Publicar eventos.
7. Actualizar el POS.
8. Actualizar reportes.

Evitar que dos equipos confirmen, cancelen o reembolsen concurrentemente la misma operación.

Las operaciones remotas de pago requieren coordinación central cuando así lo exija su consistencia.

No utilizar sincronización eventual como justificación para permitir doble cobro.

⸻

FASE 9 — INTEGRACIÓN CON CAJA

No duplicar el bounded context Caja.

Extender los métodos de pago existentes con Mercado Pago cuando corresponda.

9.1 Arqueo

Separar:

* Efectivo.
* Tarjetas procesadas por Mercado Pago.
* Checkout digital.
* Transferencias.
* Vales.
* Crédito.
* Otros métodos.
* Pagos mixtos.

No sumar los pagos Mercado Pago al efectivo físico del cajón.

9.2 Corte X y Z

Preservar formatos, impresión, UUIDv7 internos y trazabilidad existentes.

Agregar cuando aplique:

* Número de transacciones Point.
* Total bruto.
* Total de pagos digitales.
* Pagos pendientes.
* Reembolsos.
* Diferencias.
* Referencias de conciliación.
* Comisiones conocidas, separadas de las estimadas.

La comisión no debe disminuir silenciosamente el importe bruto cobrado en el corte.

9.3 Pagos mixtos

Garantizar:

Sum(payment_allocations) = TotalDue

con redondeo decimal explícito.

Ejemplo:

Venta: $500.00 MXN.

Efectivo: $200.00 MXN.

Mercado Pago: $300.00 MXN.

Si el pago externo falla, no debe completarse la venta como si existiera una cobertura total.

Diseñar compensaciones y recuperación para asignaciones parciales.

No realizar rollback destructivo de un pago electrónico que ya fue aprobado.

⸻

FASE 10 — FINANZAS, TESORERÍA Y CONCILIACIÓN

Integrar con el dominio financiero existente.

No crear tablas financieras paralelas.

Modelar correctamente:

* Venta bruta.
* Impuestos sobre la venta.
* Importe capturado.
* Cuenta por cobrar al procesador.
* Comisión del procesador.
* Impuestos sobre comisiones.
* Retenciones, si corresponden.
* Reembolsos.
* Contracargos.
* Depósito neto.
* Diferencias por conciliación.

Los registros deben representar hechos financieros distintos.

No duplicar el ingreso al registrar posteriormente el depósito bancario.

Asignar sucursal, empresa, centro de costo y cuenta cobradora según la organización real.

10.1 Conciliación

Implementar un flujo comparable a:

CAPTURED
→ AWAITING_SETTLEMENT
→ SETTLED
→ RECONCILED

Con estados de excepción:

* MISSING_PROVIDER_TRANSACTION.
* SETTLEMENT_MISMATCH.
* DUPLICATE_REFERENCE.
* UNKNOWN_FEE.
* PARTIAL_REFUND.
* CHARGEBACK.
* MANUAL_REVIEW_REQUIRED.

Los estados reales deberán adaptarse al dominio existente.

No asumir que los Webhooks de aprobación incluyen todos los detalles de comisiones y liquidación.

Investigar qué reportes, APIs o archivos oficiales proporciona Mercado Pago para obtener información de liquidación.

Si la API no permite automatizar una operación, implementar importación verificable sin inventar datos.

10.2 Reportes

Habilitar vistas por:

* Empresa.
* Sucursal.
* Planta o establecimiento, cuando corresponda.
* Caja.
* Estación.
* Cajero.
* Terminal.
* Cuenta Mercado Pago.
* Fecha de operación.
* Fecha de liquidación.
* Método.
* Estado.

Los usuarios corporativos podrán consultar información global o segmentada según sus permisos.

La empresa y la sucursal son dimensiones diferentes.

⸻

FASE 11 — REGLAS FINANCIERAS, FIDELIDAD Y BENEFICIOS

Respetar íntegramente las reglas configurables del negocio.

Invariantes:

* No aplicar descuentos incompatibles con puntos.
* El crédito limita beneficios según la política.
* Los descuentos no exceden el margen permitido.
* Los puntos no exceden los límites definidos.
* Los vales no generan puntos cuando la política lo prohíba.
* Una orden pendiente no genera puntos definitivos.
* Un pago rechazado no genera puntos.
* Los reembolsos y devoluciones deben revertir beneficios según la política.
* La asignación del método de pago no debe omitir restricciones.
* Las transacciones mixtas deben evaluar elegibilidad conforme a sus componentes.

Ejecutar las validaciones mediante los motores de políticas existentes.

No implementar reglas duplicadas en el adaptador Mercado Pago.

⸻

FASE 12 — SEGURIDAD Y CONTROL DE ACCESO

12.1 Credenciales

El Access Token debe residir únicamente en el entorno backend autorizado, protegido mediante el mecanismo seguro existente.

No almacenar tokens en:

* Widgets.
* Archivos .ui.
* SQLite local en texto plano.
* Logs.
* Tickets.
* Eventos de dominio sin sanitizar.
* URLs de pago.
* Variables visibles desde el cliente.
* Repositorio Git.

Enmascarar identificadores sensibles.

Implementar rotación y revocación de credenciales.

12.2 Permisos

Antes de crear nuevos permisos, localizar el registro central.

Adaptar capacidades conceptuales como:

* payments.mercadopago.configure
* payments.mercadopago.view
* payments.mercadopago.terminal.assign
* payments.mercadopago.charge
* payments.mercadopago.refund
* payments.mercadopago.cancel
* payments.mercadopago.reconcile
* payments.mercadopago.audit

Los identificadores definitivos deben seguir la convención real del ERP.

Configurar autorizaciones por recurso, acción y ámbito organizacional.

No limitar acceso únicamente por nombre del rol.

12.3 Auditoría

Registrar:

* Usuario.
* Operación.
* Fecha.
* Sucursal.
* Estación.
* Importe.
* Moneda.
* Proveedor.
* Referencia.
* Estado anterior.
* Estado nuevo.
* Evidencia de autorización.
* Correlation ID.

No registrar datos completos de tarjeta.

No almacenar CVV.

No introducir captura directa de PAN si el checkout alojado o la terminal permiten evitar ese alcance.

⸻

FASE 13 — UI/UX ENTERPRISE

Mantener el layout Golden Master del POS.

No reducir el espacio del carrito.

No ocultar botones esenciales bajo scroll innecesario.

No romper:

* Catálogo.
* ProductCard.
* Lectura de báscula.
* Monitor del cliente.
* Descuentos.
* Resumen de puntos.
* Suspendidas.
* Devoluciones.
* Tickets.

Agregar Mercado Pago dentro del diálogo estándar de cobro.

13.1 Flujo Point

Mostrar:

* Terminal seleccionada.
* Importe.
* Estado de conexión.
* Estado de orden.
* Progreso del cobro.
* Cancelación controlada.
* Reintento seguro.
* Recuperación de estado.
* Resultado.
* Referencia.

13.2 Flujo digital

Mostrar:

* Importe.
* QR de Checkout.
* Enlace de pago.
* Vencimiento.
* Estado.
* Copiar enlace.
* Compartir mediante integración disponible.
* Cancelar.
* Reconsultar.

13.3 Monitor del cliente

Integrar con el mecanismo existente:

* Importe a pagar.
* Indicación de uso de terminal.
* QR dinámico cuando corresponda.
* Estado de espera.
* Confirmación.
* Mensaje de agradecimiento.
* Branding de JUANIS configurado.

No reconstruir el monitor del cliente.

No modificar los assets oficiales de marca.

13.4 Configuración

Crear o extender una sección de proveedores de pagos con:

* Cuenta cobradora.
* Ambiente.
* Estado de integración.
* Terminales disponibles.
* Terminal vinculada por estación.
* Permisos.
* Salud del servicio.
* Prueba de conectividad.
* Webhook configurado.
* Última sincronización.
* Historial de incidencias.

No mostrar “Conectado” solamente porque existen credenciales guardadas.

Verificar realmente la conexión autorizada.

⸻

FASE 14 — WHATSAPP, CRM Y PEDIDOS WEB

Localizar las implementaciones existentes.

No crear otro microservicio de WhatsApp.

No recuperar código legacy eliminado.

El flujo de pago remoto deberá permitir:

1. Crear pedido.
2. Calcular total.
3. Aplicar políticas.
4. Generar orden Mercado Pago.
5. Obtener Checkout URL.
6. Enviar enlace mediante el servicio de mensajería existente.
7. Recibir evento de pago.
8. Validar con API.
9. Confirmar pedido.
10. Notificar al cliente.
11. Continuar con logística/entrega cuando corresponda.

Evitar que dos canales creen órdenes de pago duplicadas para el mismo intento.

CRM deberá consultar estados de pago por contratos de aplicación autorizados.

El microservicio WhatsApp no debe ser propietario del estado financiero.

⸻

FASE 15 — REEMBOLSOS Y CONTRACARGOS

Auditar las políticas existentes de devoluciones.

Implementar o extender soporte para:

* Reembolso total.
* Reembolso parcial cuando lo admita la modalidad.
* Autorización supervisor.
* Consulta del estado del reembolso.
* Eventos tardíos.
* Reembolso rechazado.
* Duplicados.
* Conciliación.
* Reversión de beneficios.
* Registro de diferencias financieras.

No crear un reembolso remoto únicamente por cancelar la vista del diálogo.

Nunca asumir que una solicitud de reembolso ha finalizado porque el proveedor respondió que fue recibida.

Registrar estados de procesamiento y resolución.

Los contracargos deben generar un proceso financiero y operativo de investigación, sin borrar las ventas históricas.

⸻

FASE 16 — TESTING

No aceptar implementaciones con únicamente pruebas superficiales.

16.1 Unit tests

Cubrir:

* Importes Decimal.
* Redondeos.
* Estados.
* Transiciones.
* Idempotencia.
* Restricciones de beneficios.
* Autorizaciones.
* Pagos mixtos.
* Mapeo de errores.
* Mapeo de estados externos.

16.2 Integration tests

Cubrir:

* Backend ↔ adaptador.
* Backend ↔ persistencia.
* Inbox/Outbox.
* Eventos.
* Checkout.
* Caja.
* Finanzas.
* Configuración.
* Devoluciones.
* Sincronización.
* Instalación.

16.3 Seguridad

Verificar:

* Firma inválida.
* Notificación duplicada.
* Notificación manipulada.
* Token caducado.
* Credenciales faltantes.
* Acceso cruzado entre sucursales.
* Acceso cruzado entre empresas.
* Reembolso sin permiso.
* Modificación manual de importes.
* Replay.
* Logs sin exposición de secretos.

16.4 Fallos y concurrencia

Simular:

1. Dos cajeros intentando utilizar la misma terminal.
2. Timeout al crear una orden.
3. Orden creada con respuesta HTTP perdida.
4. Pago aprobado durante caída de internet.
5. Webhook duplicado.
6. Webhook fuera de orden.
7. Webhook nunca recibido.
8. Reinicio del POS durante el pago.
9. Reinicio del backend.
10. Caída de PostgreSQL.
11. Fallo de sincronización.
12. Reintento tras aprobación.
13. Cambio de importe durante un pago pendiente.
14. Reembolso parcial seguido de otro reembolso.
15. Pago mixto con éxito parcial.
16. Contracargo después de conciliación.
17. Cliente intentando pagar un enlace vencido.
18. Cambio de terminal asignada durante una operación.
19. Dos equipos intentando confirmar el mismo pago.
20. Instalación y actualización sin pérdida de datos.

Utilizar mocks, fakes o sandbox oficial cuando sea compatible.

No enviar pagos reales durante pruebas automatizadas.

No asumir que el sandbox reproduce íntegramente el comportamiento físico de Point Smart.

16.5 Regresión visual

Verificar 1366×768 y 1920×1080, modo claro y oscuro.

Preservar los golden masters existentes.

Actualizar pruebas visuales únicamente cuando un cambio funcional aprobado lo justifique.

⸻

FASE 17 — DOCUMENTACIÓN Y OPERACIÓN

Documentar:

* Registro de aplicación en Mercado Pago.
* Obtención de credenciales.
* Separación sandbox / producción.
* Vinculación Point Smart.
* Activación modo PDV.
* Configuración del backend.
* Configuración de Webhooks.
* Puesta en marcha HTTPS.
* Configuración multi-sucursal.
* Configuración de permisos.
* Pruebas de cobro.
* Cierre de caja.
* Conciliación.
* Reembolsos.
* Recuperación tras fallos.
* Rotación de secretos.
* Desconexión segura.
* Solución de incidencias.

Crear un runbook operativo en español.

No incluir secretos reales en los documentos.

⸻

FASE 18 — INSTALADOR Y DESPLIEGUE

Auditar el instalador Windows real antes de cambiarlo.

Determinar si la integración requiere:

* Dependencias Python nuevas.
* Recursos adicionales.
* Configuración del cliente.
* Nuevos servicios.
* Reglas de firewall.
* Certificados.
* Cambios de migraciones.
* Actualizaciones de versión.
* Cambios de empaquetado.

Modificar únicamente lo necesario.

Los equipos cliente no deben requerir instalación manual de Python.

El Access Token del proveedor debe permanecer en el backend central.

No obligar a instalar servicios backend sensibles dentro de cada caja.

Si la infraestructura central todavía no existe, crear una dependencia técnica explícita y un plan de integración, sin fingir conectividad productiva.

⸻

FASE 19 — CRITERIOS DE ACEPTACIÓN

La integración estará terminada cuando:

[ ] Se completó la auditoría con evidencia del código real.

[ ] No existen bounded contexts duplicados.

[ ] Point Smart puede vincularse y verificarse.

[ ] Una orden Point puede iniciarse desde el POS.

[ ] El estado se verifica antes de completar la venta.

[ ] Checkout Pro genera órdenes vinculadas al ERP.

[ ] El QR corresponde a una orden verificable.

[ ] Los Webhooks están autenticados e implementan deduplicación.

[ ] Los timeouts no provocan doble cobro.

[ ] Los pagos mixtos respetan la integridad de importes.

[ ] Caja no confunde cobros electrónicos con efectivo.

[ ] Finanzas registra bruto, comisiones, reembolsos y liquidaciones correctamente.

[ ] La conciliación maneja diferencias.

[ ] Los permisos provienen del registro central.

[ ] Se respetan las políticas de descuentos, crédito, vales y puntos.

[ ] El monitor del cliente funciona.

[ ] El POS conserva su layout.

[ ] La aplicación funciona offline para operaciones permitidas.

[ ] La sincronización recupera operaciones pendientes.

[ ] Existen pruebas de fallos, concurrencia y regresión.

[ ] El instalador sigue funcionando.

[ ] Existe documentación operativa.

[ ] No hay secretos en el repositorio.

[ ] No se ejecutaron cobros reales sin autorización.

⸻

FASE 20 — ORDEN DE EJECUCIÓN

Trabajar en este orden:

1. Reconocimiento del repositorio.
2. Auditoría.
3. Matriz de reutilización.
4. Identificación de riesgos y dependencias.
5. Diseño adaptado al código real.
6. Pruebas base.
7. Contratos del proveedor.
8. Persistencia e idempotencia.
9. Backend y seguridad.
10. Point Smart.
11. Checkout digital.
12. QR.
13. Webhooks y recuperación.
14. Integración POS.
15. Caja.
16. Finanzas.
17. CRM/WhatsApp.
18. Monitor del cliente.
19. Reembolsos y conciliación.
20. Pruebas de regresión.
21. Instalador.
22. Documentación.
23. Validación final.

Avanza incrementalmente y conserva la posibilidad de revertir cada etapa.

Utiliza feature flags existentes o añade las mínimas necesarias, justificándolas.

No habilites producción automáticamente.

INFORME FINAL OBLIGATORIO

Entregar:

1. Resumen ejecutivo.
2. Commit SHA auditado.
3. Arquitectura encontrada.
4. Infraestructura reutilizada.
5. Cambios implementados.
6. Archivos modificados.
7. Migraciones realizadas.
8. Nuevos permisos.
9. Endpoints implementados.
10. Componentes UI afectados.
11. Pruebas ejecutadas y resultados.
12. Problemas conocidos.
13. Limitaciones del sandbox.
14. Pasos para vincular la Point Smart.
15. Pasos para configurar credenciales y Webhooks.
16. Pasos para verificar cobros y conciliación.
17. Evidencia de ausencia de regresiones.
18. Pendientes antes de habilitar producción.

REGLA FINAL

No declarar completada la integración porque compile o porque exista una pantalla de configuración.

Debe funcionar como parte integral del ERP, preservando consistencia de ventas, Caja, Finanzas, seguridad, permisos, trazabilidad, recuperación e integridad financiera.

No inventar funciones existentes, pruebas ejecutadas ni conexiones verificadas.

Si no puedes validar alguna capacidad externa por falta de credenciales, equipo, conectividad o infraestructura, dejarla implementada bajo una interfaz comprobable y reportar claramente su estado no verificado.

El objetivo es una integración enterprise, lista para validación de producción, no una demostración aislada.

INICIA AHORA CON FASE 0 Y FASE 1. NO ESCRIBAS CÓDIGO FUNCIONAL ANTES DE FINALIZAR Y DOCUMENTAR LA AUDITORÍA.