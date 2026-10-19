# Plan de desarrollo y puertas de calidad

Este plan describe cómo **construir** el producto desde cero con el repositorio como referencia, sin prometer completar todos los contextos en un único cambio. Una fase incorpora trabajo funcional, migración, UX, permisos, pruebas, manual y telemetría. Ningún cronograma cerrado se fija sin tamaño de equipo, presupuesto e instalaciones de prueba.

## Fase 0 — Descubrimiento verificable

Inventariar todas las rutas de escrituras y lecturas reales, SQL/DDL, módulos desktop/web, permisos, eventos y outbox, WhatsApp, instalador y dependencias eliminadas. Ejecutar DB limpia y flujos actuales; registrar paridad preservable, duplicados, datos maestros y contratos que no deben romperse. Aprobar diccionario de términos, ownership, capacidades por instalación, alcance multi sucursal y políticas financieras. Entrega: matriz «reusar / corregir / retirar / crear» con pruebas de caracterización.

## Fase 1 — Plataforma

Identidad canónica, permisos rol/usuario/scope, sesión, auditoría, secretos, configuración versionada, UUIDv7/Decimal, DB/migraciones, UoW/outbox/inbox, health, telemetría, CI, API central y sincronización piloto. Diseño de resiliencia local SQLite + central PostgreSQL y respaldos probados. Puerta: sin sesión o permiso todos los comandos fallan; evento duplicado no duplica efecto; instalar/actualizar en Windows limpio.

## Fase 2 — Maestros y ciclo comercial mínimo

Producto/categoría/unidad/lote, proveedor/cliente, precios, compras con OC/directa, recepción, inventario ledger, POS/caja/finanzas, tickets. Un flujo completo de abarrotes y uno por peso en sucursal, con reversa y pago mixto. Puerta: cantidades/costos y mayor reconciliados; ningún SQL de UI; saldos y folios comprensibles.

## Fase 3 — Cárnicos y logística

Despiece multiproteína y transformación directa, rendimiento versionado, costos/genealogía, calidad/merma; contenedores, embarques, custodia, cadena fría, transferencias y recepción en móvil. Puerta: balance masa/costo y una sola entrada stock por recepción, offline con conflicto de sello/custodia resuelto explícitamente.

## Fase 4 — Web y canales

Web CRM/Compras/Finanzas/BI sobre API canónica y seguridad por fila; WhatsApp remoto oficial con bandeja, pedidos borrador, consentimiento y métricas; delivery. Puerta: ruta IDOR denegada, E2E por rol, eventos idempotentes, dashboard con watermark y métricas reconciliadas.

## Fase 5 — Profundidad empresarial

Fidelidad/vales/cupones, forecast, precios avanzados, cotizaciones, RR. HH., activos, BI escenarios, promociones, integraciones adicionales, compliance aplicable y optimización. Puerta: protección de margen, pasivos y créditos balanceados; cierre de periodo y restauración probados.

## Dependencias y aceptación

| Dependencia | No avanzar hasta que... |
| --- | --- |
| Web financiera | Sync/autoridad, ledger y RBAC multi sucursal tienen tests de reconciliación. |
| Vale de canje único offline | Hay autoridad global disponible o cupos preasignados por sucursal con conciliación sin sobregiro. |
| Producción directa | Lote y costos, versión de esquema y UoW consumo/salida están probados. |
| WhatsApp pedidos | Identidad, consentimiento, catálogo/precio/reserva por API y handoff están establecidos. |
| Logística independiente | QR secret, wiring, instalador, shell/rutas y permisos se activan juntos. |
| Release | Instalación nueva + actualización desde versión soportada, backup/restauración, smoke de hardware y plan de soporte. |

## Estrategia de pruebas y evidencia

- Unidad: invariantes dominio, dinero, rendimiento, permisos y redondeo.
- Integración: UoW, transacciones, migraciones, outbox, adapters Meta/DB con sandbox, impresión y hardware simulado.
- Contrato: OpenAPI, eventos versionados, DTOs web/desktop y consumidores.
- E2E: compra→carga→recepción→transformación→venta→caja→finanzas→BI y cotización WhatsApp→pedido→delivery.
- Seguridad: IDOR por branch, payload tampering, CSRF, secretos/PII en logs, token/consentimiento, límites de campaña, doble aprobación.
- Resiliencia: caída red/API/DB/proveedor, reintentos, dos estaciones concurrentes, restore/upgrade/rollback.
- Usabilidad: operador real con escáner/báscula, pruebas teclado, móvil con guantes y baja conectividad, escritorio en dos resoluciones y modo claro/oscuro.

**Artefactos de salida por fase:** arquitectura actual y objetivo, ADRs, esquema versionado, catálogo de eventos/permisos, prototipos, OpenAPI, pruebas automáticas, captura de UX, bitácora de brechas y guía operativa. Un ítem pendiente no se marca completado por generar documentos o carpetas.
