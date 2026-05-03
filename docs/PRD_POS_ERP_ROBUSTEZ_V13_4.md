# PRD — Robustecimiento POS/ERP SPJ v13.4

**Repositorio:** `jarralfa-max/pos_spj_v13.4`  
**Documento:** Product Requirements Document  
**Versión:** 1.0  
**Issue relacionado:** #116 — Roadmap de mejoras por fases: estabilidad, seguridad, arquitectura y UI/AX  
**Estado:** Draft inicial para implementación por fases

---

## 1. Resumen ejecutivo

El sistema POS/ERP SPJ v13.4 ya cuenta con módulos clave para operación comercial: ventas, inventario, producción/recetas, finanzas, CxC, CxP, proveedores, dashboards y eventos entre módulos. Sin embargo, para soportar operación real en punto de venta y administración tipo ERP, se requiere robustecer la consistencia transaccional, trazabilidad, seguridad, arquitectura de servicios, experiencia de usuario y pruebas de regresión.

Este PRD define los requerimientos funcionales y no funcionales para evolucionar el sistema hacia una base más segura, auditable y mantenible, priorizando primero los flujos críticos de dinero e inventario.

---

## 2. Problema a resolver

Actualmente existen riesgos operativos típicos de una aplicación que ha crecido rápido por módulos:

1. Operaciones financieras e inventario con riesgo de quedar parcialmente aplicadas.
2. Uso de excepciones silenciosas en zonas críticas.
3. Lógica de negocio distribuida entre UI, servicios y repositorios.
4. Eventos entre módulos que pueden refrescar de más o publicarse antes de confirmar cambios.
5. Trazabilidad insuficiente para reversas, ajustes, pagos y cambios sensibles.
6. Permisos no necesariamente centralizados en servicios.
7. Dashboards y KPIs que requieren mejor definición, corte y consistencia.
8. Necesidad de pruebas integrales para evitar regresiones.

---

## 3. Objetivos del producto

### 3.1 Objetivo principal

Convertir SPJ v13.4 en un POS/ERP más robusto, seguro y auditable, capaz de operar flujos críticos de ventas, inventario, producción y finanzas con consistencia transaccional y reglas de negocio centralizadas.

### 3.2 Objetivos específicos

- Garantizar atomicidad en pagos, cobros, ventas, reservas y ajustes de inventario.
- Implementar auditoría inmutable para operaciones críticas.
- Centralizar reglas de negocio en servicios.
- Implementar permisos por operación sensible.
- Estandarizar eventos entre módulos.
- Separar stock físico, reservado y disponible.
- Mejorar UX en operaciones de alto riesgo.
- Agregar pruebas automatizadas para flujos críticos.
- Preparar migraciones versionadas para releases seguros.

---

## 4. Alcance

### 4.1 Incluido

- Finanzas: CxC, CxP, pagos, cobros, cancelaciones, KPIs.
- Inventario: stock físico, reservado y disponible.
- Ventas: venta completada, venta suspendida, impacto en inventario y finanzas.
- Producción/recetas: validaciones, mermas, entradas y salidas de insumos.
- Seguridad: permisos por rol/usuario para operaciones sensibles.
- Auditoría: bitácora de movimientos críticos.
- Eventos: catálogo único, publicación post-commit y debounce en UI.
- UI/AX: confirmaciones contextuales, vista previa, validaciones inline.
- Calidad: pruebas unitarias e integrales.
- Migraciones: versionado de esquema.

### 4.2 Fuera de alcance inicial

- Migración a arquitectura web/cloud.
- Multi-tenant avanzado.
- Integraciones fiscales externas.
- Facturación electrónica.
- Sincronización offline-online entre sucursales.
- Motor contable completo con pólizas formales.

Estos puntos pueden definirse en PRDs posteriores.

---

## 5. Usuarios objetivo

| Usuario | Necesidad principal |
|---|---|
| Cajero | Registrar ventas, suspender ventas, cobrar, consultar productos y stock disponible. |
| Encargado | Supervisar caja, ajustar inventario, revisar CxC/CxP, autorizar acciones sensibles. |
| Administrador | Control financiero, reportes, proveedores, auditoría, permisos y configuración. |
| Operador de producción | Crear/usar recetas, registrar producción, mermas e insumos. |
| Dueño/gerente | Ver KPIs confiables, flujo de caja, saldos pendientes, rentabilidad e inventario. |

---

## 6. Principios de diseño

```text
UI no decide negocio.
UI sólo captura datos y muestra resultados.
Services validan negocio.
Repositories sólo leen/escriben.
Events sólo notifican después de commit.
Toda operación crítica debe ser auditable.
Toda operación sensible debe validar permisos en servicio.
```

---

## 7. Requerimientos funcionales

## RF-01 — Transacciones atómicas

### Descripción
El sistema debe ejecutar operaciones críticas dentro de transacciones atómicas para evitar saldos, stock o movimientos parcialmente actualizados.

### Flujos cubiertos
- Pago global CxP.
- Cobro global CxC.
- Cancelación/reversa de pago o cobro.
- Venta completada.
- Venta suspendida con reserva.
- Liberación de reserva.
- Producción.
- Ajuste de inventario.

### Criterios de aceptación
- Si una operación falla, todos los cambios relacionados se revierten.
- No debe quedar una aplicación de pago sin actualización de saldo.
- No debe quedar una reserva sin detalle.
- No debe publicarse evento si la transacción falla.
- Los servicios críticos no deben usar `except Exception: pass`.

---

## RF-02 — Folios únicos y trazables

### Descripción
Los folios de operaciones críticas deben evitar colisiones y permitir trazabilidad por operación, sucursal y tipo.

### Operaciones cubiertas
- CxC.
- CxP.
- Pagos.
- Cobros.
- Reservas.
- Ajustes.
- Producción.

### Criterios de aceptación
- Dos operaciones en el mismo segundo no deben generar el mismo folio.
- El folio debe permitir identificar tipo de operación.
- El folio debe guardarse en auditoría y eventos relacionados.

---

## RF-03 — Auditoría inmutable

### Descripción
El sistema debe registrar una bitácora de operaciones críticas con valores antes/después, usuario, fecha y correlación de operación.

### Tabla sugerida

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    action TEXT NOT NULL,
    before_json TEXT DEFAULT '{}',
    after_json TEXT DEFAULT '{}',
    usuario_id TEXT DEFAULT '',
    correlation_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Operaciones auditables
- Crear CxC/CxP.
- Aplicar pago/cobro.
- Cancelar pago/cobro.
- Ajustar inventario.
- Reservar/liberar stock.
- Crear/editar receta.
- Cambiar precio/costo.
- Cambiar límite de crédito.
- Cambiar permisos/roles.

### Criterios de aceptación
Cada operación crítica debe responder:

- Quién lo hizo.
- Cuándo lo hizo.
- Qué entidad afectó.
- Qué cambió.
- Valor anterior.
- Valor nuevo.
- Operación origen.

---

## RF-04 — Servicios de negocio centralizados

### Descripción
La lógica de negocio debe residir en servicios, no en pantallas PyQt.

### Servicios requeridos

```text
services/
  finance_service.py
  credit_service.py
  inventory_service.py
  stock_reservation_service.py
  recipe_service.py
  audit_service.py
  permission_service.py
```

### Criterios de aceptación
- La UI no consulta directamente saldos para decidir si una CxC se puede crear.
- La validación de crédito vive en `CreditService`.
- La creación de CxC/CxP vive en `FinanceService`.
- Los ajustes de inventario viven en `InventoryService`.
- Las recetas y producción viven en `RecipeService`.
- Las reglas aplican igual desde UI, scripts o futuros procesos automáticos.

---

## RF-05 — Control de crédito de clientes

### Descripción
El sistema debe validar límite de crédito contra saldo real pendiente del cliente.

### Reglas
- El saldo usado para validar crédito debe calcularse desde CxC pendientes/parciales.
- Si el cliente no tiene límite configurado, la operación debe bloquearse o requerir permiso especial.
- Si el nuevo monto excede el disponible, la operación debe bloquearse.

### Consulta base sugerida

```sql
SELECT COALESCE(SUM(balance), 0)
FROM accounts_receivable
WHERE cliente_id = ?
  AND status IN ('pendiente', 'parcial');
```

### Criterios de aceptación
- Crear CxC con crédito disponible debe permitirse.
- Crear CxC excediendo crédito debe bloquearse.
- El mensaje debe mostrar saldo actual, límite y disponible.
- Un usuario con permiso especial puede autorizar excepción si se define esa regla.

---

## RF-06 — Pagos y cobros globales

### Descripción
El sistema debe permitir aplicar pagos/cobros globales a múltiples documentos pendientes, priorizando por vencimiento.

### Reglas
- CxP se aplica a documentos del proveedor.
- CxC se aplica a documentos del cliente.
- El orden de aplicación debe ser por vencimiento ascendente.
- Si sobra monto, debe registrarse como saldo a favor/anticipo auditable.
- Debe existir vista previa antes de confirmar.

### Criterios de aceptación
- El usuario ve documentos afectados antes de confirmar.
- La aplicación se hace en una sola transacción.
- Se registra detalle por documento.
- Se actualiza status correctamente: `pendiente`, `parcial` o `pagado`.
- La cancelación revierte saldos y status correctamente.

---

## RF-07 — Inventario físico, reservado y disponible

### Descripción
El sistema debe separar stock físico, stock reservado y stock disponible.

### Definiciones

```text
stock_disponible = stock_fisico - stock_reservado
```

### Reglas
- Venta suspendida reserva stock disponible.
- Cancelar venta suspendida libera reserva.
- Completar venta suspendida convierte reserva en salida real.
- Ajustes afectan stock físico.
- Producción consume insumos y genera producto terminado.
- Merma se registra como salida auditable.

### Criterios de aceptación
- No se puede reservar más del disponible.
- Reservas simultáneas no deben sobrerreservar.
- La UI debe mostrar físico, reservado y disponible.
- Los reportes deben usar disponible cuando aplique.

---

## RF-08 — Producción y recetas

### Descripción
El sistema debe validar recetas y producción de forma consistente con inventario.

### Reglas
- Una receta puede requerir suma exacta de 100% o modo flexible definido por configuración.
- La producción debe registrar salida de insumos.
- La producción debe registrar entrada de producto terminado.
- La merma debe quedar clasificada y auditada.

### Criterios de aceptación
- Recetas inválidas se bloquean con mensaje claro.
- Producción sin insumos suficientes se bloquea.
- Producción completada actualiza inventario y auditoría.
- Cambios en receta generan evento y bitácora.

---

## RF-09 — Permisos por operación

### Descripción
El sistema debe validar permisos dentro de servicios para operaciones sensibles.

### Matriz inicial

| Permiso | Admin | Encargado | Cajero |
|---|---:|---:|---:|
| `venta.crear` | Sí | Sí | Sí |
| `venta.cancelar` | Sí | Sí | No |
| `finanzas.crear_cxc` | Sí | Sí | No |
| `finanzas.cancelar_pago` | Sí | No | No |
| `inventario.ajustar` | Sí | Sí | No |
| `recetas.editar` | Sí | Sí | No |
| `clientes.cambiar_limite_credito` | Sí | No | No |
| `reportes.ver_finanzas` | Sí | Sí | No |

### Criterios de aceptación
- Un usuario sin permiso no puede ejecutar la acción aunque acceda al método por otra pantalla.
- La UI debe ocultar o deshabilitar botones no permitidos.
- El servicio debe bloquear la operación aunque la UI falle.
- Intentos denegados deben auditarse si son sensibles.

---

## RF-10 — Eventos entre módulos

### Descripción
El sistema debe contar con un catálogo único de eventos y publicar eventos sólo después del commit exitoso.

### Eventos base

```python
VENTA_COMPLETADA = "VENTA_COMPLETADA"
MOVIMIENTO_FINANCIERO = "MOVIMIENTO_FINANCIERO"
CXP_CREADA = "CXP_CREADA"
CXC_CREADA = "CXC_CREADA"
AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"
STOCK_RESERVADO = "STOCK_RESERVADO"
STOCK_LIBERADO = "STOCK_LIBERADO"
RECETA_ACTUALIZADA = "RECETA_ACTUALIZADA"
```

### Criterios de aceptación
- No deben existir strings sueltos para eventos en módulos.
- Todo evento crítico incluye `correlation_id`.
- Los dashboards no deben refrescar múltiples veces por la misma operación.
- Debe existir debounce para refrescos de UI.

---

## RF-11 — Dashboard financiero tipo ERP

### Descripción
El dashboard financiero debe mostrar KPIs confiables con periodo, sucursal y corte de actualización.

### KPIs mínimos
- Flujo de caja neto.
- CxC pendiente.
- CxP pendiente.
- CxC vencida.
- CxP vencida.
- Margen bruto.
- Margen operativo.
- Liquidez.
- Ticket promedio.
- Días cartera.
- Días proveedores.

### UI mínima
- Sucursal.
- Periodo.
- Última actualización.
- Tooltip/definición por KPI.
- Estado de carga/error.

### Criterios de aceptación
- Los KPIs deben cuadrar con consultas base.
- El usuario debe entender qué periodo está viendo.
- Los KPIs deben refrescarse por evento o acción manual, no de forma excesiva.

---

## RF-12 — UI/AX para operaciones críticas

### Descripción
Las pantallas deben reducir errores humanos mediante confirmaciones, vistas previas y validaciones inline.

### Requerimientos
- Vista previa antes de pago/cobro global.
- Selector robusto de cliente/proveedor.
- Confirmación contextual para cancelaciones.
- Mensajes claros de validación.
- Mostrar saldo, límite y disponible al crear CxC.
- Mostrar físico, reservado y disponible al vender/reservar.

### Ejemplo de confirmación

```text
Cobro global a cliente: Juan Pérez
Monto recibido: $5,000.00

Se aplicará a:
1. CXC-001 | Vence 2026-04-10 | Saldo $1,200 | Aplica $1,200
2. CXC-002 | Vence 2026-04-15 | Saldo $2,000 | Aplica $2,000
3. CXC-003 | Vence 2026-04-20 | Saldo $3,500 | Aplica $1,800

Total aplicado: $5,000
Saldo a favor: $0
```

---

## RF-13 — Migraciones versionadas

### Descripción
El sistema debe actualizar esquema de base de datos mediante migraciones versionadas y seguras.

### Requerimientos
- Crear carpeta `migrations/`.
- Crear tabla `schema_migrations`.
- Ejecutar migraciones idempotentes.
- Hacer backup antes de migrar.
- Validar saldos y stock después de migrar.

### Tabla sugerida

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
```

---

## 8. Requerimientos no funcionales

## RNF-01 — Consistencia

- Las operaciones críticas deben ser ACID dentro de las capacidades de SQLite.
- Se debe usar `BEGIN IMMEDIATE` cuando haya riesgo de concurrencia en stock.
- No deben existir commits parciales dentro de una operación superior.

## RNF-02 — Seguridad

- Los permisos deben validarse en servicios.
- Acciones sensibles deben auditarse.
- No se deben guardar secretos en el repositorio.
- No se deben exponer trazas técnicas completas al usuario final.

## RNF-03 — Observabilidad

- Errores críticos deben registrarse con `logger.exception`.
- Operaciones relevantes deben tener `correlation_id`.
- Debe poder reconstruirse una operación desde auditoría y eventos.

## RNF-04 — Mantenibilidad

- UI, servicios y repositorios deben tener responsabilidades separadas.
- Los nombres de eventos deben centralizarse.
- Las reglas críticas deben tener tests.
- Las migraciones deben ser versionadas.

## RNF-05 — Usabilidad

- Formularios críticos deben tener validación clara.
- Acciones destructivas o reversas deben pedir confirmación.
- Dashboards deben evitar saturación visual.
- KPIs deben explicar periodo y definición.

## RNF-06 — Performance

- Dashboards deben usar debounce o refresco manual.
- Consultas frecuentes deben tener índices.
- El sistema no debe recalcular KPIs pesados ante cada evento si no está visible la pantalla.

---

## 9. Roadmap de releases

## Release 1 — Estabilización crítica

### Objetivo
Blindar operaciones de dinero e inventario.

### Incluye
- Transacciones atómicas.
- Eliminación de `except/pass` en servicios críticos.
- Folios únicos.
- Status correcto en cancelación de pagos/cobros.
- Eventos post-commit.

### Éxito
- No quedan saldos parcialmente aplicados.
- No hay eventos de operaciones fallidas.
- Los tests críticos de pagos/cobros pasan.

---

## Release 2 — Auditoría y permisos

### Objetivo
Dar trazabilidad y control de acceso a operaciones sensibles.

### Incluye
- `audit_log`.
- `AuditService`.
- `PermissionService`.
- Matriz inicial de roles/permisos.
- Auditoría de acciones sensibles.

### Éxito
- Toda acción crítica tiene rastro.
- Un usuario sin permiso no puede ejecutar acciones sensibles.

---

## Release 3 — Arquitectura de servicios

### Objetivo
Centralizar reglas de negocio fuera de UI.

### Incluye
- `FinanceService`.
- `CreditService`.
- `InventoryService`.
- `RecipeService`.
- Refactor de pantallas para consumir servicios.

### Éxito
- La UI no decide reglas críticas.
- Tests pueden invocar servicios sin UI.

---

## Release 4 — Inventario y producción robustos

### Objetivo
Garantizar consistencia de stock físico, reservado y disponible.

### Incluye
- Vista de stock disponible.
- Reservas con concurrencia controlada.
- Producción con consumo/entrada auditable.
- Merma auditable.

### Éxito
- No hay sobrerreserva.
- Producción impacta inventario correctamente.

---

## Release 5 — UI/AX y dashboard ERP

### Objetivo
Mejorar experiencia y control operativo.

### Incluye
- Vista previa de pagos/cobros globales.
- Selector robusto cliente/proveedor.
- Dashboard financiero con periodo, sucursal y corte.
- Tooltips y estados de carga/error.

### Éxito
- Usuarios pueden entender y confirmar operaciones críticas antes de ejecutarlas.
- KPIs tienen definición y corte claro.

---

## Release 6 — Calidad y migraciones

### Objetivo
Preparar release productivo confiable.

### Incluye
- Migraciones versionadas.
- Backup pre-migración.
- Tests de regresión.
- Validación post-migración.

### Éxito
- Una base existente puede actualizarse sin pérdida de datos.
- Tests de regresión pasan antes de release.

---

## 10. Métricas de éxito

| Métrica | Meta |
|---|---:|
| Operaciones críticas con transacción | 100% |
| Acciones sensibles auditadas | 100% |
| Acciones sensibles con permiso en servicio | 100% |
| `except/pass` en servicios críticos | 0 |
| Eventos críticos post-commit | 100% |
| Tests de flujos críticos | >= 80% de cobertura funcional inicial |
| Sobrerreservas detectadas en pruebas | 0 |
| Folios duplicados en pruebas concurrentes | 0 |

---

## 11. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Romper flujos existentes al refactorizar | Alto | Tests de regresión y releases pequeños |
| Esquemas de DB inconsistentes | Alto | Migraciones versionadas e idempotentes |
| UI acoplada a lógica actual | Medio/Alto | Refactor progresivo por servicio |
| Eventos duplicados | Medio | Catálogo único y debounce |
| Bloqueos SQLite por concurrencia | Medio | `BEGIN IMMEDIATE`, transacciones cortas e índices |
| Falta de permisos claros | Alto | Matriz mínima y validación en servicios |

---

## 12. Dependencias técnicas

- PyQt para UI.
- SQLite como motor de datos local.
- Event bus interno.
- Servicios/repositories existentes.
- Módulos de finanzas, inventario, ventas y producción.
- Tests existentes en `tests/`.

---

## 13. Checklist de aceptación global

- [ ] Los pagos/cobros globales son atómicos.
- [ ] Las cancelaciones restauran saldos y status correctamente.
- [ ] Inventario distingue físico/reservado/disponible.
- [ ] No existe sobrerreserva en pruebas.
- [ ] Las acciones sensibles validan permisos en servicio.
- [ ] Toda operación crítica queda en `audit_log`.
- [ ] Eventos críticos se publican sólo después de commit.
- [ ] UI muestra vista previa en operaciones de alto riesgo.
- [ ] Dashboard financiero muestra periodo, sucursal y última actualización.
- [ ] Migraciones son versionadas.
- [ ] Tests críticos pasan antes de release.

---

## 14. Issues derivados sugeridos

- Epic: Release 1 — Estabilización crítica.
- Epic: Release 2 — Auditoría y permisos.
- Epic: Release 3 — Arquitectura de servicios.
- Epic: Release 4 — Inventario y producción robustos.
- Epic: Release 5 — UI/AX y dashboard ERP.
- Epic: Release 6 — Calidad y migraciones.

---

## 15. Notas de implementación

1. Evitar hacer todos los cambios en un único PR grande.
2. Priorizar flujos de dinero e inventario antes de rediseñar UI.
3. Cada release debe incluir tests mínimos.
4. Cada migración debe ser reversible mediante backup.
5. Cada nuevo servicio debe tener pruebas directas sin depender de UI.

---

## 16. Glosario

| Término | Definición |
|---|---|
| CxC | Cuentas por cobrar. |
| CxP | Cuentas por pagar. |
| Stock físico | Cantidad real registrada en inventario. |
| Stock reservado | Cantidad comprometida por ventas suspendidas u operaciones pendientes. |
| Stock disponible | Stock físico menos stock reservado. |
| Correlation ID | Identificador para agrupar eventos, auditoría y cambios de una misma operación. |
| Post-commit event | Evento publicado después de confirmar transacción. |
| Reversa | Operación que cancela o compensa una operación previa sin borrar historial. |
