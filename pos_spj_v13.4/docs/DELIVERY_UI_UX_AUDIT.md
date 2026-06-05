# Auditoría UI/UX — Módulo Delivery (pos_spj_v13.4)

Fecha: 2026-05-23

## 1) Estructura actual del módulo Delivery
- `modulos/delivery.py` concentra demasiadas responsabilidades: UI (layout/lista/kanban/dialogs), policy de acciones, consultas SQL, wiring de eventos, y lógica operativa.
- `ModuloDelivery` incluye header, KPI bar propia, tabs de filtro, toggle Lista/Kanban, panel detalle, acciones y utilidades de corte.

## 2) Widgets actuales relevantes
- Header con botones: nuevo pedido, repartidores, corte, historial, auto-asignar, actualizar.
- KPI bar custom embebida (antes no reutilizable).
- Filtros tipo tabs por estado.
- Vista lista (`QListWidget`) + panel detalle (`QTableWidget`, labels y botones).
- Vista kanban por columnas de estado.
- Diálogos: nuevo pedido, asignar repartidor, etc.

## 3) SQL directo en UI (hallazgos)
- En `_seleccionar_pedido` se ejecutan `SELECT` directos para `delivery_items`, `venta_items` y `whatsapp_messages`.
- En `_auto_asignar_todos` se consulta `delivery_orders` directo.
- En `_init_tables` se crean/alteran tablas desde UI.

## 4) Lógica de negocio en UI (hallazgos)
- Cálculo de KPI y conteos por estado en UI.
- Reglas de acciones visibles por estado estaban acopladas solo a `estado`.
- Reglas de render para mostrador/reparto/programado no estaban totalmente separadas por workflow.

## 5) Acciones mal ubicadas
- En flujo mostrador podían aparecer acciones de reparto (`en_ruta`, `asignar repartidor`) por policy basada solo en estado.

## 6) Botones en estados incorrectos
- El conjunto de acciones no tomaba en cuenta `workflow_type` ni `adjustment_pending` en todos los puntos.

## 7) Estilos fuera de estándar/tokens
- KPI bar de delivery usaba estilos inline manuales (border/font/color) en lugar de componente estandarizado.

## 8) Cómo está hecho KPI Bar en Inventario
- Inventario usa `modulos/kpi_card.py::KPICard` con variantes semánticas (`primary/success/danger/warning/info`), barra superior de acento y layout consistente.
- En `inventario_local.py`, `_build_kpi_row` instancia `KPICard` para todos los KPIs.

## 9) Componentes reutilizables del KPI Bar de Inventario
- `KPICard` es reusable y ya está theme-aware.
- Tokens de `design_tokens.py` (Colors, Typography, Spacing) se consumen indirectamente por `KPICard`.

## 10) Diferencias UI actual vs UI objetivo
- Objetivo requiere “Pedidos y Entregas”, tabs por flujo (Todos/Mostrador/Reparto/Programados/Ajustes/Historial), KPI semántico orientado a operación de pedidos y acciones validadas por workflow.
- Estado actual original: más orientado a reparto puro, KPIs financieros/operativos mezclados, separación parcial de flujos, y policy incompleta por contexto de pedido.

## Conclusión de auditoría
Se debe migrar progresivamente a arquitectura por servicios/use-cases:
1. extraer SQL de UI a `DeliveryService/DeliveryRepository`,
2. mantener policy única para acciones válidas,
3. reutilizar `KPICard` para paridad visual con Inventario,
4. separar vistas por workflow/tabs operativas sin romper flujo WA existente.
