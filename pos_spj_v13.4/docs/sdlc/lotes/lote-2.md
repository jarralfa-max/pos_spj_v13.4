# Lote 2 — Finanzas y RRHH

Rama `fix/lote-2`, sale de `e58f6849` (`claude/erp-financial-bounded-context-uqxz6b`). Corrección directa desde
los `intent.md` aprobados (2026-11-05, Alfred). Sin spec ni plan. Falta la revisión independiente que el nivel T0 exige.

| Ítem | Estado | Commit |
|---|---|---|
| SDLC-FIN-002 | **LISTO** (medición en copia de la BD: no corrida, ver abajo) | `8b92c07e`, `152a7b20` |
| SDLC-FIN-003 | **LISTO** | `7fa6ed32` |
| SDLC-HR-001 | **BLOQUEADO parcial**: faltas y retardos listos; cuota patronal espera las tablas | `51d0e71d` |
| SDLC-HR-002 | **LISTO** | `135b5b04` |
| SDLC-FIN-001 | **LISTO** | `b6c631f2` |
| SDLC-FIN-004 | **LISTO** | `10721ae6` |

## Pregunta abierta para el responsable

**SDLC-HR-001, cuota patronal.** La respuesta fue «lo hace el sistema», pero el cálculo necesita datos que no están en
el repositorio ni en el intent: UMA vigente, prima de riesgo de trabajo de la empresa, tabla de cesantía y vejez por
año, e integración del salario base de cotización. `docs/refactor/HR-AUD_auditoria_cebf67a.md:102` ya dice que el motor
fiscal requiere tablas oficiales vigentes y decisión del contador. No se inventó ninguna tasa.

Hasta tener esos datos, **la cuota patronal sigue en 0**: el objetivo «cuota patronal provisionada» no se cumple en
producción. Queda listo el punto de conexión (`EmployerContributionProvider`) y el asiento Dr 6105 / Cr 2125, probado
con un proveedor de prueba. Al conectar el cálculo real sólo cambia el proveedor que recibe `PayPayrollRunUseCase` en
`frontend/desktop/modules/hr/hr_routes.py:129`.

## Por ítem

### SDLC-FIN-002: activo comprado llega al auxiliar sin duplicar

- **Problema confirmado** en los dos puentes de Compras y en `CapitalizeAssetUseCase`.
- **Alta automática** (respuesta del responsable): con naturaleza `ASSET`, los puentes de crédito y contado dejan el
  activo en `fixed_assets`, en la misma transacción que su asiento. Nace en `DRAFT`, con el subtotal `ASSET` como costo
  y vida útil 0, porque ni el evento ni las categorías sembradas traen una vida útil.
- **Actualizar hasta completar:** Finanzas → Activos fijos → «Completar datos» (`CompletePurchasedAssetUseCase`) guarda
  avances. Con vida útil capturada, o la de su categoría, queda `ACTIVE` sin asiento. La cuenta de activo sigue siendo
  la que Compras cargó, aunque la categoría diga otra: la baja debe acreditar esa cuenta.
- **Doble capitalización:** `CapitalizeAssetUseCase` rechaza un documento ya presente en el auxiliar. Compara por folio
  (`fixed_assets.source_document_number`) y proveedor, y acepta cualquier parte de un folio `compra / recepción`.
- **Cierre:** nuevo punto bloqueante `purchased_assets_completed`. Antes el checklist no veía estos activos.
- **Compensaciones:** una devolución o un reverso de Compras baja el costo del activo o lo cancela. Sin esto, el
  auxiliar habría seguido depreciando lo que ya salió del mayor.
- **Bug adicional corregido:** `FinancePresenter._command(name, ...)` chocaba con el campo `name` del activo. Por eso
  «Capitalizar activo» reventaba con `TypeError` antes de llegar al caso de uso. Ahora `name` es solo posicional.
- **Prueba:** `tests/integration/finance/test_fin002_purchased_asset.py` (28).

### SDLC-FIN-003: la baja deprecia lo pendiente

- **Baja:** corre lo que falte hasta el periodo anterior, en su misma transacción y como corrida registrada. El mes de
  la baja no se deprecia. El asiento lleva la fecha de la baja, porque si la baja se puede asentar ese periodo también
  admite lo recuperado, aunque el mes omitido ya esté cerrado.
- **Meses omitidos:** `DepreciationPolicy` los recupera en el siguiente periodo corrido, ya no sólo en el último mes.
- **Suspensión:** un mes suspendido no es un mes omitido. No se recupera y alarga la vida en calendario. Requirió la
  migración 381 para distinguirlos. Una baja de un activo suspendido recupera sólo lo anterior a la suspensión.
- **Prueba:** `tests/integration/finance/test_fin003_asset_disposal.py` (28): venta con ganancia y con pérdida, desecho,
  castigo, suspensión, reactivación, idempotencia por `disposal_journal_entry_id` y balanza cuadrada.

### SDLC-HR-001: cuentas del asiento de nómina

- **Hecho:** faltas y retardos viajan aparte (`unearned_deductions`) y reducen el gasto de sueldos sin tocar 2125. ISR,
  cuota obrera y préstamos siguen en sus cuentas. Un evento anterior al cambio aún se asienta.
- **No hecho:** el importe de la cuota patronal (ver pregunta abierta).
- **Prueba:** `tests/integration/finance/test_hr001_payroll_accounts.py` (7).

### SDLC-HR-002: reintento periódico y aviso

- **Hecho:** servicio de fondo `hr.outbox` cada 2 minutos. Si el asiento no se entrega, `pay_payroll` responde «Nómina
  pagada. El asiento contable quedó pendiente…».
- **Prueba:** `tests/integration/finance/test_hr002_payroll_delivery.py` (8).
- **Limitación previa, sin cambio:** `MAX_ATTEMPTS = 10`. A 2 minutos, un fallo de más de unos 20 minutos deja de
  reintentarse, también tras reiniciar. El evento sigue visible en `pending_report` y cuenta en el cierre.

### SDLC-FIN-001: manejadores muertos

- **Verificado:** ningún archivo de `backend/` ni `frontend/` importaba estos módulos; sólo los mencionaban comentarios.
- **Retirados:** 16 manejadores y `instrument_event_adapters.py`, que sólo ellos usaban. `CommercialInstrumentProcessor`
  sigue: lo usan el puente de Fidelidad y la venta.
- **Pruebas migradas:** `test_commercial_instruments.py` y `test_loyalty_instruments.py` ahora ejercitan el procesador;
  `test_purchase_handler.py` y `test_financial_statements.py`, el puente de Compras.
- **Dos pruebas no migradas**, porque la regla viva ya tiene la suya:
  - costo de premio: `test_confirming_a_product_reward_issues_stock_and_posts_its_cost`;
  - valuación de puntos: `test_accrual_recognizes_liability_at_point_value`.
- **Guardia nueva:** `test_finance_keeps_one_implementation_per_instrument_rule`. `DARK_HANDLERS` perdió las 15 entradas.

### SDLC-FIN-004: depreciación automática

- **Hecho:** `finance_periodic_tick` corre el mes que terminó desde el día 1 (respuesta del responsable). Si la app
  estuvo apagada ese día, corre en el primer ciclo después. El `operation_id` se deriva del periodo.
- **Periodo cerrado:** se omite sin error y lo recupera el mes siguiente (depende de FIN-003).
- **Un fallo** no detiene el resto del ciclo: se registra y se reintenta. Si el mes faltante no existe y hay uno
  posterior cerrado, el error se repite en el registro cada 5 minutos.
- **Corrida sin usuario:** `run_by` vacío identifica la automática.
- **Prueba:** `tests/integration/finance/test_fin004_scheduled_depreciation.py` (11).

## Efectos a considerar al liberar

- **Primer ciclo tras instalar:** cada activo activo se deprecia con todos sus meses atrasados en un solo asiento,
  por las respuestas a FIN-003 y FIN-004. Puede ser un importe grande si la depreciación estaba rezagada.
- **Cierre más estricto:** un activo comprado sin completar bloquea el cierre del mes.
- **Activos suspendidos antes de la 381:** no tienen `suspended_on`, así que sus meses cuentan como omitidos y se
  recuperan al reanudarlos.

## Limitaciones conocidas

- Un activo por documento: varias líneas `ASSET` de una compra forman un solo registro, porque el evento sólo trae el
  subtotal por naturaleza. Una compra a crédito con varias recepciones genera un activo por recepción, y una factura
  mayor a lo recibido genera otro por la diferencia.
- La guardia de doble capitalización no cubre un alta manual pagada de tesorería sin folio, ni el número de factura de
  una compra a crédito reconocida por recepción (el folio guardado es el de compra / recepción).
- Tampoco distingue un activo cancelado por reverso: su folio sigue rechazándose.
- Activo ya depreciado que Compras devuelve: no se ajusta solo. Se registra el error y requiere baja formal.
- Devolución de una compra de contado con factura: el activo está ligado a la compra y la devolución a la factura, así
  que no se ajusta.
- Depreciación automática y varias estaciones: en bases locales separadas, cada una correría la suya. No se midió cómo
  se replica `fixed_assets`.
- `reverse_payment` y `grant_loan` conservan el patrón de HR-002 de ignorar el resultado del despacho (fuera de alcance).

## Migraciones

| Núm. | Cambio | Comprobación |
|---|---|---|
| 380 | `fixed_assets.source_document_number` | Idempotente; sólo agrega |
| 381 | `fixed_assets.suspended_on`, `suspended_months` | Idempotente; sólo agrega |

Ambas registradas en `migrations/engine.py` y en `POST_CONTRACT_COLUMNS`. `scripts/bootstrap_db.py` sobre una base vacía
en el directorio temporal: 333 migraciones, 380 y 381 aplicadas, columnas presentes, `foreign_key_check` vacío.

**No corrido:** la migración sobre una copia de la BD real, y la medición de FIN-002 de compras `ASSET` sin auxiliar. El
responsable indicó que no hay datos; no hay copia en este worktree.

## Resultados de pruebas

| Comando | Resultado |
|---|---|
| `python -m compileall -q .` | rc=0 |
| `tests/integration/finance tests/unit/finance tests/integration/hr tests/unit/hr tests/integration/procurement tests/integration/loyalty tests/integration/shell/test_hr_module_migration.py` | **963 passed** |
| 10 archivos de guardias del área + `tests/integration/finance` (sobre `152a7b20`) | **2 failed, 372 passed** (16:55), ambos de línea base |
| `tests/architecture` completo (sobre `2f6da855`) | **22 failed, 880 passed, 1 skipped, 2 xfailed** (35:32) |
| `tests/unit` e `integration` completos | **No corridos**: sólo las áreas tocadas |

Esas 963 se corrieron antes de `152a7b20`. Después de ese commit se repitió `tests/integration/finance` (fila de guardias).

## Fallos preexistentes

Sin fallos en unit e integración de las áreas tocadas. En las guardias fallan dos, ambos en la línea base
(`docs/sdlc/baseline/2026-10-28.md`, SDLC-CORE-008):

- `test_no_raw_sqlite_connect_outside_pool`: `finance_schema.py:955`. Es la línea 952 de la línea base, movida 3 líneas
  por las columnas nuevas; este lote no agregó conexiones.
- `test_clean_birth_guardrails.py::test_services_repositories_ui_do_not_create_schema`: la línea base lo atribuye a
  `unit_repository.py`, que este lote no toca.

`tests/architecture` completo: los mismos 22 fallos de la línea base, prueba por prueba (SDLC-CORE-008, CORE-009 y
WA-005), y ninguno nuevo. Pasan 880 frente a 879: la diferencia es la guardia nueva de FIN-001.
