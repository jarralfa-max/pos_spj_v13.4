# Benchmark de producto — referencia para SPJ ERP/POS

Investigación de documentación oficial consultada el 17 de octubre de 2026. Se estudian patrones y límites; SPJ no copiará interfaces ni presume paridad funcional. Cada decisión siguiente es una **inferencia de diseño**, no una afirmación de que el software de referencia implemente exactamente el flujo mexicano de SPJ.

| Producto | Patrón observado | Decisión SPJ | Fuente oficial |
| --- | --- | --- | --- |
| Odoo Accounting | Asientos automáticos desde facturas, POS e inventario; partida doble | Separar hecho operativo de asiento, mantener referencia y reconciliación; prohibir doble posting | [Contabilidad](https://www.odoo.com/documentation/19.0/es/applications/finance/accounting.html) |
| Odoo Manufacturing | Despiece, subproductos, lotes, BOM, unbuild, costos y órdenes de uno o varios pasos | Diferenciar transformación, rendimiento, receta, reconstrucción física y bundle comercial; incluir ejecución rápida de cortes | [Manufacturing](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing.html) |
| Odoo POS | Productos de catálogo e inventario configurado para venta | POS con búsqueda/escáner y estado vendible por sucursal; foto y SKU sin sobrecargar teclado del cajero | [POS products](https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/products.html) |
| ERPNext | Documentos de compra y recepción vinculados a efectos de stock y contabilidad; flujo POS conectado | Trazabilidad por línea desde compra hasta venta; controles contra doble ingreso y salida | [Purchase cycle](https://docs.frappe.io/erpnext/purchase-cycle-ledger-impact), [POS](https://docs.frappe.io/erpnext/point-of-sale) |
| Microsoft Business Central | Recepción, ubicación, picking y salida se modelan como pasos de almacén | Recepción no equivale a custodia logística ni a ubicación final; permitir almacén simple y avanzado | [Warehouse management](https://learn.microsoft.com/en-ca/dynamics365/business-central/warehouse-manage-warehouse) |
| Zoho CRM | Pipeline configurable y registro del proceso por etapas | CRM con lead → oportunidad → cotización → pedido → venta, actividades, SLA y cliente 360 | [Multiple sales pipelines](https://www.zoho.com/crm/tutorials/multiple-sales-pipeline/overview.html) |
| Microsoft Power BI | Seguridad por fila sobre un modelo semántico | Métricas definidas una vez, scope sucursal/rol aplicado en servidor a consultas y exportaciones | [RLS](https://learn.microsoft.com/power-bi/service-admin-rls) |
| Meta WhatsApp Business Platform | API oficial, webhooks, plantillas y herramientas de prueba | Microservicio único para ingestión y salida, plantillas y gestión de credenciales; no usar sesiones personales no oficiales | [Developer Hub](https://whatsappbusiness.com/developers/developer-hub/), [Meta Postman webhooks](https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference), [Meta Blueprint templates](https://www.facebookblueprint.com/student/path/253055-message-templates) |

## Diferenciación de SPJ

1. Operación multi sucursal con POS local desconectado y reconciliación central verificable.
2. Compra en origen con OC, compra directa o embarque provisional regularizado; contenedores físicos y custodia.
3. Despiece de varias proteínas: peso real, rendimientos versionados por producto, múltiples cortes con precios distintos y reconstrucción diferenciada de bundle.
4. Protección financiera configurable en caja: descuentos, puntos, vales, crédito y margen conjuntamente evaluados.
5. Arquitectura única para escritorio, web CRM/compras/finanzas/BI y móvil logística/delivery; microservicio WhatsApp separado con contratos y métricas.

## Criterio de investigación

Las referencias sirven para decisiones de diseño, no para asumir cumplimiento regulatorio en México ni equivalencia de funcionalidades. Impuestos, CFDI, privacidad, trabajo y cadena fría requieren validación profesional y configuración jurisdiccional antes del despliegue. Las prácticas y APIs externas deben revalidarse durante la implementación por cambios de versión.
