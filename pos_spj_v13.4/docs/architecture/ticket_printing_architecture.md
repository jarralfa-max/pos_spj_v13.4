# Arquitectura de Impresión de Tickets (ESC/POS)

## Por qué no HTML para ticket térmico físico
Las impresoras térmicas no renderizan HTML/CSS; requieren bytes ESC/POS RAW. HTML/QPrinter puede cortar, escalar o deformar contenido.

## Ruta oficial de impresión térmica
1. `TicketPrintModel`
2. `TicketESCPOSRenderer`
3. bytes ESC/POS
4. `PrinterService.print_ticket`
5. `PrintTransport` RAW (TCP/Serial/USB_WIN32/FILE)

## Preview vs PDF vs Ticket físico
- **Preview HTML**: aproximado, no vinculante.
- **Preview texto ESC/POS**: aproximación monoespaciada térmica.
- **PDF auditoría**: evidencia/documentación.
- **Ticket físico**: solo ESC/POS RAW.

## Configuración de impresora
Usar `PrinterService.validate_ticket_printer_config()` y `print_test_ticket()`.
- `SYSTEM` inválido para térmica.
- TCP requiere `ip:puerto`.
- Serial requiere `COMx` o `/dev/tty*` + baud.

## Branding
Fuente oficial: Configuración del Sistema (global) con fallback legacy controlado.

## Layout por bloques
`TicketLayoutConfig` + `TicketLayoutRepository` persistido como `ticket_layout_config`.
Bloques: logo, header, sale_info, customer, items, totals, payment, loyalty, fomo, qr, barcode, footer, legal.

## Fidelidad/FOMO
`TicketMessageEngine` genera mensajes desde contexto/servicios de negocio (no desde UI).

## Pruebas recomendadas
- `python -m pytest tests/test_ticket_escpos_renderer.py -q`
- `python -m pytest tests/test_printer_service_config_validation.py -q`
- `python -m pytest tests/test_ticket_pipeline_integration.py -q`

## Troubleshooting
- **Ticket cortado**: revisar `paper_width_mm`, `feed_lines`, `cut_type`.
- **Caracteres raros**: usar `cp850`/`latin-1`; revisar sanitización.
- **Logo no aparece**: validar `brand_logo_b64` o fallback `ticket_logo_b64`.
- **QR no aparece**: revisar `show_qr` y contenido QR.
- **Impresora no responde**: validar transporte/destino con `validate_ticket_printer_config()`.
- **Corte no funciona**: probar `cut_type` y compatibilidad del firmware.
- **Acentos mal impresos**: ajustar encoding térmico (`cp850` recomendado).
