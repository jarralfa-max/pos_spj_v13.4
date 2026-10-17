# Aplicaciones web — CRM, Compras, Finanzas y BI

## 1. Plataforma compartida

Cuatro experiencias dentro de una misma web administrativa: misma identidad, API, navegación, componentes, sistema de permisos, búsqueda y trazabilidad. Cada área tiene rutas y espacio de trabajo propios; no hay cuatro bases de datos ni cuatro implementaciones del negocio. Backend web llama a los casos de uso y QueryServices canónicos. Responsiva en laptop/tablet; POS y hardware siguen en escritorio. PWA de logística/delivery se integra por contrato y session scope. Hoy el repositorio sólo contiene `frontend/web/logistics` y `frontend/web/delivery`, y `backend/api/main.py` sólo monta routers de móvil y analítica: las cuatro web apps son **propuestas**.

| Capa | Contrato |
| --- | --- |
| Sesión | OIDC/SSO o identidad propia endurecida; cookie HttpOnly Secure SameSite, CSRF para mutaciones y MFA en administración; servicio BFF cuando convenga. |
| API | `/api/v1/...`, OpenAPI, DTOs versionados, paginación/cursor, filtros validados, Idempotency-Key para comandos, ETag/expected_version. |
| Permisos | Mismo catálogo del escritorio; scope obligatorio `organization_id`, `branch_ids`, `warehouse_ids`; check en caso de uso y query, nunca sólo ocultar botón. |
| Web | Navegación por rol, tabla estándar, búsqueda asistida, formularios paso a paso, pendientes/conflictos, accesibilidad WCAG verificable. |
| Datos | API central/PostgreSQL propuestos, proyecciones sincronizadas desde sucursales; watermark «actualizado hasta» en cada métrica. |
| Auditoría | Acción, actor, antes/después redactados, motivo, cliente/app, IP apropiada, correlation ID. |

## 2. CRM web

**Navegación:** Resumen → Bandeja de actividades → Leads → Oportunidades → Clientes 360 → Cotizaciones/pedidos → Segmentos/campañas → Servicio → Configuración.

| Vista | Contenido y acción | Protección |
| --- | --- | --- |
| Pipeline | Kanban/lista por etapa, probabilidad y fecha, pérdidas con causa, próxima actividad | No inventar ventas desde mover tarjeta; conversión por UseCase. |
| Cliente 360 | Datos, compras, devoluciones, crédito, puntos, consentimientos, conversaciones y tickets | Enmascarar PII; acceso por sucursal/equipo y finalidad. |
| Cotización | Productos con precio vigente/snapshot, disponibilidad, vencimiento y aprobación | Margen y crédito en backend. |
| Campañas | Audiencia consentida, supresión, límite, plantilla aprobada, simulación/costo | No enviar al guardar; aprobación y outbox. |
| WhatsApp inbox | Conversaciones, asignación, SLA, handoff, estado de entrega y relación cliente | PII y consentimiento; transmisión desde microservicio. |

## 3. Compras web

**Navegación:** Tablero → Requisiciones → Cotizaciones/RFQ → Comparativo → OC → Compras directas → Embarques/recepciones → Facturas/diferencias → Proveedores → Analítica.

| Vista | Contenido y acción | Protección |
| --- | --- | --- |
| Solicitud | Sugerencia forecast/stock, necesidad por sucursal, adjunto y presupuesto | Creador no aprueba su límite propio. |
| Comparativo | Oferta, flete, impuestos, calidad, plazo y costo total | Historial versionado, explicación de adjudicación. |
| OC/directa | Líneas por pieza/peso, proveedor, entrega en origen o sucursal | Límites por usuario/rol, idempotencia, costo snapshot. |
| Recepción | Documento, embarque/QR, tolerancia, aceptado/rechazado/cuaren. | Web puede supervisar; captura móvil/desktop comparte mismo comando. |
| Factura | Match 2/3 vías, discrepancia, CxP y pago | No editar entrada de stock para «cuadrar» factura. |

## 4. Finanzas web

**Navegación:** Pendientes de contabilizar → Mayor/diarios → CxP → CxC → Tesorería/bancos → Conciliación → Presupuestos → Cierres → Auditoría.

| Vista | Contenido y acción | Protección |
| --- | --- | --- |
| Bandeja de excepciones | Evento huérfano, asiento fallido, duplicado, diferencia de caja | Reprocesar idempotentemente, no editar el ledger. |
| Documento origen | Venta/compra/caja/nómina y asiento(s) vinculados | Drill-down con permisos cruzados. |
| Conciliación | Importar extracto, proponer matching, aprobar y reversar | Separar importación, propuesta y aprobación. |
| Cierre | Periodo, bloqueos, cuentas sin conciliar, diferencias, reapertura autorizada | Asiento balanceado y periodo abierto. |
| Tesorería | Saldos, pagos programados, caja entregada, depósitos | Doble control por umbral; sin mostrar datos bancarios completos a todos. |

## 5. BI web

**Navegación:** Ejecutivo → Ventas → Margen por corte → Inventario → Compras/proveedores → Producción/rendimiento → Clientes → Logística/entregas → Caja/finanzas → RR. HH. agregado → Alertas → Diccionario de métricas.

Cada KPI expone fórmula, fuente, rango, timezone, latencia, filtros, dueño, versión y permiso. Drill-down a documento fuente sin saltarse RBAC; exports y filtros aplican la misma seguridad por fila. Proyecciones sólo lectura, snapshots reproducibles y reconciliación contra ledgers. No promediar precios de cortes para afirmar rentabilidad; costo asignado por lote/merma y venta real. Ejemplos: rendimiento real = suma de pesos salida / peso consumido; margen neto = venta neta − costo salida − descuentos − costos asignados; «ventas completadas» excluye reversadas mediante métricas declaradas.

## 6. Contratos web y aceptación

- Componentes base: AppShell, PageHeader, FilterBar, SearchSelector, StandardTable, DetailDrawer, ActivityTimeline, ApprovalPanel, KPIBar/Chart y estados Loading/Empty/Error/Offline/SyncPending/PermissionDenied.
- Aplicar búsqueda de entidad a cliente/producto/proveedor/empleado; no cargar listas masivas. IDs técnicos fuera de tablas visibles y tickets.
- Pruebas E2E por rol: comprador crea y gerente aprueba, receptor confirma, contador concilia, analista ve sólo sus sucursales; intento de IDOR por URL/API devuelve denegación.
- Latencia: registrar p95 por página y consulta; paginar toda vista de alto volumen. Cambios de esquema de API consumidos con contract tests por los cuatro frontends.
