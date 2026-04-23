# Auditoría Enterprise SPJ POS v13.4 (2026-04-23)

Documento de trabajo generado por revisión técnica/operativa del repositorio.

## Evidencias críticas verificadas

1. **El sistema no es Odoo modular estándar**, es una app PyQt + SQLite con transición a arquitectura por capas documentada en `CLAUDE.md` (legacy + objetivo).  
2. **Riesgo de cancelación de ventas por fallback inseguro en UI**: llamada errónea a `SalesReversalService(self.container.db)` sin `branch_id`, que dispara excepción y cae a `UPDATE ventas SET estado='cancelada'` directo.  
3. **Autenticación acepta texto plano y SHA-256 legacy**, no obliga migración a bcrypt.  
4. **Múltiples `except Exception: pass`** en componentes críticos (auth, auditoría, ventas, configuración).  
5. **API web con CORS abierto y auth opcional en “dev mode”**, además bug que ignora `db_path` recibido.  
6. **Tokens de delivery PWA en memoria + CORS `*`**, sin revocación persistente ni trazabilidad robusta.

## Alcance

Se revisaron módulos clave de ventas, caja, inventario, transferencias, merma, configuración, seguridad/autenticación, WhatsApp/webapp, reversas de venta, eventos y auditoría.

## Estado de ejecución del plan

**Plan completado al 100% (2026-04-23).**

Se cerraron los frentes definidos para hardening fase 0:

- Seguridad y autenticación (migración de hash legacy, lockout y endurecimiento de repositorio).
- Flujo de venta/cancelación con trazabilidad y reducción de rutas inseguras.
- Outbox persistente con despacho dedicado y métricas de observabilidad.
- Endurecimiento de WebApp/WhatsApp (token obligatorio y validaciones robustas).
- Auditoría con opciones fail-closed/strict y pruebas de regresión asociadas.
