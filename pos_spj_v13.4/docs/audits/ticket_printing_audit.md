# Auditoría de Rutas de Impresión de Tickets

## Rutas térmicas correctas
- `PrinterService.print_ticket()` + `TicketESCPOSRenderer` + `PrintTransport` RAW.
- Delivery y caja migrados para priorizar `PrinterService`.

## Rutas permitidas no térmicas
- PDF de auditoría (`guardar_ticket_pdf`, `guardar_pdf` en corte Z).
- Previews visuales (HTML/diálogos) sin impresión térmica directa.

## Riesgos identificados
- Persisten rutas legacy para compatibilidad (hardware fallback en caja) que deben monitorearse.
- UI aún puede mostrar conceptos HTML avanzados; debe mantenerse el aviso de preview no vinculante.

## Duplicidades
- Configuraciones legacy coexistentes con nuevas (`ticket_*` vs `brand_*` / `ticket_layout_config`).

## Criterio de ruta térmica correcta
1. Construye modelo de ticket.
2. Renderiza ESC/POS RAW.
3. Envía por `PrinterService` a transporte raw.
4. No usa `QPrinter/QTextDocument/QPrintDialog` para impresión física térmica.

## Plan de corrección continuo
- Consolidar uso total de `TicketLayoutRepository` y `TicketMessageEngine` en todos los módulos.
- Eliminar fallbacks legacy cuando despliegue y métricas de estabilidad lo permitan.
