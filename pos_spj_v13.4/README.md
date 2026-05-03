# SPJ POS v13.0 — Enterprise Edition

Sistema de Punto de Venta para carnicerías y negocios cárnicos.

## Requisitos
```
Python 3.9+   PyQt5   reportlab   Pillow   bcrypt   qrcode
pip install -r requirements.txt
```

## Instalación
```bash
python main.py
```

## v13.0 — Cambios principales

### Estabilidad y arranque
- Crash handler global — cualquier error no capturado se registra en log y muestra mensaje
- Instancia única — previene abrir dos POS en la misma BD (QLocalServer)
- Verificación de integridad BD al arrancar (PRAGMA integrity_check)
- Restauración automática de backup si la BD está dañada
- Verificador de actualizaciones en segundo plano (VersionChecker)
- VACUUM/ANALYZE semanal automático

### Bot WhatsApp v13
- Verifica horario de la sucursal antes de aceptar pedidos
- Pedidos fuera de horario se programan para cuando abra
- Pregunta sucursal si el número es compartido entre varias
- Pregunta hora deseada → asigna prioridad (alta/normal/baja)
- Flujo completo de cotización via WhatsApp:
  - Recopila productos + fecha de entrega
  - Genera cotización en BD con número COT-XXXX
  - Calcula anticipo (por categoría + por monto, criterio configurable)
  - Envía link de MercadoPago para anticipo o confirma efectivo
  - Crea orden ORD-XXXX y notifica al personal y al cliente
  - Recordatorios automáticos D-2 y D-1 antes de entrega

### Anticipos configurables
- Reglas por categoría de producto (ej: cortes especiales 50%)
- Reglas por monto total (rangos con % creciente)
- Criterio combinación: máximo / mínimo / suma (configurable)
- Exenciones: crédito aprobado / nivel fidelidad / monto mínimo

### Escalación de pedidos sin atender
- 5 min → pedido amarillo, nueva alerta
- 15 min → WhatsApp al gerente
- 30 min → respuesta automática al cliente
- Todos los tiempos configurables

### Notificaciones en POS
- Badge "📦 Pedidos (N) 🔴" en la barra de menú
- Se actualiza en tiempo real via GestorNotificaciones
- Clic abre módulo Delivery directamente

### Nuevas tablas (migración 047)
- ordenes_cotizacion, anticipo_reglas, anticipo_config
- lotes_tarjetas_pdf, rol_permisos, usuarios_sucursales
- Horarios en sucursales, campos extras en usuarios y pedidos_whatsapp

### Bugs corregidos
- Stock check antes de agregar al carrito del POS
- Auto-focus en campo de búsqueda al abrir el POS
- Lambda-in-loop bug en delivery.py y finanzas.py
- SQL injection en delivery.py
- __init__.py añadidos en 7 paquetes faltantes
