# CASH-5 — Configuración de Caja

Fecha: 2026-08-03  
Estado: `IMPLEMENTED` como configuración canónica; los diálogos de edición se conectarán al integrar navegación.

## Entregado

- Jerarquía `SYSTEM → COMPANY → BRANCH → REGISTER → USER` con precedencia determinista.
- Vigencias UTC `[effective_from, effective_to)` y versiones sin sobrescritura histórica.
- Denominaciones Decimal configurables por moneda.
- Medios de pago con indicador explícito de afectación al efectivo físico.
- Límites configurables por operación/scope, umbral y hard cap.
- Alertas por evento, severidad y canales `IN_APP`, `WHATSAPP`, `EMAIL`.
- Destinatarios WhatsApp validados como E.164.
- Perfiles compuestos únicamente por permisos `CASH_*`.
- Página PyQt canónica en español con PageHeader, StandardTable y botones estándar.
- QueryService y repositorio de lectura; la UI no ejecuta SQL.

## Persistencia

La migración 176 crea ocho tablas `cash_*`, índices de resolución y FKs. Está registrada en `engine.py` y en el bootstrap limpio `m000_base_schema.py`. No inserta denominaciones, métodos, límites ni alertas arbitrarias: una instalación nace sin defaults de negocio y exige configuración explícita.

## UI

La página presenta secciones Jerarquía, Vigencias, Denominaciones, Medios de pago, Límites, Alertas, WhatsApp y Permisos. Las acciones se emiten como señales para Use Cases; no se agregó persistencia directa ni lógica funcional a PyQt.

## Tests

- Dominio: jerarquía, vigencias, Decimal, E.164, alertas y permisos.
- Integración: schema born-clean, índices, FKs, repetibilidad y ausencia de seeds arbitrarios.
- Arquitectura: UI estándar, español, sin SQL/commit/rollback/estilos inline.
