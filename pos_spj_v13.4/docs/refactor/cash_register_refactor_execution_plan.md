# CASH-0 — Plan de ejecución del refactor de Caja

Fecha de auditoría: 2026-08-03  
Estado: `CASH-0 AUDITED` — no autoriza avanzar a `CASH-1` mientras la línea base de tests no esté verde.  
Alcance: Caja, cajones, terminales, turnos, ledger, conteos, cortes, pagos, hardware, impresión, notificaciones, permisos e integraciones.

## 1. Decisiones obligatorias

- El bounded context canónico se denomina `cash_register` y debe vivir en `backend/domain/cash_register/`, `backend/application/cash_register/`, `backend/infrastructure/db/repositories/cash_register/` y `frontend/desktop/modules/cash_register/`.
- UUIDv7 es la única identidad. `event_id`, `operation_id` y `entity_id` son UUID distintos.
- Todo monto se representa con `Decimal` en dominio, comandos, DTO, casos de uso y repositorios. SQLite podrá persistir texto decimal o minor units según la decisión de `CASH-3`; no se acepta `REAL` como contrato monetario nuevo.
- Caja registra liquidación y custodia física. Compras, nómina, CAPEX y pagos bancarios pertenecen a Tesorería/Finanzas.
- Un turno tiene un único ledger reconstruible, un único conteo final confirmado y un único Corte Z final.
- La UI solo consume QueryServices y Use Cases. No calcula saldos, diferencias ni efectivo esperado.
- No se conservarán datos de desarrollo legacy ni se crearán rutas duales. El esquema born-clean se corregirá en la fuente.

## 2. Línea base encontrada

### 2.1 Frontend y navegación

| Elemento | Ubicación actual | Hallazgo | Clasificación CASH-25 |
|---|---|---|---|
| Vista principal | `modulos/caja.py` (1553 líneas) | `ModuloCaja` y `DialogoCorteZCiego` siguen en carpeta legacy | `REWRITE`, después `DELETE` |
| Navegación | `interfaz/main_window.py` | Registra directamente `ModuloCaja` | `MOVE` |
| Menú | `interfaz/menu_lateral.py` | Una entrada visible `CAJA`, aún con texto/icono legacy | `MOVE` |
| Cálculos UI | `modulos/caja.py` | Suma fondo, ventas, ingresos, retiros, subtotales y formatos mediante `float` | `REWRITE` |
| Estilos UI | `modulos/caja.py` | Numerosos `setStyleSheet()` locales y widgets directos | `REWRITE` |
| Impresión | `modulos/caja.py` | Construye payload/HTML de corte localmente | `MOVE` |

No se detectó SQL directo actual en `modulos/caja.py`; las lecturas fueron extraídas parcialmente. Esto no vuelve canónica a la vista: conserva cálculos monetarios, presentación de tickets y arquitectura legacy.

### 2.2 Aplicación y dominio

| Elemento | Ubicación actual | Hallazgo | Clasificación |
|---|---|---|---|
| Orquestador | `backend/application/services/cash_register_application_service.py` | Delega apertura, movimiento y Corte Z a `FinanceService`; publica eventos antes de contar con UnitOfWork/outbox garantizado | `REWRITE` |
| Commands | `backend/application/commands/cash_register_commands.py` | Montos `float`; Corte Z recibe efectivo físico en `payload` genérico | `REWRITE` |
| Use Cases | `backend/application/use_cases/{open_cash_shift,register_cash_movement,generate_z_cut}_use_case.py` | Son shells de delegación sin invariantes propias | `REWRITE` |
| QueryService | `backend/application/queries/cash_register_query_service.py` | Adaptador genérico; no expone DTOs específicos de turno, ledger, conteo o corte | `REWRITE` |
| Dominio Caja | inexistente | No hay entidades/policies canónicas para register, drawer, terminal, shift, ledger, count, cuts, differences o handover | `CREATE` |
| Servicio de cierre | `core/services/cierre_caja_service.py` | Ruta legacy paralela | `DELETE` tras cobertura |
| Auto cierre | `core/services/caja_auto_close.py` | Consumidor legacy que debe convertirse en policy/job canónico | `MOVE` |
| Repositorio | `repositories/caja.py` | SQL y escritura duplicada en `caja_operations` y `movimientos_caja`; contrato `float` | `REWRITE`, después `DELETE` |
| Finanzas legacy | `core/services/enterprise/finance_service.py` | Aún posee `abrir_turno`, movimiento manual y Corte Z | `DELETE` de responsabilidades de Caja |

### 2.3 Persistencia

El esquema fuente `migrations/m000_base_schema.py::_create_caja` crea actualmente:

| Tabla | Uso observado | Decisión preliminar |
|---|---|---|
| `movimientos_caja` | log operativo legacy | `REPLACE` por ledger canónico |
| `caja_operations` | idempotencia/operaciones paralelas | `MERGE` con ledger y registro de operaciones |
| `turnos_caja` | turno principal actual | `REPLACE` por `cash_shifts` |
| `cierres_caja` | historial de cortes | `REPLACE` por documentos X/Z inmutables |
| `turno_actual` | segunda fuente de turno abierto | `DROP` |
| `cajas` | caja física incompleta | `REPLACE` por `cash_registers`, `cash_drawers` y `pos_terminals` |

Hallazgos de esquema:

- Las PK son `TEXT`, pero faltan FKs y constraints funcionales en la sección auditada.
- Los montos están en `REAL` y varios defaults monetarios son `0` numérico.
- Los estados son texto libre.
- No existen modelos canónicos separados para conteo ciego, denominaciones, Corte X, diferencias, entrega de valores, apertura de cajón ni terminal bancaria.
- Existen tablas financieras adicionales (`pagos_cobros`, `pagos_cobros_aplicaciones`, `cortes_caja_erp`) que requieren consolidación de fronteras, no reutilización automática.
- La migración standalone `080_caja_turno_id_link.py` evidencia deuda de relación legacy y no debe formar parte del arranque born-clean futuro.

### 2.4 Pagos e integraciones

- Ventas y Caja ya cuentan con tests sobre exclusión de tarjeta/transferencia/crédito del efectivo esperado, pero la lógica sigue alojada en servicios legacy.
- Compras tiene guardrails para no escribir `movimientos_caja`; deben mantenerse durante todo el refactor.
- Finanzas consume `CASH_SHIFT_CLOSED` mediante `backend/application/event_handlers/finance/cash_shift_closed_handler.py`.
- RRHH consume apertura/cierre mediante handlers de asistencia. La identidad `employee_id` debe permanecer separada de `user_id`.
- Existe `core/events/cash_event_bridge.py`, que mapea eventos españoles legacy a eventos canónicos: es una ruta dual y su destino final es `DELETE`.
- Hardware e impresión siguen concentrados en `core/services/hardware_service.py` y `core/services/printer_service.py`; se reutilizarán únicamente detrás de gateways hasta reemplazarlos.
- Notificaciones y WhatsApp tienen infraestructura general, pero Caja aún no posee policy, gateway y deduplicación propios.

### 2.5 Seguridad

El catálogo actual solo declara:

```text
CAJA.ver
CAJA.abrir
CAJA.cerrar
CAJA.retiro
CAJA.corte_z
```

Es insuficiente para consulta sensible, cajas/terminales, movimientos, conteos, Corte X, diferencias, entregas, reembolsos, cajón, hardware, impresión, configuración y notificaciones. La expansión se hará en `CASH-1` con scope de sucursal, límites monetarios, autorización en caliente y segregación de funciones; no se autorizará por nombre de rol.

## 3. Riesgos priorizados

| Prioridad | Riesgo | Evidencia | Protección requerida |
|---|---|---|---|
| P0 | Montos y diferencias pierden precisión | Commands, ApplicationService, repositorio y UI usan `float`; schema usa `REAL` | Tests Decimal de dominio e integración |
| P0 | Cierre no es atómico ni post-commit | ApplicationService delega y publica mediante callback sin UoW/outbox común | Test de rollback e idempotencia de Corte Z |
| P0 | Múltiples fuentes de turno/saldo/corte | Seis tablas de Caja y servicios paralelos | Tests de una sola ruta y consolidación de schema |
| P0 | Doble Corte Z/reintento | No hay constraint canónico visible por turno final | `UNIQUE(cash_shift_id, final_z_cut)` o equivalente |
| P1 | Eventos incompletos | Algunos payloads carecen de `event_id`, `entity_id`, `user_id`, timestamp y source_module | Test de contrato canónico |
| P1 | UI puede divergir del backend | La vista calcula totales y diferencia con `float` | DTO calculado por QueryService/Use Case |
| P1 | Permisos demasiado amplios | Cinco acciones bajo `CAJA` | Matriz granular y tests de scope/límites |
| P1 | Puente de eventos duplica consumidores | `core/events/cash_event_bridge.py` | Ratchet de eventos legacy y cero consumidores |
| P2 | Hardware/impresión acoplados | Servicios legacy compartidos | Gateways y tests de fallo no transaccional |
| P2 | Notificaciones duplicables | Sin policy/idempotencia específica de Caja | Outbox + dedupe_key + tests |

## 4. Tests de caracterización existentes a conservar

- `tests/unit/test_cash_cut_denomination_recalculation.py`
- `tests/integration/test_cash_z_cut_blind_count_flow.py`
- `tests/integration/test_cash_z_cut_expected_cash_excludes_card_transfer_credit.py`
- `tests/integration/test_cash_register_application_service.py`
- `tests/integration/test_cash_module_direct_movements_only.py`
- `tests/integration/test_purchase_does_not_touch_cash_register.py`
- `tests/integration/test_cash_cut_increments_capital.py`
- `tests/integration/test_caja_turno_str_identity.py`
- `tests/test_caja_corte_z_characterization.py`
- `tests/test_caja_ticket_uses_escpos.py`

Estos tests protegen comportamiento existente, pero no demuestran la definición enterprise de terminado. En cada fase se añadirán tests antes de retirar la ruta cubierta.

## 5. Secuencia de ejecución

| Fase | Entregable verificable | Condición de salida |
|---|---|---|
| CASH-1 | permisos granulares, scope, límites, autorización y auditoría | matriz y tests backend verdes |
| CASH-2 | dominio Decimal/UUIDv7: register, drawer, terminal, shift, ledger, count, cuts, difference, handover | unit tests de invariantes verdes |
| CASH-3 | esquema born-clean, constraints, índices e idempotencia | bootstrap limpio + FK check |
| CASH-4 | repositorios y UnitOfWork | rollback integral y eventos post-commit |
| CASH-5..6 | configuración, cajas, cajones, terminales y hardware abstraído | CRUD/configuración sin SQL en UI |
| CASH-7..8 | apertura, turnos y ledger | saldo reconstruible e idempotente |
| CASH-9..10 | ventas y medios no monetarios | pagos mixtos cuadrados sin inflar efectivo |
| CASH-11..17 | movimientos, conteo, X/Z, diferencias, entregas y reembolsos | workflows y segregación cubiertos |
| CASH-18..20 | hardware, offline, notificaciones/WhatsApp | fallos desacoplados y deduplicados |
| CASH-21..22 | Tesorería, Finanzas y BI | fronteras y proyecciones canónicas |
| CASH-23..24 | UI/UX e impresión | vista nueva, design system y renderers |
| CASH-25 | eliminación total de legacy | cero consumidores y allowlist vacía |
| CASH-26 | validación final | suites, bootstrap y auditorías verdes |

No se avanzará de fase con fallos nuevos de la fase actual. Las infracciones existentes se congelarán mediante allowlist explícita y decreciente, nunca mediante exclusiones abiertas.

## 6. Archivos objetivo de las próximas fases

```text
backend/domain/cash_register/
backend/application/cash_register/
backend/infrastructure/db/repositories/cash_register/
backend/infrastructure/hardware/cash_drawer_gateway.py
backend/infrastructure/printers/cash_document_renderer.py
frontend/desktop/modules/cash_register/
migrations/standalone/<next>_cash_register_bounded_context_schema.py
tests/unit/cash_register/
tests/integration/cash_register/
tests/architecture/test_cash_register_*.py
docs/refactor/cash_register_legacy_inventory.md
docs/refactor/cash_register_schema_consolidation.md
```

Todas estas rutas estarán dentro del paquete real `pos_spj_v13.4/`.

## 7. Criterio para iniciar CASH-1

1. Ejecutar la línea base de tests de Caja indicada en este documento.
2. Registrar cualquier fallo preexistente sin alterar lógica para ocultarlo.
3. Crear primero tests del catálogo granular y del scope por sucursal.
4. Implementar permisos en backend; después adaptar navegación/UI.
5. Mantener intactos los cambios de Merma actualmente presentes en el worktree.

## 8. Estado CASH-0

- [x] Skills obligatorios leídos.
- [x] Caja, turnos, cortes y arqueos inventariados.
- [x] Pagos e integraciones inventariados.
- [x] Hardware, impresión, notificaciones y WhatsApp inventariados.
- [x] Permisos y navegación inventariados.
- [x] Esquema y rutas legacy clasificados preliminarmente.
- [x] Riesgos y tests de protección identificados.
- [ ] Línea base de tests ejecutada y verde. Bloqueada el 2026-08-03: el Python activo no tiene instalado `pytest` (`No module named pytest`).
- [ ] Autorización técnica para iniciar CASH-1.
