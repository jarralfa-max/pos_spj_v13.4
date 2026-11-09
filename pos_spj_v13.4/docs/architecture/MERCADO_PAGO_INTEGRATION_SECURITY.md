# Mercado Pago — Seguridad (SECURITY)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Contexto:** [TRD](MERCADO_PAGO_INTEGRATION_TRD.md) · [ADR](MERCADO_PAGO_INTEGRATION_ADR.md)

## 1. Credenciales

| Regla | Estado | Ítem |
|---|---|---|
| Token en el almacén de secretos de la máquina (Credential Manager o Fernet+DPAPI), nunca en SQLite en claro, widgets, `.ui`, logs, tickets, URLs, eventos ni git | Hecho para el almacén | — |
| Token temporalmente en cada caja | Decisión del responsable, en conflicto con el plan maestro | ADR-MP-001 |
| Segunda fuente `MP_ACCESS_TOKEN` en el entorno del microservicio | A retirar: el microservicio pide al ERP | PAY-022, PAY-025 |
| Ambiente sandbox o producción explícito; «Configurado» ≠ «Conectado» (prueba real contra la API) | Ausente | PAY-022 |
| Rotación y revocación (`rotate_secret`/`delete_secret` existen sin llamadores) | Parcial | PAY-022 |
| Filtro de redacción instalado en todos los handlers de log, con `Bearer <token>` | Ausente | SDLC-SEC-006 |
| Sin PAN ni CVV: el cobro con tarjeta ocurre en la terminal o en el checkout alojado | Por diseño | — |

## 2. Webhooks (ADR-MP-002)

- Sólo las rutas de webhook detrás de ngrok. La API completa y PostgreSQL nunca salen al túnel.
- Firma `x-signature` (HMAC con la clave secreta del webhook) y ventana de `ts`.
  - **No verificado:** la unidad del `ts` (segundos o milisegundos) se valida contra la documentación
    vigente (SDLC-WA-002).
  - El verificador del backend (`webhook_signature_verifier.py:47-60`) tiene defectos y se corrige en
    PAY-010.
- Límite de tamaño y parsing estricto.
- Se persiste antes de responder 200.
- Deduplicación por id de notificación.
- La notificación nunca cambia una venta por sí misma: se consulta el recurso con el token y se compara
  `collector_id` (una cuenta por empresa), monto, moneda y `external_reference`.
- La firma del microservicio se omite si falta `APP_ENV`. Debe fallar cerrada (SDLC-WA-002).

## 3. Permisos

Del registro central, con la convención `MODULO.accion`. Se reutilizan los códigos que ya existen antes
de crear otros:

| Capacidad conceptual (§12.2) | Código | Estado |
|---|---|---|
| Cobrar con MP | `POS.pago.mercado_pago` | Existe |
| Configurar la integración | `CONFIGURACION.integracion.*` | Existe; falta autorización en backend (SDLC-ARQ-PERM-001) |
| Asignar terminal | `CAJA.terminal_pago.*` | Existe parcial (PAY-023) |
| Conciliar operación de terminal | `CAJA.terminal_pago.conciliar_operacion` | Declarado sin uso (PAY-023) |
| Reembolsar | `CAJA.reembolso.*` | Existe. Confirmar un reembolso electrónico: el cajero con su permiso y alerta al gerente (decisión PAY-006) |
| Cancelar orden en proveedor | Nuevo, bajo `POS.pago.*` o `CAJA.terminal_pago.*` | PAY-023 |
| Conciliar liquidaciones | `FINANZAS.conciliacion.*` | Existe; se extiende en PAY-019 |
| Auditar | Nuevo `…auditar` en el módulo que se elija | PAY-023/024 |

Todo permiso se exige en el caso de uso, no sólo en el presentador. Nunca se decide por nombre de rol.
Un permiso nuevo necesita su migración de siembra: la lista congelada de la 206 deja fuera los módulos
nuevos.

## 4. Auditoría (PAY-024)

Cada operación de pago registra:

- usuario, sucursal y estación;
- importe, moneda, proveedor y referencia (enmascarada donde la vea un cliente);
- estado anterior y estado nuevo;
- evidencia de autorización y `operation_id` como correlation id.

`record_sales_audit_entry` existe sin llamadores: se usa, no se duplica.

## 5. Datos visibles al cliente

- **Ticket:** sólo los últimos 4 caracteres de la referencia, con `mask_payment_reference` (PAY-003).
- **Caja y Finanzas:** la referencia completa, porque la conciliación la necesita.
