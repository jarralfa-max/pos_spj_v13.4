# Mercado Pago — Decisiones de arquitectura (ADR)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09 · **Rama:** `fix/lote-4`
- **Base:** auditoría `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`. Ese archivo **no está en la rama base**
  (`git ls-tree HEAD` no lo lista): se lee con
  `git show 0d8c5844:pos_spj_v13.4/docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`. Su enlace desde
  `docs/sdlc/arquitectura/matriz-mercado-pago.md` está roto.
- **Formato:** el de `docs/architecture/hybrid_postgresql/08_decisions_adr.md`.
- **Estados:** **Aprobada** = la respondió el responsable (Alfred, 2026-11-05, en el intent de PAY-001,
  PAY-002 o PAY-004). **Propuesta** = decisión técnica derivada de la auditoría; necesita la aprobación
  del responsable antes de diseñar el ítem que depende de ella.

## ADR-MP-001 — El Access Token vive temporalmente en cada caja · Aprobada, con conflicto abierto

**Decisión.** Mientras no exista el servicio local de sucursal (SDLC-ARQ-HYB-001) ni un servidor central
operando, cada caja guarda el Access Token en su almacén de secretos actual:

- Credential Manager con `CRED_PERSIST_LOCAL_MACHINE`;
- o Fernet+DPAPI (`backend/security/secrets/…`, ver la auditoría §12.1).

Nunca va en SQLite en claro, en widgets, en logs ni en tickets. Respuesta del responsable: «cada caja
temporalmente».

**Conflicto que no se resuelve aquí.** Tres fuentes dicen otra cosa:

- `docs/sdlc/PLAN-MAESTRO.md`, decisión 1: «El token de Mercado Pago vive cifrado en la PC anfitriona
  (servicio local), nunca en las cajas».
- `docs/sdlc/inputs/mercado-pago.md` §12.1: el token sólo en el entorno backend autorizado.
- El mismo documento, §18: no obligar a instalar servicios sensibles en cada caja.

La respuesta del responsable es la más reciente y manda para el periodo temporal. Queda pendiente su
**criterio de salida**: cuándo y hacia dónde se mueve el token. Se debe registrar como pregunta abierta
en `BACKLOG.md`; este lote no edita el backlog.

**Consecuencias.**

- El adaptador (PAY-009) debe poder correr en la caja sin servidor. El puerto (ADR-MP-003) lo aísla, y
  moverlo a la PC anfitriona después no cambia a los llamadores.
- Riesgo: cada caja con token es una superficie de robo más.

  Mitigaciones:
  - token de producción con el mínimo alcance que permita la cuenta;
  - rotación documentada (PAY-022);
  - «Configurado» no debe decir «Conectado» (PAY-022);
  - el filtro de redacción instalado en los logs (SDLC-SEC-006).
- Dos cajas con el mismo token pueden crear órdenes en paralelo. La exclusión por terminal (PAY-012) y la
  idempotencia por `operation_id` (SDLC-ARQ-IDEM-001) dejan de ser opcionales.

## ADR-MP-002 — Webhooks entran por ngrok · Aprobada

**Decisión.** La entrada pública HTTPS de los webhooks es un túnel ngrok con dominio fijo gratuito
(`*.ngrok-free.app`), según la opción (a) de la decisión 1 del plan maestro. La usan WhatsApp y Mercado
Pago. El túnel sólo expone las rutas de webhook: nunca la API completa ni PostgreSQL. Respuesta del
responsable: «ngrok».

**Consecuencias.**

- El receptor corre en un solo equipo encendido 24/7. Como el token está en cada caja (ADR-MP-001), ese
  equipo también tiene el token, para consultar el recurso remoto antes de aplicar nada.
- El túnel puede caer y la cuota mensual del plan gratuito es limitada. Por eso la **conciliación por
  consulta** (PAY-011) es obligatoria: un pago con webhook perdido se resuelve al consultar la orden.
- Firma `x-signature`, ventana de `ts`, límite de tamaño e inbox durable antes de responder 200
  (PAY-010, SDLC-WA-002). El webhook es una señal para consultar, nunca una autorización.
- Sin reglas nuevas de firewall entrante: ngrok sale por conexión saliente.

## ADR-MP-003 — Puerto canónico: `PaymentProviderPort` nuevo en un contexto de pagos · Propuesta

**Contexto.** La auditoría cuenta seis puertos de pago sin uno canónico. Los principales:

| Puerto | Ubicación | Forma |
|---|---|---|
| `PaymentTerminalGateway` | `backend/application/cash_register/hardware.py:61` | `charge()` síncrono |
| `PaymentTerminalGatewayPort` | `backend/domain/device_management/hardware_ports.py:32` | sólo `is_ready()` |
| `PaymentProviderGateway` | `whatsapp_service/domain/whatsapp/payment_provider_ports.py:30` | sólo preferencias |
| `PaymentGateway` | `whatsapp_service/erp/gateways/payment_gateway.py:9` | escribe `anticipos` legacy |

**Decisión propuesta.**

1. Crear `PaymentProviderPort` en un contexto de pagos (`backend/domain/payments/`, PAY-007), con
   operaciones asíncronas por naturaleza:
   - `create_order`, `get_order` y `cancel_order`;
   - `refund`;
   - `list_terminals` y `link_terminal`;
   - `verify_notification`.

   Ninguna devuelve «aprobado» por crear: crear deja la intención en `SUBMITTED`, y el estado lo decide
   la consulta o el webhook verificado.
2. `PaymentTerminalGateway.charge()` no se extiende. Un cobro de Point no es síncrono: el cliente tarda,
   la terminal se ocupa y la respuesta se pierde. Estirar `charge()` reproduciría el diálogo modal que
   PAY-013 tiene que quitar.
3. `PaymentTerminalGatewayPort` se queda como salud del dispositivo (`is_ready`) en Dispositivos.
4. Los puertos del microservicio dejan de hablar con Mercado Pago por su cuenta. Piden la orden al ERP
   (PAY-025, SDLC-WA-004).

**Razón.** El POS no debe conocer endpoints, tokens ni esquemas HTTP del proveedor (§3 del documento). Un
adaptador anticorrupción (ACL) traduce los estados externos a los internos (ver `DATA_MODEL` §3).

## ADR-MP-004 — Cliente HTTP: `httpx` directo, no el SDK `mercadopago` · Propuesta

**Contexto.** `mercadopago==3.6.0` y `httpx==0.28.1` ya van en
`installer/windows/requirements-release.txt` (:39, :32). Nadie importa el SDK. El backlog conserva la
pregunta de PAY-009: «¿SDK oficial `mercadopago` o `httpx` directo?».

**Decisión propuesta: `httpx`.**

- Control explícito de `X-Idempotency-Key` estable por operación lógica, de los tiempos de espera y de
  los reintentos.
- Las pruebas usan `httpx.MockTransport`, sin red y sin pagos reales.
- Ya se usa en el backend. El instalador no necesita dependencias nuevas.

Si se aprueba, el SDK sale de `requirements-release.txt` en PAY-009 y no antes. La pregunta del backlog
queda abierta hasta que el responsable la conteste.

## ADR-MP-005 — Una cuenta cobradora por empresa y una cuenta de tesorería de procesadores · Aprobada

**Decisión.**

- Mercado Pago se usa hoy de forma **manual**: el cajero cobra en la app o la terminal y registra el pago.
  Hay **una cuenta cobradora por empresa** (respuesta a PAY-001).
- En Finanzas, Mercado Pago y las tarjetas comparten **una sola** cuenta de tesorería `PAYMENT_PROCESSOR`
  con espejo en la 1115 (respuestas a PAY-004).
- La venta carga directo a esa cuenta, no a la 1120.

Implementado en `fix/lote-4`:

- `backend/application/services/finance/treasury_resolution.py`;
- migración 385;
- el alta rechaza una segunda cuenta de procesador.

**Consecuencias.** La validación de `collector_id` del webhook (PAY-010) compara contra una sola cuenta
por empresa. Si un día hay una cuenta por sucursal, se reabren esta ADR y PAY-004.

## ADR-MP-006 — Contención manual mientras no haya integración · Aprobada e implementada

El cobro manual sigue siendo el flujo de producción. Desde `fix/lote-4`:

- La referencia es obligatoria y única para Mercado Pago, Tarjeta y Transferencia. El índice único
  parcial viene de la migración 384 (PAY-002, respuesta: «sí» para los tres métodos).
- Caja, Finanzas y el ticket conservan la referencia. El ticket la imprime enmascarada (PAY-003).
- El Corte X/Z desglosa lo cobrado por medio (PAY-005).
- Los reembolsos a medio electrónico siguen registrándose como ejecutados: PAY-006 está **bloqueado** por
  decisiones contables (ver `MERCADO_PAGO_INTEGRATION_TRD.md` §6).
