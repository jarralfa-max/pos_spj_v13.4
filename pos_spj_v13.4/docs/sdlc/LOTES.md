# Lotes de corrección directa

Generado desde `BACKLOG.md`. Cada lote agrupa ítems de una misma área (máximo 6), en orden de dependencias y prioridad. Se ejecuta con `/sdlc-corregir lote N` o, en paralelo, `/sdlc-corregir ronda N`.

**Rondas:** los lotes de una misma ronda son de áreas distintas y no dependen entre sí, así que pueden correr al mismo tiempo, cada uno con su subagente y su rama `fix/lote-N`. Una ronda empieza cuando los PRs de las rondas anteriores ya están integrados en la rama base.

**Marcas:** ✓ intent aprobado · B intent en borrador (apruébalo o el comando lo salta) · ? tiene pregunta abierta en el backlog (el comando lo intenta y lo bloquea si necesita la decisión).


## Ronda 1 — 10 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 1 | Caja y turnos | SDLC-ARQ-SHIFT-001 (P0·✓), SDLC-ARQ-SHIFT-004 (P0·✓), SDLC-ARQ-SHIFT-002 (P1·✓), SDLC-ARQ-SHIFT-003 (P1·✓), SDLC-CASH-001 (P1·B), SDLC-CASH-002 (P2·B?) | 4/6 |
| 2 | Finanzas y RRHH | SDLC-FIN-002 (P0·B?), SDLC-FIN-003 (P1·B?), SDLC-HR-001 (P1·B?), SDLC-HR-002 (P1·B), SDLC-FIN-001 (P2·B), SDLC-FIN-004 (P2·B?) | 0/6 |
| 3 | Instalador y actualizador | SDLC-ARQ-INST-001 (P0·✓), SDLC-INST-001 (P0·B?), SDLC-ARQ-INST-002 (P1·✓), SDLC-INST-002 (P1·B?), SDLC-INST-003 (P2·B?), SDLC-ARQ-INST-003 (P1·✓) | 3/6 |
| 4 | Mercado Pago | SDLC-PAY-002 (P0·B?), SDLC-PAY-003 (P1·B), SDLC-PAY-004 (P1·B?), SDLC-PAY-005 (P1·B), SDLC-PAY-006 (P1·B?), SDLC-PAY-001 (P2·B?) | 0/6 |
| 5 | Núcleo y configuración | SDLC-CORE-012 (P0·B), SDLC-BI-001 (P1·B), SDLC-CORE-001 (P1·B), SDLC-CORE-007 (P1·B?), SDLC-SET-001 (P1·✓), SDLC-ARQ-TEST-001 (P2·✓) | 2/6 |
| 6 | Pedidos y repartos | SDLC-ORD-004 (P0·B?), SDLC-ORD-001 (P1·B?), SDLC-ORD-005 (P1·B?), SDLC-ORD-002 (P2·B), SDLC-ORD-003 (P2·B?), SDLC-ORD-006 (P2·B?) | 0/6 |
| 7 | Permisos, sesiones y seguridad | SDLC-ARQ-PERM-001 (P0·✓), SDLC-ARQ-SESS-003 (P0·✓), SDLC-ARQ-PERM-003 (P1·✓), SDLC-ARQ-PERM-002 (P0·✓), SDLC-ARQ-AUD-001 (P1·✓), SDLC-ARQ-PERM-004 (P1·✓) | 6/6 |
| 8 | Terminales y sincronización | SDLC-ARQ-TERM-002 (P0·✓), SDLC-SYNC-001 (P0·B?), SDLC-SYNC-002 (P0·B?), SDLC-ARQ-TERM-001 (P1·✓), SDLC-SYNC-003 (P1·B), SDLC-ARQ-SYNC-001 (P0·✓) | 3/6 |
| 9 | WhatsApp | SDLC-WA-002 (P0·✓?), SDLC-WA-001 (P0·B?), SDLC-WA-003 (P1·B?), SDLC-WA-021 (P0·B?), SDLC-WA-004 (P1·B?), SDLC-WA-005 (P1·B) | 0/6 |
| 10 | UI / Design System | SDLC-UI-001 (P1·✓), SDLC-UI-002 (P2·✓), SDLC-UI-003 (P2·✓), SDLC-UI-004 (P2·✓?), SDLC-UI-005 (P2·✓), SDLC-UI-007 (P2·✓) | 5/6 |

## Ronda 2 — 9 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 11 | Inventario, compras y producción | SDLC-INV-001 (P0·B?), SDLC-LOSS-001 (P0·B?), SDLC-PROC-002 (P0·B), SDLC-TRF-001 (P0·B), SDLC-TRF-003 (P0·B?), SDLC-INV-003 (P1·B?) | 0/6 |
| 12 | Ventas y precios | SDLC-ARQ-IDEM-001 (P0·✓), SDLC-SALES-001 (P0·B?), SDLC-ARQ-IDEM-002 (P1·✓), SDLC-ARQ-IDEM-003 (P1·✓), SDLC-ARQ-IDEM-004 (P1·✓), SDLC-CRED-001 (P1·B?) | 4/6 |
| 13 | Clientes y fidelidad | SDLC-CRM-001 (P1·B), SDLC-CRM-002 (P1·B?), SDLC-CRM-003 (P2·B), SDLC-LOY-001 (P3·B?) | 0/4 |
| 14 | Permisos, sesiones y seguridad | SDLC-ARQ-SESS-001 (P1·✓), SDLC-ARQ-SESS-002 (P1·✓), SDLC-SEC-001 (P1·B), SDLC-SEC-002 (P1·B), SDLC-ARQ-AUD-002 (P2·✓), SDLC-ARQ-AUD-003 (P2·✓) | 4/6 |
| 15 | Terminales y sincronización | SDLC-ARQ-HYB-001 (P1·✓), SDLC-ARQ-HYB-002 (P1·✓), SDLC-ARQ-SYNC-002 (P1·✓), SDLC-ARQ-TERM-003 (P1·✓), SDLC-ARQ-TERM-004 (P1·✓), SDLC-ARQ-TERM-005 (P1·✓) | 6/6 |
| 16 | WhatsApp | SDLC-WA-006 (P1·B), SDLC-WA-008 (P1·B?), SDLC-WA-012 (P1·B), SDLC-WA-013 (P1·B?), SDLC-WA-020 (P1·B), SDLC-WA-028 (P1·B) | 0/6 |
| 17 | Activos | SDLC-ASSET-001 (P2·✓), SDLC-ASSET-002 (P2·B), SDLC-ASSET-004 (P2·B?), SDLC-ASSET-005 (P2·B), SDLC-ASSET-006 (P2·B?), SDLC-ASSET-007 (P2·B) | 1/6 |
| 18 | Núcleo y configuración | SDLC-BI-002 (P2·B), SDLC-BI-003 (P2·B), SDLC-CORE-002 (P2·B?), SDLC-CORE-003 (P2·B), SDLC-CORE-008 (P2·B), SDLC-CORE-010 (P2·B) | 0/6 |
| 19 | Pedidos y repartos | SDLC-ORD-007 (P2·B?), SDLC-ORD-008 (P2·B), SDLC-ORD-009 (P2·B?), SDLC-ORD-010 (P3·B), SDLC-ORD-011 (P3·B?) | 0/5 |

## Ronda 3 — 5 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 20 | Terminales y sincronización | SDLC-SYNC-004 (P1·B), SDLC-SYNC-005 (P1·B?), SDLC-ARQ-SYNC-003 (P1·✓), SDLC-ARQ-OFF-001 (P1·✓), SDLC-ARQ-HYB-003 (P2·✓), SDLC-ARQ-HYB-004 (P2·✓) | 4/6 |
| 21 | WhatsApp | SDLC-WA-029 (P1·B?), SDLC-WA-034 (P1·B?), SDLC-WA-035 (P1·B?), SDLC-WA-038 (P1·B), SDLC-WA-007 (P2·B), SDLC-WA-016 (P2·B) | 0/6 |
| 22 | Activos | SDLC-ASSET-008 (P2·B?), SDLC-ASSET-009 (P3·B?), SDLC-ASSET-010 (P2·B?), SDLC-ASSET-011 (P2·B), SDLC-ASSET-012 (P2·B), SDLC-ASSET-013 (P2·B) | 0/6 |
| 23 | Mercado Pago | SDLC-PAY-007 (P2·B), SDLC-PAY-008 (P2·B?), SDLC-PAY-010 (P2·B), SDLC-PAY-016 (P2·B), SDLC-PAY-017 (P2·B?), SDLC-PAY-018 (P2·B?) | 0/6 |
| 24 | Permisos, sesiones y seguridad | SDLC-ARQ-PERM-005 (P2·✓), SDLC-ARQ-SCOPE-001 (P2·✓), SDLC-SEC-003 (P2·B), SDLC-SEC-004 (P2·B), SDLC-SEC-006 (P2·B), SDLC-ARQ-PERM-006 (P3·✓) | 3/6 |

## Ronda 4 — 8 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 25 | Ventas y precios | SDLC-PRICE-001 (P1·B?), SDLC-PRICE-002 (P1·B?), SDLC-SALES-002 (P1·B?), SDLC-SALES-003 (P1·B), SDLC-ARQ-IDEM-005 (P2·✓), SDLC-SALES-004 (P2·B?) | 1/6 |
| 26 | WhatsApp | SDLC-WA-048 (P2·B), SDLC-WA-019 (P1·B?), SDLC-WA-036 (P1·B?), SDLC-WA-009 (P2·B?), SDLC-WA-010 (P2·B), SDLC-WA-011 (P2·B?) | 0/6 |
| 27 | Activos | SDLC-ASSET-014 (P2·B), SDLC-ASSET-015 (P2·B), SDLC-ASSET-016 (P2·B?), SDLC-ASSET-017 (P2·B), SDLC-ASSET-018 (P2·B), SDLC-ASSET-019 (P2·B?) | 0/6 |
| 28 | Mercado Pago | SDLC-PAY-019 (P2·B?), SDLC-PAY-022 (P2·B?), SDLC-PAY-009 (P2·B?), SDLC-PAY-011 (P2·B), SDLC-PAY-012 (P2·B?), SDLC-PAY-013 (P2·B) | 0/6 |
| 29 | Núcleo y configuración | SDLC-CORE-011 (P2·B), SDLC-SET-002 (P2·B?), SDLC-SET-003 (P2·B?), SDLC-CORE-004 (P3·B), SDLC-CORE-005 (P3·B), SDLC-CORE-006 (P3·B) | 0/6 |
| 30 | Terminales y sincronización | SDLC-ARQ-OFF-002 (P2·✓), SDLC-ARQ-SYNC-004 (P2·✓), SDLC-ARQ-TERM-006 (P2·✓) | 3/3 |
| 31 | UI / Design System | SDLC-UI-010 (P2·✓), SDLC-UI-011 (P2·✓), SDLC-UI-012 (P2·✓), SDLC-UI-013 (P2·✓), SDLC-UI-016 (P2·✓), SDLC-UI-017 (P2·✓?) | 5/6 |
| 32 | Permisos, sesiones y seguridad | SDLC-SEC-005 (P3·B) | 0/1 |

## Ronda 5 — 7 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 33 | Inventario, compras y producción | SDLC-PROC-001 (P0·B?), SDLC-INV-002 (P1·B), SDLC-LOG-002 (P1·B?), SDLC-PROC-004 (P1·B?), SDLC-PUR-001 (P1·B), SDLC-TRF-002 (P1·B) | 0/6 |
| 34 | Activos | SDLC-ASSET-020 (P2·B?), SDLC-ASSET-021 (P2·B), SDLC-ASSET-022 (P2·B), SDLC-ASSET-024 (P2·B?), SDLC-ASSET-023 (P2·B?), SDLC-ASSET-026 (P2·B) | 0/6 |
| 35 | Mercado Pago | SDLC-PAY-014 (P2·B), SDLC-PAY-015 (P2·B), SDLC-PAY-020 (P2·B), SDLC-PAY-021 (P2·B?), SDLC-PAY-023 (P2·B), SDLC-PAY-024 (P2·B) | 0/6 |
| 36 | UI / Design System | SDLC-UI-018 (P2·✓), SDLC-UI-019 (P2·✓), SDLC-UI-020 (P2·✓), SDLC-UI-021 (P2·✓), SDLC-UI-022 (P2·✓), SDLC-UI-023 (P2·✓) | 6/6 |
| 37 | Ventas y precios | SDLC-SALES-005 (P2·B), SDLC-SALES-006 (P2·B), SDLC-SALES-007 (P3·B) | 0/3 |
| 38 | WhatsApp | SDLC-WA-014 (P2·B), SDLC-WA-015 (P2·B), SDLC-WA-017 (P2·B), SDLC-WA-018 (P2·B), SDLC-WA-022 (P2·B), SDLC-WA-023 (P2·B?) | 0/6 |
| 39 | Núcleo y configuración | SDLC-CORE-009 (P3·B?) | 0/1 |

## Ronda 6 — 5 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 40 | Activos | SDLC-ASSET-027 (P2·B), SDLC-ASSET-025 (P2·B), SDLC-ASSET-028 (P2·B?), SDLC-ASSET-029 (P2·B), SDLC-ASSET-032 (P2·B), SDLC-ASSET-003 (P3·B?) | 0/6 |
| 41 | Inventario, compras y producción | SDLC-INV-004 (P2·B), SDLC-INV-005 (P2·B), SDLC-INV-008 (P2·B?), SDLC-LOG-001 (P2·B), SDLC-PROC-003 (P2·B), SDLC-PROD-001 (P2·B?) | 0/6 |
| 42 | Mercado Pago | SDLC-PAY-025 (P2·B), SDLC-PAY-026 (P2·B), SDLC-PAY-027 (P2·B), SDLC-PAY-028 (P3·B?), SDLC-PAY-029 (P3·B) | 0/5 |
| 43 | UI / Design System | SDLC-UI-024 (P2·✓), SDLC-UI-025 (P2·✓), SDLC-UI-029 (P2·✓), SDLC-UI-006 (P3·✓), SDLC-UI-008 (P3·✓), SDLC-UI-009 (P3·B) | 5/6 |
| 44 | WhatsApp | SDLC-WA-024 (P2·B), SDLC-WA-026 (P2·B?), SDLC-WA-027 (P2·B), SDLC-WA-031 (P2·B), SDLC-WA-032 (P2·B), SDLC-WA-037 (P2·B) | 0/6 |

## Ronda 7 — 4 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 45 | WhatsApp | SDLC-WA-039 (P2·B), SDLC-WA-044 (P2·B?), SDLC-WA-041 (P2·B), SDLC-WA-042 (P2·B), SDLC-WA-043 (P2·B), SDLC-WA-045 (P2·B) | 0/6 |
| 46 | Activos | SDLC-ASSET-030 (P3·B), SDLC-ASSET-031 (P3·B), SDLC-ASSET-033 (P3·B), SDLC-ASSET-034 (P3·B?), SDLC-ASSET-035 (P3·B) | 0/5 |
| 47 | Inventario, compras y producción | SDLC-INV-006 (P3·B), SDLC-INV-007 (P3·B), SDLC-PUR-002 (P3·B) | 0/3 |
| 48 | UI / Design System | SDLC-UI-014 (P3·✓), SDLC-UI-015 (P3·✓), SDLC-UI-026 (P3·✓), SDLC-UI-027 (P3·✓), SDLC-UI-028 (P3·✓), SDLC-UI-030 (P3·✓) | 6/6 |

## Ronda 8 — 2 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 49 | WhatsApp | SDLC-WA-047 (P2·B), SDLC-WA-049 (P2·B), SDLC-WA-050 (P2·B?), SDLC-WA-025 (P3·B), SDLC-WA-030 (P3·B), SDLC-WA-033 (P3·B) | 0/6 |
| 50 | UI / Design System | SDLC-UI-031 (P3·✓) | 1/1 |

## Ronda 9 — 1 lotes

| Lote | Área | Ítems (en orden) | Listos |
|---|---|---|---|
| 51 | WhatsApp | SDLC-WA-040 (P3·B), SDLC-WA-046 (P3·B), SDLC-WA-051 (P3·B?) | 0/3 |

## Detalle por lote

### Lote 1 — Caja y turnos (ronda 1)

- `SDLC-ARQ-SHIFT-001` P0 T0 [✓] — Turno activo resuelto por ~12 caminos distintos: Caja y POS discrepan sobre si hay turno · depende de: —
- `SDLC-ARQ-SHIFT-004` P0 T0 [✓] — Transiciones de turno sin control de concurrencia y apertura no idempotente · depende de: SDLC-ARQ-SHIFT-001
- `SDLC-ARQ-SHIFT-002` P1 T0 [✓] — Gerente no puede consultar el turno abierto por el cajero: el contexto de Caja se filtra por usuario · depende de: SDLC-ARQ-SHIFT-001
- `SDLC-ARQ-SHIFT-003` P1 T0 [✓] — Permisos de caja definidos pero nunca verificados y entrega de turno sin implementar · depende de: SDLC-ARQ-SHIFT-001
- `SDLC-CASH-001` P1 T0 [B] — Reversa de venta registra la salida de efectivo en el turno original, aunque esté cerrado · depende de: —
- `SDLC-CASH-002` P2 T0 [B?] — Depósito de caja confirmado nunca se asienta al banco · depende de: —

### Lote 2 — Finanzas y RRHH (ronda 1)

- `SDLC-FIN-002` P0 T0 [B?] — Activo comprado en Compras queda en la cuenta de activo sin alta en el auxiliar; darlo de alta después duplica la CxP o el pago · depende de: —
- `SDLC-FIN-003` P1 T0 [B?] — Baja o venta de activo fijo no exige depreciación al día y sus casos de uso no tienen pruebas · depende de: —
- `SDLC-HR-001` P1 T0 [B?] — Nómina asienta faltas y retardos como retenciones por enterar e ignora la cuota patronal · depende de: —
- `SDLC-HR-002` P1 T0 [B] — Asiento de nómina sin reintento periódico; la UI dice 'pagada' aunque Finanzas falle · depende de: —
- `SDLC-FIN-001` P2 T0 [B] — 16 handlers de Finanzas muertos duplican las reglas del puente de Lealtad · depende de: —
- `SDLC-FIN-004` P2 T0 [B?] — La depreciación mensual solo se corre a mano: la corrida automática del legacy se perdió al borrarlo · depende de: SDLC-FIN-003

### Lote 3 — Instalador y actualizador (ronda 1)

- `SDLC-ARQ-INST-001` P0 T0 [✓] — Actualizar con el Setup manual o 'Reparar' migra la base al arrancar sin respaldo previo · depende de: —
- `SDLC-INST-001` P0 T0 [B?] — El actualizador confía en update_job.json escribible por cualquier usuario local · depende de: —
- `SDLC-ARQ-INST-002` P1 T0 [✓] — Respaldo de actualización omite configuración e identidad; desinstalar borra install_config.json · depende de: —
- `SDLC-INST-002` P1 T0 [B?] — Llavero de releases vacío: ninguna actualización puede aplicarse · depende de: SDLC-INST-001
- `SDLC-INST-003` P2 T0 [B?] — Carpeta de datos con permiso de modificación para todos los usuarios de Windows · depende de: —
- `SDLC-ARQ-INST-003` P1 T0 [✓] — Llave maestra de secretos en claro sin pywin32; DPAPI por usuario con datos de alcance máquina · depende de: SDLC-INST-003

### Lote 4 — Mercado Pago (ronda 1)

- `SDLC-PAY-002` P0 T0 [B?] — Un mismo pago de Mercado Pago puede respaldar varias ventas: referencia opcional, libre y no única · depende de: —
- `SDLC-PAY-003` P1 T0 [B] — La referencia del procesador se pierde en Caja, Finanzas y ticket: conciliación por operación imposible · depende de: SDLC-PAY-002
- `SDLC-PAY-004` P1 T0 [B?] — Cobros con procesador se asientan a la cuenta puente 1120 mientras tesorería y compras usan la 1115 · depende de: —
- `SDLC-PAY-005` P1 T0 [B] — Arqueo y cortes X/Z sólo cuentan efectivo: no desglosan tarjeta, Mercado Pago, transferencia, vales ni crédito · depende de: SDLC-PAY-003
- `SDLC-PAY-006` P1 T0 [B?] — Reembolsos y anulaciones a medio electrónico se registran como ejecutados sin que nadie los haga · depende de: SDLC-PAY-003
- `SDLC-PAY-001` P2 T2 [B?] — Diseño de la integración Mercado Pago: TRD, flujos, modelo de datos, seguridad, UX y plan de pruebas · depende de: —

### Lote 5 — Núcleo y configuración (ronda 1)

- `SDLC-CORE-012` P0 T0 [B] — Pruebas de protección del flujo recepción → producción → venta → precio antes de corregirlo · depende de: —
- `SDLC-BI-001` P1 T0 [B] — BI ignora el alcance por sucursal y usa un verificador de permisos que permite todo · depende de: —
- `SDLC-CORE-001` P1 T0 [B] — Falla en el cableado de eventos al arrancar deja la app sin integración contable, en silencio · depende de: —
- `SDLC-CORE-007` P1 T0 [B?] — El segmento de integración de CI no colecta: las pruebas de integración nunca corren · depende de: —
- `SDLC-SET-001` P1 T0 [✓] — Anclar la sucursal de la instalación no cambia la sesión en curso · depende de: —
- `SDLC-ARQ-TEST-001` P2 T1 [✓] — Arnés de aceptación multi-terminal y pruebas obsoletas que importan módulos eliminados · depende de: —

### Lote 6 — Pedidos y repartos (ronda 1)

- `SDLC-ORD-004` P0 T0 [B?] — Pedido cobrado y completado nunca descuenta inventario; su reverso suma existencia que nunca salió · depende de: —
- `SDLC-ORD-001` P1 T0 [B?] — Dinero de Pedidos: efecto de caja tragado y cobros/liquidaciones de repartidor sin asiento · depende de: —
- `SDLC-ORD-005` P1 T1 [B?] — "Todos los pedidos → Nuevo pedido" captura el producto por UUID y un precio libre que termina cobrándose · depende de: —
- `SDLC-ORD-002` P2 T1 [B] — Outbox de Pedidos, CRM, clientes, cotizaciones, tarjetas, sorteos y privacidad nunca se drenan · depende de: —
- `SDLC-ORD-003` P2 T1 [B?] — Tres pipelines de pedidos paralelos sin fuente de verdad decidida · depende de: —
- `SDLC-ORD-006` P2 T1 [B?] — Avisos al cliente de Pedidos sin reintento: si WhatsApp falla, el mensaje se pierde · depende de: —

### Lote 7 — Permisos, sesiones y seguridad (ronda 1)

- `SDLC-ARQ-PERM-001` P0 T0 [✓] — Configuración autoriza sólo en el presentador: casos de uso de escritura sin política en backend · depende de: —
- `SDLC-ARQ-SESS-003` P0 T0 [✓] — Una venta suspendida puede reanudarla otro usuario y queda atribuida al cajero original · depende de: —
- `SDLC-ARQ-PERM-003` P1 T0 [✓] — Dos resolvedores de alcance discrepan y Transferencias pasa cuando no hay sucursal · depende de: —
- `SDLC-ARQ-PERM-002` P0 T0 [✓] — Escalada por alcance: se pueden asignar roles y permisos fuera del alcance de quien los otorga · depende de: SDLC-ARQ-PERM-003
- `SDLC-ARQ-AUD-001` P1 T0 [✓] — Eventos de seguridad (login, bloqueo, denegación) nunca se persisten; una denegación por sitio cuenta como éxito · depende de: —
- `SDLC-ARQ-PERM-004` P1 T0 [✓] — Rol corporativo o de acceso total obtiene operación POS en cualquier sucursal; el nombre del rol concede privilegios · depende de: —

### Lote 8 — Terminales y sincronización (ronda 1)

- `SDLC-ARQ-TERM-002` P0 T0 [✓] — Re-anclar la sucursal de la estación no tiene autorización en backend, ni auditoría, ni candado · depende de: —
- `SDLC-SYNC-001` P0 T0 [B?] — Servidor central no aplica p006: toda petición de sync revienta en BD nueva · depende de: —
- `SDLC-SYNC-002` P0 T0 [B?] — Hecho en CONFLICTO reenviado se marca SYNCED y nunca se proyecta · depende de: SDLC-SYNC-001
- `SDLC-ARQ-TERM-001` P1 T0 [✓] — Identidad de terminal fragmentada en cinco lugares; la sesión usa el hostname · depende de: SDLC-SYNC-001
- `SDLC-SYNC-003` P1 T0 [B] — Proyección central: errores permanentes, eventos fuera de orden y última-escritura-gana en crédito/lealtad · depende de: SDLC-SYNC-001
- `SDLC-ARQ-SYNC-001` P0 T0 [✓] — Conflictos entre estaciones invisibles: sin autoridad por entidad ni detección de turno doble o sobreventa · depende de: SDLC-SYNC-002, SDLC-SYNC-003, SDLC-ARQ-TERM-001

### Lote 9 — WhatsApp (ronda 1)

- `SDLC-WA-002` P0 T1 [✓?] — Webhooks de WhatsApp y pagos aceptan peticiones sin firma si falta APP_ENV · depende de: —
- `SDLC-WA-001` P0 T1 [B?] — Webhook de MercadoPago puede confirmar el pedido equivocado y pierde aprobaciones · depende de: SDLC-WA-002
- `SDLC-WA-003` P1 T1 [B?] — Pedidos, cotizaciones y anticipos por WhatsApp no pueden crearse en producción · depende de: SDLC-WA-002
- `SDLC-WA-021` P0 T1 [B?] — El precio y la existencia guardados en la conversación se vuelven el precio de registro del pedido · depende de: SDLC-WA-003
- `SDLC-WA-004` P1 T0 [B?] — Anticipos por WhatsApp sin asiento y regla de monto que nunca casa · depende de: SDLC-WA-003
- `SDLC-WA-005` P1 T1 [B] — Microservicio WhatsApp importa el paquete core.* eliminado y la bandeja del POS nunca recibe avisos · depende de: —

### Lote 10 — UI / Design System (ronda 1)

- `SDLC-UI-001` P1 T1 [✓] — La suite tests/ui no termina (una prueba tumba el proceso) y los jobs ventas/ui/api de CI llaman un script inexistente · depende de: —
- `SDLC-UI-002` P2 T2 [✓] — 106 fallas en tests/ui: layout de módulo, iconos del sidebar de Finanzas y secciones de Productos · depende de: SDLC-UI-001
- `SDLC-UI-003` P2 T2 [✓] — Guardia de deuda visual en rojo: línea base del 2026-09-10 con 17 hallazgos nuevos y 26 resueltos sin podar · depende de: —
- `SDLC-UI-004` P2 T2 [✓?] — Tokens semánticos incompletos; modo oscuro con color de marca crudo y gráficas casi invisibles en oscuro · depende de: —
- `SDLC-UI-005` P2 T2 [✓] — Segundo sistema visual: webs de delivery/logística con paleta azul propia y PDF de BI con colores sueltos · depende de: —
- `SDLC-UI-007` P2 T2 [✓] — Densidad global por usuario de Windows: POS, Inventario, Recepción y Producción no arrancan en TOUCH · depende de: —

### Lote 11 — Inventario, compras y producción (ronda 2)

- `SDLC-INV-001` P0 T0 [B?] — Ajustes, diferencias de conteo y disposición de cuarentena sin asiento contable · depende de: —
- `SDLC-LOSS-001` P0 T0 [B?] — Mermas: ningún caso puede aprobarse, y al habilitarlo una revaluación asentaría doble · depende de: —
- `SDLC-PROC-002` P0 T0 [B] — Disponibilidad para producción suma piezas como kg y con REAL · depende de: SDLC-CORE-012
- `SDLC-TRF-001` P0 T0 [B] — Recepción de transferencias no captura peso, piezas, lote ni temperatura · depende de: SDLC-CORE-012
- `SDLC-TRF-003` P0 T0 [B?] — La transferencia recibida cae al almacén de compras y el despiece nunca la ve · depende de: SDLC-CORE-012, SDLC-TRF-001
- `SDLC-INV-003` P1 T0 [B?] — Cada flujo pone stock en una 'ubicación' distinta (sucursal, almacén o técnica) · depende de: SDLC-INV-001

### Lote 12 — Ventas y precios (ronda 2)

- `SDLC-ARQ-IDEM-001` P0 T0 [✓] — Doble clic en cobro registra dos pagos: el POS genera un operation_id nuevo por clic · depende de: —
- `SDLC-SALES-001` P0 T0 [B?] — Falla del motor de precios cobra en silencio el precio de catálogo · depende de: SDLC-CORE-012
- `SDLC-ARQ-IDEM-002` P1 T0 [✓] — Reintentos de checkout y operaciones ya aplicadas devuelven error en vez del resultado original · depende de: SDLC-ARQ-IDEM-001
- `SDLC-ARQ-IDEM-003` P1 T0 [✓] — Guardar una venta borra y reinserta sus hijos; pagos revertidos siguen CONFIRMED · depende de: —
- `SDLC-ARQ-IDEM-004` P1 T0 [✓] — Ventas tienen columna version pero el repositorio la sobrescribe sin compararla · depende de: SDLC-ARQ-IDEM-003
- `SDLC-CRED-001` P1 T0 [B?] — Exposición de crédito suma la tabla legacy cuentas_por_cobrar que ya nadie escribe · depende de: —

### Lote 13 — Clientes y fidelidad (ronda 2)

- `SDLC-CRM-001` P1 T0 [B] — Fusión de clientes escribe crédito directo, cierra crédito con saldo y deja puntos huérfanos · depende de: —
- `SDLC-CRM-002` P1 T1 [B?] — Anonimización de cliente deja nombre y teléfono en claro fuera del maestro · depende de: —
- `SDLC-CRM-003` P2 T1 [B] — Dos maestros de clientes vivos (clientes y customers) con puente bidireccional · depende de: SDLC-WA-003
- `SDLC-LOY-001` P3 T1 [B?] — Cupones nunca expiran (ExpireCouponsUseCase sólo en pruebas) · depende de: —

### Lote 14 — Permisos, sesiones y seguridad (ronda 2)

- `SDLC-ARQ-SESS-001` P1 T0 [✓] — Menú y router conservan los permisos del login; no hay prueba de dos usuarios secuenciales · depende de: —
- `SDLC-ARQ-SESS-002` P1 T0 [✓] — Sin bloqueo de pantalla ni expiración: la sesión de 8 h nunca se aplica · depende de: —
- `SDLC-SEC-001` P1 T0 [B] — Contraseñas de usuario se hashean en la UI y saltan la política de contraseñas · depende de: —
- `SDLC-SEC-002` P1 T0 [B] — Autorización de dos personas confía en IDs enviados por la UI; usuarios inactivos siguen autorizando · depende de: —
- `SDLC-ARQ-AUD-002` P2 T0 [✓] — Auditoría fragmentada sin esquema común; actor por defecto 'Sistema' y sin terminal ni resultado · depende de: SDLC-ARQ-TERM-001
- `SDLC-ARQ-AUD-003` P2 T0 [✓] — Bloqueo de cuenta sólo por usuario; sin límite por terminal o IP en login · depende de: SDLC-ARQ-AUD-001

### Lote 15 — Terminales y sincronización (ronda 2)

- `SDLC-ARQ-HYB-001` P1 T0 [✓] — No existe servicio local de sucursal: caja, turno e inventario no pueden coordinarse entre terminales · depende de: SDLC-ARQ-TERM-001, SDLC-ARQ-SHIFT-001, SDLC-ARQ-SHIFT-004
- `SDLC-ARQ-HYB-002` P1 T0 [✓] — Operación degradada sin política: nada se bloquea sin coordinación y el estado offline nunca se fija · depende de: SDLC-ARQ-HYB-001
- `SDLC-ARQ-SYNC-002` P1 T0 [✓] — Conflictos centrales nunca se resuelven y hay tres modelos de conflicto paralelos · depende de: SDLC-ARQ-SYNC-001
- `SDLC-ARQ-TERM-003` P1 T0 [✓] — El login no verifica el estado del dispositivo: una terminal bloqueada o retirada sigue vendiendo · depende de: SDLC-ARQ-TERM-001
- `SDLC-ARQ-TERM-004` P1 T0 [✓] — Registro central de dispositivos sin pruebas, duplicado y con actor admin no firmado · depende de: SDLC-SYNC-001, SDLC-ARQ-TERM-001
- `SDLC-ARQ-TERM-005` P1 T0 [✓] — El escritorio nunca se enrola ni consulta su estado en el central; la instalación no registra la terminal · depende de: SDLC-ARQ-TERM-004

### Lote 16 — WhatsApp (ronda 2)

- `SDLC-WA-006` P1 T1 [B] — Trabajadores del microservicio WhatsApp nunca corren y el webhook responde 200 aunque falle · depende de: —
- `SDLC-WA-008` P1 T1 [B?] — Secretos del canal fuera del SecretStore: token de Mercado Pago y llave del ERP solo de entorno, respaldo en claro en SQLite · depende de: —
- `SDLC-WA-012` P1 T1 [B] — Cliente de WhatsApp resuelto por los últimos 10 dígitos con LIMIT 1: pedidos y crédito pueden caer en otro cliente · depende de: —
- `SDLC-WA-013` P1 T1 [B?] — Pedidos por WhatsApp caen en la sucursal 1 cuando falta sucursal y todo sale por un solo número · depende de: —
- `SDLC-WA-020` P1 T1 [B] — Selección de producto por WhatsApp falla con IDs UUIDv7: int() descarta el producto en silencio · depende de: —
- `SDLC-WA-028` P1 T1 [B] — Rechazar una cotización por WhatsApp escribe la tabla legacy de cotizaciones incluso en producción · depende de: SDLC-WA-003

### Lote 17 — Activos (ronda 2)

- `SDLC-ASSET-001` P2 T2 [✓] — Módulo Activos visible en el menú sin persistencia: 31 de 36 rutas en construcción · depende de: —
- `SDLC-ASSET-002` P2 T2 [B] — Las guardias de arquitectura de Activos pasan en vacío y no vigilan el andamiaje ni el esquema legacy · depende de: —
- `SDLC-ASSET-004` P2 T0 [B?] — Seis tablas legacy de activos se siguen creando sin lector ni escritor, con dinero en REAL · depende de: —
- `SDLC-ASSET-005` P2 T1 [B] — El menú interno de Activos ignora el permiso de cada ruta · depende de: —
- `SDLC-ASSET-006` P2 T0 [B?] — Los 83 permisos `ACTIVOS.*` no están sembrados en ningún rol y no existen los roles de §82: solo el dueño entra · depende de: —
- `SDLC-ASSET-007` P2 T1 [B] — Activos no tiene resolvedor de alcance: sin sucursal en la sesión, el tablero suma toda la empresa · depende de: SDLC-ARQ-PERM-003

### Lote 18 — Núcleo y configuración (ronda 2)

- `SDLC-BI-002` P2 T2 [B] — BI: ajustes y estado de alertas sólo en memoria; errores SQL se muestran como $0 · depende de: SDLC-BI-001
- `SDLC-BI-003` P2 T2 [B] — Dos motores de pronóstico dan números distintos para lo mismo · depende de: —
- `SDLC-CORE-002` P2 T0 [B?] — operation_id compuesto por concatenación de cadenas en rutas de dinero e inventario · depende de: —
- `SDLC-CORE-003` P2 T1 [B] — La UI crea esquema y repositorios SQLite (22 archivos de frontend importan infraestructura) · depende de: —
- `SDLC-CORE-008` P2 T0 [B] — Guardias de arquitectura en rojo por DDL fuera de migraciones, conexiones crudas y ratchet UUID · depende de: —
- `SDLC-CORE-010` P2 T1 [B] — 4 fallas en tests/unit: permiso de aprobar flags, diálogo de cobro y barra lateral de Transferencias · depende de: —

### Lote 19 — Pedidos y repartos (ronda 2)

- `SDLC-ORD-007` P2 T1 [B?] — PWA de repartidor: sin ubicación en ruta y evidencia de entrega siempre vacía · depende de: —
- `SDLC-ORD-008` P2 T2 [B] — Clic en un aviso de la campana no abre el pedido: solo lo marca como leído · depende de: —
- `SDLC-ORD-009` P2 T1 [B?] — Pedidos/Delivery nunca se validó de punta a punta en entorno real (PWA en dispositivo, PyQt5 real, ERP+WhatsApp) · depende de: SDLC-ORD-004, SDLC-WA-003, SDLC-WA-005
- `SDLC-ORD-010` P3 T1 [B] — Restos del legacy de Delivery: 31 archivos de prueba importan paquetes borrados y no se pueden recolectar · depende de: —
- `SDLC-ORD-011` P3 T1 [B?] — Política de avisos de Pedidos fija en código, sin ajuste por sucursal · depende de: SDLC-ORD-006

### Lote 20 — Terminales y sincronización (ronda 3)

- `SDLC-SYNC-004` P1 T0 [B] — Huecos en la secuencia de estación bloquean la recuperación de dispositivo · depende de: SDLC-SYNC-001
- `SDLC-SYNC-005` P1 T0 [B?] — Ninguna estación replica al central: transporte nunca configurado y sin planificador · depende de: SDLC-SYNC-002, SDLC-SYNC-003, SDLC-SYNC-004
- `SDLC-ARQ-SYNC-003` P1 T0 [✓] — No existe sincronización de bajada (central → estación): maestros, precios, permisos y revocaciones · depende de: SDLC-SYNC-005, SDLC-ARQ-TERM-004
- `SDLC-ARQ-OFF-001` P1 T0 [✓] — No hay modelo de autorización offline: login siempre local, sin vigencia ni autoridad central · depende de: SDLC-ARQ-SYNC-003, SDLC-ARQ-TERM-001
- `SDLC-ARQ-HYB-003` P2 T0 [✓] — Central sin artefactos de despliegue, respaldo de PostgreSQL ni salud real · depende de: SDLC-SYNC-001
- `SDLC-ARQ-HYB-004` P2 T2 [✓] — Nada impide que el escritorio hable directo con PostgreSQL · depende de: —

### Lote 21 — WhatsApp (ronda 3)

- `SDLC-WA-029` P1 T1 [B?] — Aprobación del ajuste de peso por el cliente escribe tablas legacy de delivery y no usa el caso de uso de Orders · depende de: SDLC-WA-005, SDLC-WA-003
- `SDLC-WA-034` P1 T1 [B?] — Cualquier número desconocido se registra como cliente al primer mensaje, sin aviso de privacidad ni consentimiento · depende de: SDLC-WA-012
- `SDLC-WA-035` P1 T1 [B?] — No hay forma de darse de baja por WhatsApp y el control de consentimiento falla abierto · depende de: SDLC-WA-034
- `SDLC-WA-038` P1 T1 [B] — Avisos de Pedidos por WhatsApp ignoran la credencial guardada en Integraciones y solo funcionan con variables de entorno · depende de: —
- `SDLC-WA-007` P2 T1 [B] — Microservicio WhatsApp viola REGLA CERO y escribe configuración/migraciones del ERP · depende de: SDLC-WA-003
- `SDLC-WA-016` P2 T1 [B] — main.py del microservicio arma todo a mano: abre la base del ERP, migra, registra globals y manipula sys.path en ejecución · depende de: SDLC-WA-007

### Lote 22 — Activos (ronda 3)

- `SDLC-ASSET-008` P2 T1 [B?] — Dominio de Activos: segregación de funciones incompleta y transiciones que saltan el flujo · depende de: —
- `SDLC-ASSET-009` P3 T1 [B?] — Validaciones de dominio de Activos incompletas o inalcanzables (ubicación raíz, QR, escaneo, seguros, inspecciones, documentos) · depende de: —
- `SDLC-ASSET-010` P2 T0 [B?] — Activos sin persistencia: esquema, repositorios y unidad de trabajo para activo, categoría, ubicación y etiqueta, con folio configurable · depende de: SDLC-ASSET-002, SDLC-ASSET-004, SDLC-ASSET-008, SDLC-ASSET-009
- `SDLC-ASSET-011` P2 T1 [B] — Casos de uso de registro de activos con autorización en backend, auditoría y outbox de eventos · depende de: SDLC-ASSET-010, SDLC-ASSET-006, SDLC-ASSET-007
- `SDLC-ASSET-012` P2 T1 [B] — Activos abre vacío: el shell lo compone con `query_services={}` y faltan 11 de 17 servicios de consulta · depende de: SDLC-ASSET-010, SDLC-ASSET-007, SDLC-ASSET-001
- `SDLC-ASSET-013` P2 T1 [B] — No hay forma de dar de alta ni editar un activo: falta el formulario por secciones con MoneyInput · depende de: SDLC-ASSET-011, SDLC-ASSET-012

### Lote 23 — Mercado Pago (ronda 3)

- `SDLC-PAY-007` P2 T0 [B] — No existe contexto de pagos: sin intención de pago, estados, puerto de proveedor ni capa anticorrupción · depende de: SDLC-PAY-001, SDLC-ARQ-IDEM-001
- `SDLC-PAY-008` P2 T0 [B?] — La venta se completa sin pago verificado: estado «esperando pago» muerto y puntos acumulados sobre pagos no confirmados · depende de: SDLC-PAY-007
- `SDLC-PAY-010` P2 T0 [B] — No hay webhook central ni inbox durable: notificaciones de Mercado Pago no verificadas ni recuperables · depende de: SDLC-PAY-007, SDLC-PAY-001, SDLC-WA-002
- `SDLC-PAY-016` P2 T0 [B] — Pagos mixtos con porción electrónica: sin compensación si falla y montos capturados vía float · depende de: SDLC-PAY-008
- `SDLC-PAY-017` P2 T0 [B?] — Sin política offline para cobros electrónicos ni coordinación entre equipos · depende de: SDLC-PAY-008, SDLC-ARQ-HYB-002, SDLC-ARQ-HYB-001
- `SDLC-PAY-018` P2 T0 [B?] — Finanzas no registra comisión del procesador, IVA de la comisión ni depósito neto; un depósito puede duplicar el ingreso · depende de: SDLC-PAY-004

### Lote 24 — Permisos, sesiones y seguridad (ronda 3)

- `SDLC-ARQ-PERM-005` P2 T0 [✓] — Permisos sin dimensión de recurso ni condiciones; el ámbito va codificado en el nombre · depende de: SDLC-ARQ-PERM-001
- `SDLC-ARQ-SCOPE-001` P2 T0 [✓] — Almacenes y plantas acoplados a sucursal; Logística necesita una sucursal anclada · depende de: SDLC-ARQ-PERM-003
- `SDLC-SEC-003` P2 T0 [B] — Alcance de seguridad abierto: central acepta cualquier actor y algunos checkers omiten sucursal · depende de: —
- `SDLC-SEC-004` P2 T0 [B] — Código de autenticación duplicado y muerto (security/auth.py, listas de admin divergentes) · depende de: —
- `SDLC-SEC-006` P2 T0 [B] — Filtro de redacción de secretos no instalado en el logging y sin patrón para tokens Bearer · depende de: —
- `SDLC-ARQ-PERM-006` P3 T2 [✓] — Falta la matriz de permisos de los perfiles de referencia · depende de: SDLC-ARQ-PERM-004

### Lote 25 — Ventas y precios (ronda 4)

- `SDLC-PRICE-001` P1 T1 [B?] — Cambiar un solo precio de una lista aprobada obliga a duplicar toda la lista · depende de: SDLC-SALES-001
- `SDLC-PRICE-002` P1 T1 [B?] — Lista de precios por cliente: sin caso de uso ni UI, varias listas posibles y elección arbitraria · depende de: SDLC-PRICE-001, SDLC-ARQ-PERM-005
- `SDLC-SALES-002` P1 T0 [B?] — Totales de venta nunca se redondean a centavos · depende de: —
- `SDLC-SALES-003` P1 T0 [B] — Outbox de ventas sin contador de intentos ni dead-letter: un evento envenenado se reintenta para siempre · depende de: —
- `SDLC-ARQ-IDEM-005` P2 T0 [✓] — Sin vocabulario común de estados de operación (borrador/pendiente/confirmada/rechazada/compensada) · depende de: SDLC-ARQ-IDEM-002
- `SDLC-SALES-004` P2 T0 [B?] — Expiración de ventas suspendidas sin llamador e insegura si se cablea · depende de: —

### Lote 26 — WhatsApp (ronda 4)

- `SDLC-WA-048` P2 T1 [B] — Las pruebas del canal no corren en CI: 15 fallan, 1 archivo no se recolecta y las legacy importan paquetes borrados · depende de: —
- `SDLC-WA-019` P1 T1 [B?] — Corte del webhook vivo al pipeline canónico: hoy procesa en línea con el router legacy y el stack nuevo no recibe tráfico · depende de: SDLC-WA-002, SDLC-WA-006, SDLC-WA-016, SDLC-WA-048
- `SDLC-WA-036` P1 T1 [B?] — El bot promete "Te comunico con un asesor" y nunca escala; el personal contesta desde su teléfono personal · depende de: SDLC-WA-019
- `SDLC-WA-009` P2 T1 [B?] — Llamadas WhatsApp→ERP con X-API-Key estática, sin HMAC ni identidad de servicio · depende de: SDLC-WA-003, SDLC-WA-008
- `SDLC-WA-010` P2 T1 [B] — Webhook de Meta sin ventana de tiempo, sin anti-replay persistido ni registro de intentos inválidos · depende de: SDLC-WA-002
- `SDLC-WA-011` P2 T1 [B?] — Mensajes y teléfonos en claro sin política de retención; bitácora de IA guarda texto y hash de teléfono reversible · depende de: —

### Lote 27 — Activos (ronda 4)

- `SDLC-ASSET-014` P2 T1 [B] — Custodia y préstamos de activos sin persistencia ni casos de uso; Activos no consulta empleados de RRHH · depende de: SDLC-ASSET-011
- `SDLC-ASSET-015` P2 T1 [B] — Transferencias de activos entre sucursales sin persistencia ni flujo · depende de: SDLC-ASSET-011, SDLC-ASSET-008, SDLC-ASSET-007
- `SDLC-ASSET-016` P2 T1 [B?] — Mantenimiento: planes y órdenes de trabajo sin persistencia, casos de uso ni folio; faltan ejecución, tareas y recursos · depende de: SDLC-ASSET-011, SDLC-ASSET-008
- `SDLC-ASSET-017` P2 T1 [B] — Ninguna orden preventiva se genera sola: sin ciclo por vencimiento, medidores sin persistencia ni avisos · depende de: SDLC-ASSET-016
- `SDLC-ASSET-018` P2 T1 [B] — Tablero de órdenes de trabajo y agenda son de solo lectura; no hay formulario de OT · depende de: SDLC-ASSET-016
- `SDLC-ASSET-019` P2 T0 [B?] — El costo real de mantenimiento nunca llega a Finanzas ni a Cuentas por Pagar · depende de: SDLC-ASSET-016

### Lote 28 — Mercado Pago (ronda 4)

- `SDLC-PAY-019` P2 T0 [B?] — Sin conciliación de liquidaciones de Mercado Pago: estados CAPTURED→SETTLED→RECONCILED y excepciones · depende de: SDLC-PAY-018, SDLC-PAY-003
- `SDLC-PAY-022` P2 T0 [B?] — Access Token en cada caja y en el microservicio, sin ambiente ni rotación; «Configurado» no significa conectado · depende de: SDLC-PAY-001
- `SDLC-PAY-009` P2 T0 [B?] — No hay adaptador de Mercado Pago Orders API; el SDK empaquetado no se usa · depende de: SDLC-PAY-007, SDLC-PAY-022
- `SDLC-PAY-011` P2 T0 [B] — Sin conciliación por consulta: un pago con webhook perdido, timeout o reinicio queda sin resolver · depende de: SDLC-PAY-007, SDLC-PAY-009
- `SDLC-PAY-012` P2 T0 [B?] — Terminales Point Smart: sin descubrimiento, vinculación a estación, modo PDV ni exclusión entre estaciones · depende de: SDLC-PAY-009, SDLC-ARQ-TERM-001, SDLC-ARQ-HYB-001
- `SDLC-PAY-013` P2 T0 [B] — Cobro con Point desde el diálogo estándar: el diálogo es modal y síncrono, sin estados ni recuperación · depende de: SDLC-PAY-008, SDLC-PAY-011, SDLC-PAY-012

### Lote 29 — Núcleo y configuración (ronda 4)

- `SDLC-CORE-011` P2 T1 [B] — 74 fallas y 32 errores en tests/integration, en su mayoría fixtures desactualizados · depende de: SDLC-CORE-007
- `SDLC-SET-002` P2 T1 [B?] — Tablas de configuración legacy (configuraciones, feature_flags, hardware_config) siguen vivas · depende de: SDLC-WA-007
- `SDLC-SET-003` P2 T1 [B?] — Secciones de Configuración que guardan datos que nada lee · depende de: —
- `SDLC-CORE-004` P3 T0 [B] — Archivos de migración SQLite sin registrar y números duplicados · depende de: —
- `SDLC-CORE-005` P3 T1 [B] — Código muerto y cascarones de casos de uso (ventas, delivery, RRHH, BI) · depende de: —
- `SDLC-CORE-006` P3 T1 [B] — Float residual en dinero y cantidades (lealtad, recibos, analítica, proveedores, depreciación) · depende de: —

### Lote 30 — Terminales y sincronización (ronda 4)

- `SDLC-ARQ-OFF-002` P2 T0 [✓] — Tokens móviles con fotografía de permisos de 15 min sin verificación de revocación · depende de: —
- `SDLC-ARQ-SYNC-004` P2 T0 [✓] — El central no aplica versión mínima ni compatibilidad de protocolo de las estaciones · depende de: SDLC-ARQ-TERM-001
- `SDLC-ARQ-TERM-006` P2 T0 [✓] — Perfiles de despliegue incompletos y API móvil sin compuerta de módulo instalado · depende de: SDLC-ARQ-TERM-001

### Lote 31 — UI / Design System (ronda 4)

- `SDLC-UI-010` P2 T2 [✓] — Overflow: 101 pantallas sin contrato explícito, scroll anidado y encabezado/acciones fijos fuera del viewport · depende de: SDLC-UI-003
- `SDLC-UI-011` P2 T2 [✓] — Layouts canónicos que solo existen de nombre (FormPage, MasterDetailPage, POSPage, Toast) y WizardPage duplicado · depende de: SDLC-UI-007, SDLC-UI-010
- `SDLC-UI-012` P2 T2 [✓] — AppSidebar: sin Inicio ni Reportes, orden distinto al estándar, encabezado crudo 'operacion' y búsqueda que coincide con todo · depende de: —
- `SDLC-UI-013` P2 T1 [✓] — El indicador de sesión siempre dice 'Conectado': offline_status nunca cambia y 'próxima a vencer' no tiene fuente · depende de: SDLC-SYNC-005, SDLC-ARQ-HYB-002, SDLC-ARQ-SESS-002
- `SDLC-UI-016` P2 T0 [✓] — No existe 'Cambiar sucursal': ni en Archivo ni en el menú de usuario, y el contexto no puede cambiar en sesión · depende de: SDLC-SET-001, SDLC-ARQ-TERM-002, SDLC-ARQ-PERM-003
- `SDLC-UI-017` P2 T2 [✓?] — ModuleSidebar: deep-links que dejan oculta la página en grupos colapsados; badge y permiso por grupo sin uso; módulos grandes planos · depende de: —

### Lote 32 — Permisos, sesiones y seguridad (ronda 4)

- `SDLC-SEC-005` P3 T0 [B] — Endurecimiento menor: rate limit por cabecera no autenticada, nonce por proceso, respaldo de secretos en claro · depende de: —

### Lote 33 — Inventario, compras y producción (ronda 5)

- `SDLC-PROC-001` P0 T0 [B?] — Lo recibido no llega al despiece: falta orquestación recepción → transformación · depende de: SDLC-TRF-001, SDLC-TRF-003, SDLC-PROC-002, SDLC-INV-003, SDLC-CORE-002, SDLC-ARQ-IDEM-005
- `SDLC-INV-002` P1 T0 [B] — Captura de peso suma el peso completo al stock y el signo del peso puede invertirse · depende de: —
- `SDLC-LOG-002` P1 T1 [B?] — No hay bandeja única de recepciones: compras, llegadas de embarque y transferencias se reciben en tres lugares · depende de: SDLC-TRF-001, SDLC-TRF-003
- `SDLC-PROC-004` P1 T0 [B?] — Salidas de despiece estimadas sin regla de venta, pesaje posterior ni conciliación · depende de: SDLC-PROC-001
- `SDLC-PUR-001` P1 T0 [B] — Recepción de compra rechazada por Inventario se descarta, pero la CxP sí se crea · depende de: —
- `SDLC-TRF-002` P1 T0 [B] — Ciclo de transferencia termina en la recepción: faltantes desaparecen sin merma ni asiento · depende de: SDLC-TRF-001, SDLC-LOSS-001

### Lote 34 — Activos (ronda 5)

- `SDLC-ASSET-020` P2 T0 [B?] — Las refacciones de mantenimiento no tienen solicitud a Inventario (reserva y consumo) · depende de: SDLC-ASSET-016
- `SDLC-ASSET-021` P2 T1 [B] — Inspecciones y checklists configurables sin persistencia, casos de uso ni pantalla · depende de: SDLC-ASSET-016, SDLC-ASSET-009
- `SDLC-ASSET-022` P2 T1 [B] — Documentos, fotos, garantías y seguros de activos sin almacenamiento ni avisos de vencimiento · depende de: SDLC-ASSET-011, SDLC-ASSET-009
- `SDLC-ASSET-024` P2 T0 [B?] — Dos identidades de activo: el `Asset` de Activos y el `FixedAsset` de Finanzas no se enlazan, y hay dos pantallas de activos · depende de: SDLC-FIN-002, SDLC-ASSET-010
- `SDLC-ASSET-023` P2 T0 [B?] — Las mejoras y propuestas de capitalización no tienen camino a Finanzas: Finanzas solo capitaliza activos nuevos · depende de: SDLC-ASSET-011, SDLC-ASSET-008, SDLC-ASSET-024
- `SDLC-ASSET-026` P2 T0 [B] — Dos bajas paralelas: Finanzas da de baja sin el flujo de solicitud y aprobación de Activos · depende de: SDLC-ASSET-024, SDLC-FIN-003, SDLC-ASSET-008

### Lote 35 — Mercado Pago (ronda 5)

- `SDLC-PAY-014` P2 T0 [B] — Checkout Pro y enlaces de pago: no se generan desde el ERP; el microservicio tiene dos versiones sin idempotencia · depende de: SDLC-PAY-009
- `SDLC-PAY-015` P2 T0 [B] — QR dinámico: no existe en el diálogo de cobro ni en el monitor del cliente · depende de: SDLC-PAY-014, SDLC-PAY-013
- `SDLC-PAY-020` P2 T0 [B] — Reembolso vía API de Mercado Pago con estados, parciales y eventos tardíos · depende de: SDLC-PAY-006, SDLC-PAY-009, SDLC-PAY-010
- `SDLC-PAY-021` P2 T0 [B?] — Contracargos no modelados: sin proceso financiero ni operativo de investigación · depende de: SDLC-PAY-019, SDLC-PAY-020
- `SDLC-PAY-023` P2 T0 [B] — Permisos de pagos con proveedor incompletos: sin cobrar, cancelar, reembolsar, asignar terminal ni conciliar MP en backend · depende de: SDLC-PAY-007
- `SDLC-PAY-024` P2 T0 [B] — Operaciones de pago sin auditoría: el registro de auditoría de Ventas existe y nadie lo llama · depende de: SDLC-ARQ-AUD-002, SDLC-PAY-007

### Lote 36 — UI / Design System (ronda 5)

- `SDLC-UI-018` P2 T2 [✓] — CRM tiene pestañas dentro de pestañas (4 niveles) y un componente de pestañas propio (PillTabBar) · depende de: —
- `SDLC-UI-019` P2 T2 [✓] — StandardTable sin acciones por fila ni ordenamiento; anchos guardados, filtro y carga casi sin uso · depende de: —
- `SDLC-UI-020` P2 T1 [✓] — MoneyInput guarda montos en float (QDoubleSpinBox) · depende de: —
- `SDLC-UI-021` P2 T1 [✓] — Teclado virtual: el modo por terminal nunca se aplica y la protección contra escáner/báscula está muerta · depende de: —
- `SDLC-UI-022` P2 T2 [✓] — La matriz de 5 resoluciones solo cubre 4 módulos y con páginas de relleno · depende de: SDLC-UI-001, SDLC-UI-002
- `SDLC-UI-023` P2 T2 [✓] — Productos: 57 QPushButton, 18 QLineEdit, 34 QComboBox y 2 QTreeWidget fuera del estándar · depende de: SDLC-UI-011, SDLC-UI-019

### Lote 37 — Ventas y precios (ronda 5)

- `SDLC-SALES-005` P2 T1 [B] — Modelo de ventas legacy (ventas/detalles_venta) sigue vivo como fuente de lectura · depende de: —
- `SDLC-SALES-006` P2 T1 [B] — 'Guardar PDF' del ticket ignora el diseñador de Configuración · depende de: —
- `SDLC-SALES-007` P3 T1 [B] — POS reporta cualquier OperationalError como 'no hay turno abierto'; folio de CxC = id de venta · depende de: —

### Lote 38 — WhatsApp (ronda 5)

- `SDLC-WA-014` P2 T1 [B] — Tablas del canal duplicadas y huérfanas: tres fuentes de números, dos de conversaciones, colas que nadie drena · depende de: SDLC-WA-012, SDLC-WA-013
- `SDLC-WA-015` P2 T1 [B] — WhatsApp emite SALE_CREATED y PAYMENT_RECEIVED como si fuera dueño, triplica eventos y ninguno de los canónicos se emite · depende de: SDLC-WA-014
- `SDLC-WA-017` P2 T1 [B] — /health sin autenticación hace un ping síncrono a Meta en cada llamada y /diagnostics cuenta tablas que el camino vivo no escribe · depende de: SDLC-WA-016
- `SDLC-WA-018` P2 T1 [B] — Dos caminos de envío a Meta: flujos y router llaman al sender legacy sin pasar por el gateway ni persistir antes de enviar · depende de: SDLC-WA-016
- `SDLC-WA-022` P2 T1 [B] — Conversación viva como cadena de if/elif sobre estados legacy; el timeout borra el carrito sin avisar · depende de: SDLC-WA-019
- `SDLC-WA-023` P2 T1 [B?] — Resolución de intención viva fuera de orden: la IA corre antes que las capas deterministas y su salida no se valida · depende de: SDLC-WA-022, SDLC-WA-007

### Lote 39 — Núcleo y configuración (ronda 5)

- `SDLC-CORE-009` P3 T1 [B?] — Resto de guardias de arquitectura en rojo (UI, deuda visual, herramientas de refactor) · depende de: —

### Lote 40 — Activos (ronda 6)

- `SDLC-ASSET-027` P2 T1 [B] — Etiquetas, QR y reporte PDF de activos se perdieron con el legacy · depende de: SDLC-ASSET-010, SDLC-ASSET-009
- `SDLC-ASSET-025` P2 T1 [B] — Inventario físico de activos sin persistencia, escaneo ni resolución de diferencias · depende de: SDLC-ASSET-027, SDLC-ASSET-009, SDLC-ASSET-014
- `SDLC-ASSET-028` P2 T1 [B?] — Compras no solicita el registro de activos de capital al recibir · depende de: SDLC-FIN-002, SDLC-ASSET-011
- `SDLC-ASSET-029` P2 T0 [B] — No existe autorización en caliente en Activos · depende de: SDLC-ASSET-011
- `SDLC-ASSET-032` P2 T0 [B] — Activos fuera de la replicación offline; los conflictos existen solo como vocabulario · depende de: SDLC-ASSET-011, SDLC-SYNC-005, SDLC-ARQ-SYNC-001
- `SDLC-ASSET-003` P3 T1 [B?] — Restos del legacy de Activos: pruebas y script que importan `core/` borrado y andamiaje muerto con float · depende de: SDLC-ASSET-002

### Lote 41 — Inventario, compras y producción (ronda 6)

- `SDLC-INV-004` P2 T0 [B] — Cableado muerto de inventario (cutover canónico, puentes huérfanos, wire_logistics) · depende de: —
- `SDLC-INV-005` P2 T0 [B] — Almacén de stock legacy (inventory_stock) se sigue creando y BI lo lee · depende de: —
- `SDLC-INV-008` P2 T1 [B?] — Destinatarios de alertas de stock por texto de rol legacy y teléfonos globales, fuera del RBAC · depende de: SDLC-ARQ-PERM-003, SDLC-ARQ-PERM-005
- `SDLC-LOG-001` P2 T1 [B] — Logística ejecuta SQL contra tablas de Compras y Productos · depende de: —
- `SDLC-PROC-003` P2 T1 [B] — Asiento de costo de producción fallido espera a la siguiente orden · depende de: —
- `SDLC-PROD-001` P2 T2 [B?] — Ficha de producto sin flujo guiado ni camino a capturar su precio · depende de: SDLC-PRICE-001

### Lote 42 — Mercado Pago (ronda 6)

- `SDLC-PAY-025` P2 T0 [B] — Pago remoto por WhatsApp/CRM: enlace inalcanzable, preferencias repetidas y estado financiero en el microservicio · depende de: SDLC-PAY-014, SDLC-WA-003, SDLC-ORD-003
- `SDLC-PAY-026` P2 T2 [B] — BI atribuye toda venta mixta a su primer pago, mezcla códigos de método y no tiene dimensiones de procesador · depende de: SDLC-PAY-003
- `SDLC-PAY-027` P2 T0 [B] — Sin suite de fallos y concurrencia para pagos (20 escenarios del documento) · depende de: SDLC-PAY-011, SDLC-PAY-013, SDLC-PAY-016
- `SDLC-PAY-028` P3 T1 [B?] — Pruebas y docstrings de Mercado Pago apuntan a código legacy eliminado · depende de: —
- `SDLC-PAY-029` P3 T2 [B] — Runbook operativo de Mercado Pago en español · depende de: SDLC-PAY-013, SDLC-PAY-014, SDLC-PAY-019, SDLC-PAY-022

### Lote 43 — UI / Design System (ronda 6)

- `SDLC-UI-024` P2 T2 [✓] — RRHH: 32 QLineEdit y 8 QDateEdit nativos · depende de: SDLC-UI-011
- `SDLC-UI-025` P2 T1 [✓] — Finanzas y Cárnico: 4 QTableWidget (asiento contable editable incluido) e inputs nativos · depende de: SDLC-UI-019, SDLC-UI-020
- `SDLC-UI-029` P2 T2 [✓] — Huecos de las guardias: personalización por instancia, QTreeWidget/QTableView, Qt.<color>, glifos y ventanas QWidget · depende de: SDLC-UI-003
- `SDLC-UI-006` P3 T2 [✓] — Quedan glifos Unicode como icono (⌨ ⌫ →) y la guardia no cubre ese rango · depende de: SDLC-UI-003
- `SDLC-UI-008` P3 T2 [✓] — StandardWindow no gestiona tema ni estado y la pantalla del cliente lo evita sin que la guardia lo note · depende de: —
- `SDLC-UI-009` P3 T2 [B] — StandardDialog: sin icono en encabezado, orden de botones de la plataforma y Escape implícito · depende de: —

### Lote 44 — WhatsApp (ronda 6)

- `SDLC-WA-024` P2 T1 [B] — Plantillas del proveedor en un diccionario fijo: sin versión, categoría, estado ni esquema de parámetros · depende de: SDLC-WA-014
- `SDLC-WA-026` P2 T1 [B?] — Horarios del canal sin zona horaria, abiertos ante error y con aviso de cerrado que no detiene el pedido · depende de: SDLC-WA-013
- `SDLC-WA-027` P2 T1 [B] — Audio, video, sticker y contactos se descartan sin respuesta; imagen y documento sin pipeline de media seguro · depende de: SDLC-WA-019
- `SDLC-WA-031` P2 T0 [B] — El canal calcula el crédito disponible sobre clientes legacy y con eso decide si pide anticipo · depende de: SDLC-WA-003
- `SDLC-WA-032` P2 T1 [B] — Delivery por WhatsApp: dirección solo como texto libre, ubicación compartida ignorada y sincronización de estado siempre falla · depende de: SDLC-WA-003
- `SDLC-WA-037` P2 T1 [B] — Notificaciones del ERP al cliente por /api/notify v1 sin outbox; la v2 no tiene llamadores y nadie decide el canal · depende de: SDLC-WA-018

### Lote 45 — WhatsApp (ronda 7)

- `SDLC-WA-039` P2 T1 [B] — Reintentos sin clasificación de errores, dead letter sin escritor y límite de mensajes solo por teléfono en memoria · depende de: SDLC-WA-019
- `SDLC-WA-044` P2 T1 [B?] — Sin vocabulario de permisos del canal WhatsApp ni segregación de funciones · depende de: —
- `SDLC-WA-041` P2 T1 [B] — No existe módulo WhatsApp en el escritorio: nadie puede ver conversaciones ni su estado dentro del ERP · depende de: SDLC-WA-019, SDLC-WA-044
- `SDLC-WA-042` P2 T1 [B] — Sin composer ni respuesta humana desde el ERP, y el sistema de diseño no tiene componentes de conversación · depende de: SDLC-WA-041, SDLC-WA-036
- `SDLC-WA-043` P2 T1 [B] — Configuración → Integraciones no permite dar de alta cuentas, números por sucursal, plantillas ni enrutamiento de WhatsApp · depende de: SDLC-WA-013, SDLC-WA-044
- `SDLC-WA-045` P2 T1 [B] — Sin auditoría de acciones del canal: envío, handoff, bloqueo, opt-out, plantillas y configuración no dejan rastro · depende de: SDLC-WA-044

### Lote 46 — Activos (ronda 7)

- `SDLC-ASSET-030` P3 T2 [B] — Indicadores de Activos incompletos: 5 conteos, sin gráficas, MTBF/MTTR, salud ni candidatos a reemplazo, y nada expuesto a BI · depende de: SDLC-ASSET-016, SDLC-ASSET-024
- `SDLC-ASSET-031` P3 T1 [B] — Configuración del módulo de Activos ausente (numeración, categorías, SLA, estados) y sin vínculo a dispositivos · depende de: SDLC-ASSET-010
- `SDLC-ASSET-033` P3 T2 [B] — Defectos de las páginas actuales de Activos: enums crudos, error tragado, accesibilidad y docstrings falsos · depende de: —
- `SDLC-ASSET-034` P3 T1 [B?] — Procesamiento Cárnico lleva su propio mantenimiento de equipos, paralelo al de Activos · depende de: SDLC-ASSET-016
- `SDLC-ASSET-035` P3 T2 [B] — Inventarios de documentación de Activos (§4) faltantes o desactualizados · depende de: —

### Lote 47 — Inventario, compras y producción (ronda 7)

- `SDLC-INV-006` P3 T1 [B] — Folios de ajuste, conteo y peso se repiten (new_uuid()[:8]) · depende de: —
- `SDLC-INV-007` P3 T1 [B] — Báscula simulada (StubScaleGateway) cableada en la composición de Inventario; doble mecanismo de retención de calidad · depende de: —
- `SDLC-PUR-002` P3 T1 [B] — Falla al leer días de crédito vuelve la factura de proveedor exigible hoy · depende de: —

### Lote 48 — UI / Design System (ronda 7)

- `SDLC-UI-014` P3 T2 [✓] — Bloque de usuario sin iniciales ni rol, Acerca de sin logo y Configuración deshabilitada sin explicación · depende de: —
- `SDLC-UI-015` P3 T2 [✓] — Contador de notificaciones calculado sobre 50 filas y avisos que no llevan a su origen · depende de: —
- `SDLC-UI-026` P3 T2 [✓] — Inventario y resto de módulos: QComboBox nativos y componentes locales · depende de: SDLC-UI-011
- `SDLC-UI-027` P3 T2 [✓] — Accesibilidad: sin orden de tabulación, nombres accesibles sin guardia y estado por color sin prueba · depende de: —
- `SDLC-UI-028` P3 T2 [✓] — QSS con variantes de botón no oficiales y KPICard que solo muestra la frescura en estado STALE · depende de: —
- `SDLC-UI-030` P3 T2 [✓] — Pruebas visuales sin imágenes de referencia, fuera de CI y con componentes sin cubrir · depende de: SDLC-UI-001

### Lote 49 — WhatsApp (ronda 8)

- `SDLC-WA-047` P2 T1 [B] — 129 except Exception en el microservicio, 29 tragan el error; la taxonomía de errores del canal no existe · depende de: —
- `SDLC-WA-049` P2 T1 [B] — Ninguna de las 20 guardias de arquitectura del canal existe y la única que hay falla · depende de: SDLC-WA-048
- `SDLC-WA-050` P2 T1 [B?] — Eliminación del legacy del canal: bridge con escrituras, orquestador, sender, webhook y notify v1, eventos y migraciones · depende de: SDLC-WA-019, SDLC-WA-021, SDLC-WA-028, SDLC-WA-029, SDLC-WA-035, SDLC-WA-037, SDLC-WA-049
- `SDLC-WA-025` P3 T1 [B] — ~170 textos al cliente fijos en código y menú de 3 botones no configurable · depende de: SDLC-WA-022
- `SDLC-WA-030` P3 T1 [B] — Cantidades por WhatsApp sin gramos, paquete ni caja; la unidad que pide el cliente se ignora · depende de: SDLC-WA-021
- `SDLC-WA-033` P3 T1 [B] — Fidelidad por WhatsApp: SQL directo a loyalty_snapshots y ningún flujo la ofrece · depende de: SDLC-WA-003

### Lote 50 — UI / Design System (ronda 8)

- `SDLC-UI-031` P3 T2 [✓] — Prueba de geometría intermitente: la ventana queda 2 px fuera del área del monitor nuevo · depende de: SDLC-UI-001

### Lote 51 — WhatsApp (ronda 9)

- `SDLC-WA-040` P3 T1 [B] — Alertas internas por WhatsApp sin llamadores y sin política de severidad ni escalamiento · depende de: SDLC-WA-037
- `SDLC-WA-046` P3 T1 [B] — Logs del canal sin correlación y sin métricas de entrega, resolución o latencia · depende de: SDLC-WA-019
- `SDLC-WA-051` P3 T2 [B?] — CLAUDE.md pide preservar shims de WhatsApp que ya no existen y los informes WA-0…22 describen código borrado · depende de: —

