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

## 4. Pendientes honestos (no hechos en esta ronda)

* **Decisión contable pendiente:** Finanzas ya tiene manejadores para
  `LOYALTY_POINTS_ISSUED/REDEEMED/EXPIRED`, cupones y vales, pero nadie los
  suscribe ni drena los outbox. Conectarlos genera asientos por cada punto
  acumulado (pasivo por puntos a valor razonable) y requiere elegir cuentas.
* Tarjetas preimpresas sin asignar y la entidad `LoyaltyCardAssignment`
  (§44-45) no existen en el dominio; tampoco los tipos/estados ampliados de §31.
* Importar plantillas (`ImportLoyaltyCardDesignUseCase` existe) no tiene pantalla.
* Ajuste de puntos con autorización de otra persona no tiene pantalla.
* Ningún despachador drena los outbox de los cuatro contextos (Finanzas y BI no
  reaccionan a Fidelidad).
* La acumulación viva usa los ajustes de `configuraciones` que el usuario
  decidió en SALES-23; el motor declarativo `LoyaltyRule` (§13), stacking (§24)
  y `EvaluateCustomerBenefitsQuery` completo (§25) no están conectados al POS.
* Imprimir/reimprimir boletos desde Fidelidad registra la impresión pero no
  envía nada a una impresora.
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
