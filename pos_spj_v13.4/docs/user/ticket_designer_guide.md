# Guía de Usuario — Diseñador de Tickets

## Objetivo
Configurar experiencia de ticket para impresión térmica real por ESC/POS.

## Pestañas principales
- **Estructura**: plantilla/orden visual base + preview.
- **Marca**: presentación de logo/QR/barcode (la identidad oficial se gestiona en Configuración del Sistema).
- **Impresión ESC/POS**: papel, márgenes, tipografía base y prueba de impresión.

## Reglas importantes
- HTML es solo preview/PDF.
- Impresión física usa `PrinterService.print_ticket()` (ESC/POS).

## Flujo recomendado
1. Ajustar ancho papel (58/80).
2. Validar branding en Configuración del Sistema.
3. Revisar preview ESC/POS monoespaciado.
4. Ejecutar impresión de muestra térmica.

## Reimpresión y auditoría
- **Reimprimir ticket térmico**: ESC/POS.
- **PDF auditoría**: acción separada.

## Errores comunes
- "No hay impresora térmica ESC/POS configurada": configurar hardware y destino.
- QR/logo no visibles: revisar flags y contenido en configuración.
