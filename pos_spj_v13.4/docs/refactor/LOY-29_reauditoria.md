# LOY-29 — Re-auditoría de Fidelidad, Instrumentos, Sorteos y Tarjetas (2026-10-02)

El prompt maestro de Fidelidad (72 secciones) se volvió a pegar. LOY-0..28 ya
estaban construidos (agosto), así que esto es una **re-auditoría sobre lo que
corre de verdad**: la pantalla viva abierta contra una COPIA de la base real y
cada acción recorrida con los dos usuarios reales (JoseR y Juanis, ambos
`system_owner`) para probar la segregación de funciones.

## 1. Lo que se encontró (medido, no supuesto)

| # | Hallazgo | Gravedad |
|---|----------|----------|
| 1 | El dueño de la instalación tenía 4 de 58 permisos de Fidelidad y **0 de 27** de Tarjetas: veía el módulo pero no podía crear un programa, inscribir a nadie ni emitir una tarjeta. | P0 |
| 2 | 14 de 15 rutas de Fidelidad y 5 de 8 de Tarjetas mostraban "sección en construcción" en el shell vivo. Programas listaba sólo los ACTIVOS, así que "Aprobar" nunca encontraba un borrador. Los clientes y membresías se capturaban pegando el UUID. | P0 |
| 3 | **El creador podía aprobar su propio programa** y una segunda aprobación pisaba a la primera (§60). | P0 |
| 4 | Reversar una acumulación ya canjeada dejaba el saldo **negativo** (§29). | P1 |
| 5 | El escaneo de tarjeta en el POS buscaba SÓLO en la tabla legacy `clientes`: **ninguna tarjeta canónica identificaba al cliente**. | P0 |
| 6 | Cliente 360 leía `loyalty_snapshots` (legacy, sin escritores): todo cliente aparecía "no inscrito, 0 puntos". | P1 |
| 7 | **Ningún caso de uso auditaba** (§61): los escritores de auditoría existían y nadie los llamaba. | P1 |
| 8 | Dos libros de puntos: el saldo sumaba `loyalty_ledger` (legacy) + `loyalty_transactions`. En la base real el legacy tenía 0 filas. | P2 |
| 9 | 38 tablas legacy (Growth Engine, `loyalty_*` viejas, `tarjetas_fidelidad`, `raffle_*`…) vivas en la base; todas vacías salvo una fila de configuración de fábrica; sin lectores tras esta ronda. | P2 |
| 10 | Reimprimir un boleto no pedía motivo (§28). | P2 |
| 11 | El diseño de tarjeta era de una sola cara (sin reverso) y el validador aceptaba claves desconocidas de primer nivel. El PDF no traía marcas de corte. | P2 |
| 12 | Tarjetas era una entrada global aparte (§5-6 la quiere dentro de Fidelidad). | P2 |

## 2. Lo que se cerró

1. **Migración 290** — siembra las acciones de `GROWTH_ENGINE` y
   `TARJETAS_FIDELIDAD`: dueño y admin todo; gerente el juego operativo (sin
   definir/aprobar programas, campañas, plantillas ni lotes; sin sortear ni
   rotar QR); cajero y solo_lectura nada nuevo. Mismo criterio que la 260
   (Precios), aprobado entonces por el usuario.
2. **UI completa, declarativa**: `records/` (página genérica sobre
   `WorklistPage`, diálogo generado desde `FieldSpec`, pestañas) + catálogos de
   Fidelidad y Tarjetas. 31 rutas reales, cada una visible sólo con su propio
   permiso de lectura. Resumen con los seis KPI del §64, Alertas, Perfil de
   miembro y Canjear con el buscador estándar de Clientes. **Tarjetas** es una
   sección DENTRO de Fidelidad (resumen, tarjetas, plantillas+versiones,
   diseñador, formatos y pliegos, lotes, impresión, reimpresiones, tarjetas
   digitales, QR y validación, auditoría); su módulo global se retiró. La
   etiqueta global pasa de "Fidelización" a "Fidelidad".
3. **Lado de lectura**: `LoyaltyRecordsQueryService` (35 registros, permiso por
   registro, búsqueda/estado/paginación, filtros sólo por claves declaradas),
   saldos de cuentas y vales derivados del libro con la política de dominio,
   resumen §64, alertas y resumen de tarjetas.
4. **Dominio**: segregación al aprobar programas y bloqueo de doble aprobación;
   reverso que no deja saldo negativo; reimpresión de boleto con motivo
   obligatorio; esquema de diseño con reverso (`back_elements`) y lista blanca de
   claves; `LoyaltyCardPrivacyPolicy` (§37: modo de nombre, puntos ocultos por
   omisión).
5. **Tarjetas**: `ResolveLoyaltyCardQuery` (§49) — QR `SPJ-CARD:<token>`,
   código de barras o número; QR rotado/revocado y tarjeta bloqueada no
   identifican a nadie. El **POS** la usa primero al escanear.
   `LoyaltyCardRenderDataQuery` arma las variables impresas (privacidad incluida),
   los destinatarios de un lote (membresías activas sin tarjeta vigente) y el
   diseño vigente de una plantilla. Renderizador con **reverso en página espejo
   (dúplex por borde largo)** y **marcas de corte**. Diseñador con capas,
   variables, guías y vista previa; guardar crea una versión nueva.
6. **Auditoría (§61)**: `_emit` de los cuatro contextos escribe `audit_logs` en
   la misma transacción; las transiciones sin evento canónico (aprobar, suspender…)
   también quedan auditadas. Nunca viaja un token.
7. **Un solo libro**: se retiró la doble lectura de `loyalty_ledger`; Cliente 360
   consume `LoyaltyCustomerSummaryQueryService` (propiedad de Fidelidad).
8. **Migración 291** — retira las 38 tablas legacy vacías (y la configuración de
   fábrica); una tabla con historia se CONSERVA y se avisa en el log.
9. **Código legacy eliminado**: `backend/application/use_cases/create_customer_use_case.py`
   (escribía `tarjetas_fidelidad`), `backend/application/queries/customer_history_query_service.py`
   (leía `loyalty_ledger`), `loyalty_query_service.py`, `loyalty_commands.py`,
   `assign_loyalty_card_use_case.py`, `redeem_loyalty_points_use_case.py` (tres
   clases distintas se llamaban `RedeemLoyaltyPointsUseCase`), las páginas viejas
   de Programas/Cupones-Vales/Sorteos y el módulo `tarjetas_fidelidad/`.

## 3. Tabla obligatoria (§72)

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|---|---|---|---|
| fidelidad_config.py / Growth Engine | `frontend/desktop/modules/fidelidad` + use cases | DELETE (ya borrado con `modulos/`) | 0 |
| LoyaltyService legacy | `backend/application/loyalty` | DELETE (ya borrado con `core/`) | 0 |
| saldo sumando `loyalty_ledger` | `loyalty_transactions` + `LoyaltyBalancePolicy` | DELETE | 0 |
| tablas legacy (38) | esquemas canónicos | DROP (291) | 0 |
| `loyalty_snapshots` en Cliente 360 | `LoyaltyCustomerSummaryQueryService` | REWRITE | 0 |
| escaneo de tarjeta sobre `clientes` | `ResolveLoyaltyCardQuery` | REWRITE (búsqueda por teléfono sigue en Clientes) | POS |
| tarjeta dentro de un módulo global | sección Tarjetas en Fidelidad | MOVE | 0 |
| páginas "en construcción" | páginas declarativas | REWRITE | 0 |
| permiso `GROWTH_ENGINE.ver` como único útil | 58 + 27 acciones granulares sembradas | SEED (290) | — |
| diseño de una sola cara | `elements` + `back_elements` validados | EXTEND | — |

## 3b. Segunda tanda (misma sesión, migración 292)

* **QR sin token en claro (§32).** `loyalty_card_tokens` guarda `token_hash`
  (SHA-256), `token_prefix` y `token_version`; el token se deriva con HMAC del
  secreto de la instalación (`loyalty_card_secrets`, en la base para que una
  tarjeta pueda reimprimirse en cualquier sucursal con el MISMO QR) y del id del
  registro. Resolver un escaneo sólo necesita la huella. La proyección digital
  guarda `token_id` y deriva el QR al leer. La 292 reconstruye ambas tablas; las
  filas previas quedan como huella con versión 0 (resuelven, pero hay que rotar
  para reimprimir). Ojo: la base real trae una vista legacy rota
  (`v_negative_inventory` → `branch_inventory_old`); renombrar en modo moderno la
  revalidaba y tumbaba el arranque, por eso la 292 renombra con
  `legacy_alter_table=ON`.
* **PDF entregado.** Generar impresión / Reimprimir devuelven el PDF y la
  pantalla ofrece guardarlo (antes se generaba y se descartaba).
* **Privacidad de tarjetas** con pantalla propia (Configuración de tarjetas).
* **Ajuste de puntos con autorización de otra persona** (usuario y clave
  verificados como en el login; el autorizador necesita `puntos.ajustar`); ni el
  ajuste ni el reverso pueden dejar saldo negativo.

## 3c. Tercera tanda (migración 293): tarjetas preimpresas (§44-45)

* Estado `UNASSIGNED`: la tarjeta nace con número y QR, sin cliente ni
  membresía. «Lote preimpreso» genera N tarjetas así; «Asignar» la entrega a una
  membresía (una sola vez, nunca se reasigna; una membresía no puede tener dos
  tarjetas vigentes) y queda en `loyalty_card_assignments` con quién, cuándo,
  dónde y por qué. Después se activa como cualquier tarjeta. Escanear una tarjeta
  sin asignar no identifica a nadie y lo dice.
* La 293 reconstruye `loyalty_cards` para admitir NULL en cliente/membresía
  (llaves foráneas desactivadas durante la copia y verificadas al final).
* Instalación desde cero verificada: ninguna tabla legacy, modelo nuevo.

## 3d. Cuarta tanda

* **Importar diseño** (PNG/JPEG/SVG) desde Plantillas: crea una versión nueva por
  aprobar; un SVG con script o un PDF se rechazan.
* **Boletos impresos de verdad**: «Imprimir»/«Reimprimir» envían el boleto a la
  impresora de tickets de la sucursal (ruta de Document Output, la misma del
  ticket de venta) DESPUÉS de validar y ANTES de registrar; sin impresora no se
  registra impresión fantasma. La copia lleva «(COPIA)».

## 3e. Contabilidad de Fidelidad (2026-10-03, migración 294)

Decisión del usuario: "contabiliza los puntos, cupones, vales, boletos y
cualquier programa de fidelidad". Medido antes: **ningún** movimiento de
Fidelidad llegaba a contabilidad (los manejadores de Finanzas existían sin
suscriptor) y los bonos de cumpleaños, retos y referidos ni siquiera emitían
evento. El puente (`backend/application/loyalty/integrations/finance_posting.py`)
lee los LIBROS, no los eventos:

| Movimiento | Asiento (cuentas del perfil contable) |
|---|---|
| Acumulación / bono / ajuste a favor | Dr 4202 contra-ingreso de fidelidad / Cr 2130 pasivo por puntos, al valor del punto vigente |
| Canje en una venta | Dr 2130 / Cr 4201 descuento (la venta ya cargó el canje como descuento: no hay doble ingreso) |
| Canje fuera de venta (recompensa, boleto por puntos) | Dr 2130 / Cr 4101 ingreso |
| Caducidad | Dr 2130 / Cr 4120 breakage, sólo lo que queda (FIFO) |
| Ajuste en contra, reverso de acumulación | espejo parcial del reconocimiento |
| Reverso de un canje (venta cancelada) | espejo del asiento del canje |
| Apartado (RESERVE) | nada hasta confirmarse; liberado no asienta |
| Vale emitido / canjeado / vencido / cancelado | pasivo según su naturaleza / Dr pasivo Cr ingreso / breakage / retiro |
| Cupón en venta | reclasificación Dr 4203 (o 1135 si lo financia el proveedor) / Cr 4201 |
| Premio de sorteo | provisión al activar (Dr 6110 / Cr **2136** nueva), uso al entregar, liberación al resolver o cancelar |

Cada consumo de puntos se asigna FIFO a sus acumulaciones (cada una a su valor
reconocido); el estado vive en `loyalty_finance_links` y lo fallido queda
FAILED, se reintenta solo y se ve en **Control → Contabilidad** (con alerta).
Se dispara tras cada comando de Fidelidad, tras cada venta/cancelación/
devolución y al abrir Fidelidad. Verificado sobre copia de la base real:
4 pólizas, todas cuadradas.

## 3f. Las reglas salen de Fidelidad y el POS las ejecuta (2026-10-03, migración 295)

Decisión del usuario. Antes: `LoyaltyRule` (§13), la política de combinación
(§24) y `EvaluateCustomerBenefitsQuery` (§25) no existían; el POS acumulaba 1
punto por cada $N fijo de `configuraciones`.

* **`LoyaltyRule`** (dominio): 14 tipos; los 11 que se evalúan con una compra
  se crean en **Programas → Reglas de acumulación** (cumpleaños, referidos y
  retos se otorgan desde Beneficios — el maestro de clientes ni siquiera guarda
  fecha de nacimiento). Prioridad, vigencia, acumulable, límites (totales, por
  cliente, por día, por mes) y alcances por sucursal, canal, forma de pago,
  producto, categoría (con subcategorías), segmento de cliente y programa.
  Condición en un lenguaje declarativo CERRADO (campos y operadores conocidos,
  sin `eval`/`exec`). La activa otra persona (§60); activa no se edita.
* **Motor** (`LoyaltyRuleEngine`, puro): base de Configuración (o reglas base
  que la sustituyen para su alcance) + multiplicadores + bonos; puntos enteros
  hacia abajo; cada regla descartada dice por qué. **Sin reglas activas el POS
  acumula exactamente como antes.**
* **El POS las ejecuta**: el cobro manda líneas, canal y pagos en
  `SALE_COMPLETED`; `AccrueSalePointsUseCase` evalúa UNA vez, guarda el
  desglose (`loyalty_sale_evaluations`, pestaña «Puntos por compra») y los usos
  por regla, y acredita; un reintento acredita lo guardado. «Puntos a ganar» en
  el POS es el mismo cálculo.
* **Combinación de beneficios** (§24): 8 combinaciones × 6 opciones,
  configurables en Control → Combinación de beneficios; arranque: todo se
  combina salvo varios cupones.
* **`EvaluateCustomerBenefitsQuery`** (§25): carrito, sucursal, canal, pago,
  cupones, vales y puntos pedidos → elegibles, descartados con motivo, desglose
  de descuentos, puntos a ganar/canjear, cupones y vales a reservar, efecto
  financiero previsto.
* Verificado en copia real: regla «categoría doble» creada por un usuario y
  activada por otro; venta de $200 → 20 base + 20 de la regla, desglose
  guardado y asentado en contabilidad.

## 3g. Pendientes cerrados (2026-10-03, migraciones 296 y 297)

Decisiones del usuario, una por pendiente:

| Pendiente | Decisión | Cómo quedó |
|---|---|---|
| Cupones en caja | Descuento del ticket | Botón «Cupón» en el POS; Fidelidad valida vigencia, dueño y combinación (§24, un cupón por venta de arranque) y lo aparta; el % sigue al carrito; cobrar lo canjea con el importe aplicado y el puente lo reclasifica a 4203; cancelar lo libera. Tabla `sale_coupons`. |
| Vales en caja | Forma de pago | Método «Vale / saldo a favor» (`POS.pago.vale`, sembrado a cajero/gerente/admin/dueño): aparta hasta su saldo, la venta liquida el pasivo del vale (no entra al cajón; Caja lo ve como instrumento), cobrar confirma el canje; devolución/reverso regresan el dinero al vale. |
| Vale prepagado | Venderlo en el POS | Botón «Vender vale»: línea del ticket sin inventario, sin costo y sin puntos; se cobra como cualquier venta (Dr caja / Cr 2132 con el perfil nuevo `PREPAID_VOUCHER`) y se activa al cobrar; emitirlo desde Fidelidad ya no se permite; un vale ya usado impide reversar su venta; uno sin cobrar se anula con la venta. |
| Recompensa de producto | Descontar inventario | La recompensa declara el producto (código) y cantidad; confirmar la entrega da salida del almacén de venta de la sucursal (sin existencia no se entrega) y el puente asienta Dr 5101 / Cr 1150 al costo. |
| Cumpleaños | Opcional con consentimiento | Día/mes (año opcional) en Clientes → Editar, sólo con la casilla de consentimiento (sin ella no se guarda; quitarla lo borra). Habilita la regla «Bono de cumpleaños» (puntos o multiplicador, ventana de días) y el beneficio de cumpleaños de cada programa, que se otorga solo, una vez al año, dentro de su ventana. |
| Devoluciones con bono fijo | Bono sólo si deja de cumplir | Base y multiplicadores en proporción; cada bono fijo se retira completo sólo si lo que queda ya no cumple su condición de importe o la devolución es total. |

Además: las reglas evalúan en hora LOCAL (sábados, horarios, vigencia y
cumpleaños) y guardan en UTC. Hallazgo fuera de alcance, corregido porque
bloqueaba la pantalla del cumpleaños: el Expediente y la edición de cliente
reventaban para CUALQUIER cliente en la base real (el resumen de reparto
ordenaba por una columna `fecha` que la tabla real no tiene).

## 4. Pendientes honestos (no hechos en esta ronda)

* Un canje de cupón sin venta no se asienta (el descuento lo asienta quien lo
  aplicó). Los boletos no se venden: no tienen asiento propio. Un vale
  prepagado no se devuelve como mercancía (se anula en Fidelidad o se reversa
  la venta). La regla de bono por devolución sólo reevalúa condiciones de
  importe (unidades o renglones devueltos no viajan a Fidelidad).
* Tipos y estados ampliados de §31 (PHYSICAL_AND_DIGITAL, LOST/STOLEN…) no
  existen; la reposición no registra el motivo.
* Ajuste de puntos con autorización de otra persona no tiene pantalla.
* BI no reacciona a Fidelidad (Finanzas ya sí, por el puente de libros).
* La pantalla de ajustes de privacidad de tarjetas (las claves ya existen).

## 5. Verificación

* Recorrido de punta a punta sobre copia de la base real (`flow_fid.py`):
  programas, membresías, puntos, niveles, recompensas, retos, campañas,
  cumpleaños, cupones, vales, sorteo completo, antifraude, pliego 12×18 (3×7 =
  21 tarjetas CR80), plantilla con reverso, emisión, QR, rotación, lote con
  segundo aprobador, impresión y reimpresión. Auditoría: 24 filas de Fidelidad
  y 14 de Tarjetas.
* Pruebas nuevas: `tests/integration/loyalty/test_loy29_*`,
  `tests/unit/test_loy29_fidelidad_ui.py`,
  `tests/unit/loyalty_cards/test_loy29_privacy_and_duplex.py`,
  `tests/architecture/test_loyalty_loy29_guardrails.py`, escaneo canónico en
  `tests/unit/test_sales_customer_integration.py`.
