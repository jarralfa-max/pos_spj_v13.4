# Auditoría Real — Módulo Caja (pos_spj v13.4)
**Fecha:** 2026-05-19  
**Auditor:** Claude Code — ERP Architect

---

## 1. Mapa de Archivos

| Archivo | Líneas | Rol |
|---------|--------|-----|
| `modulos/caja.py` | 1,188 | UI PyQt5 — contiene SQL directo (VIOLACIÓN) |
| `repositories/caja.py` | 290 | CajaRepository — enterprise, dual-write |
| `core/services/enterprise/finance_service.py` | 1,600+ | FinanceService — métodos caja en líneas 1113-1266 |
| `core/services/cierre_caja_service.py` | 278 | CierreCajaService — servicio legacy v9 (DUPLICADO) |
| `core/app_container.py` | 965 | AppContainer — NO registra CajaRepository ni CajaApplicationService |
| `migrations/m000_base_schema.py` | 3,100+ | Esquema base — define 6 tablas de caja |

---

## 2. Flujo Actual — Abrir Turno

```
UI.abrir_caja()
  → QInputDialog.getDouble() → fondo
  → container.finance_service.abrir_turno(sucursal_id, usuario, fondo)
      → SELECT id FROM turnos_caja WHERE cajero=? AND estado='abierto'
      → INSERT INTO turnos_caja (sucursal_id, cajero, fondo_inicial, estado, fecha_apertura)
      → db.commit()
  → Toast.success()
  → hardware_service.open_cash_drawer()
  → verificar_estado_caja()
```

**Problemas:**
- No publica evento de dominio CAJA_TURNO_ABIERTO
- No valida sucursal existente
- No registra en turno_actual (tabla de CierreCajaService)
- Sin transacción atómica

---

## 3. Flujo Actual — Registrar Movimiento

```
UI.registrar_movimiento()
  → lee cmb_tipo_movimiento, txt_monto_mov, txt_concepto
  → container.finance_service.registrar_movimiento_manual(turno_id, sucursal_id, usuario, tipo, monto, concepto)
      → INSERT INTO movimientos_caja (turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
      → db.commit()
  → _cargar_movimientos_turno()  ← SQL directo en UI
```

**Problemas:**
- No publica evento
- No valida que turno esté abierto antes de insertar
- _cargar_movimientos_turno usa self.container.db.execute() directamente

---

## 4. Flujo Actual — Corte Z

```
UI.cerrar_caja()
  → DialogoCorteZCiego.exec_()
      → _ejecutar_corte()
          → container.finance_service.generar_corte_z(turno_id, sucursal_id, cajero, efectivo)
              [1] SUM(total) FROM ventas WHERE sucursal_id=? AND usuario=?  ← TODOS los pagos
              [2] SUM(INGRESO) - SUM(RETIRO) FROM movimientos_caja
              [3] fondo_inicial FROM turnos_caja
              [4] esperado = fondo + total_ventas + ingresos - retiros  ← BUG: suma tarjeta/transferencia
              [5] UPDATE turnos_caja SET estado='cerrado'...
              [6] NO inserta en cierres_caja  ← BUG CRÍTICO
              [7] NO publica eventos  ← BUG
              [8] NO usa transacción  ← BUG
              [9] NO registra asiento si diferencia  ← BUG
          → nav.indexOf(...)  ← BUG: nav fuera de scope
  → imprimir_ticket_corte(resultado)
  → verificar_estado_caja()
```

**Bugs críticos:**
1. `total_ventas` incluye tarjeta y transferencia → efectivo esperado incorrecto
2. No inserta en `cierres_caja` → historial siempre vacío
3. Variable `nav` fuera de scope → crash en línea 298
4. Sin transacción → inconsistencia si falla a mitad
5. No publica eventos de dominio

---

## 5. Tablas Usadas

| Tabla | Propósito | Estado |
|-------|-----------|--------|
| `turnos_caja` | Turnos de cajero (fuente principal) | ✅ Activa |
| `movimientos_caja` | Movimientos manuales + ventas | ✅ Activa (legacy) |
| `caja_operations` | Operaciones enterprise con idempotency | ✅ Activa (nueva) |
| `cierres_caja` | Historial de cortes Z/X | ⚠️ No se llena desde flujo principal |
| `turno_actual` | Estado abierto por sucursal (CierreCajaService) | ⚠️ No se usa en flujo principal |
| `cajas` | Registro de cajas físicas | ⚠️ No integrada al flujo actual |

---

## 6. Servicios Duplicados

| Funcionalidad | finance_service | cierre_caja_service | Ganador |
|---------------|----------------|---------------------|---------|
| abrir turno | `abrir_turno()` | `abrir_turno()` | finance_service |
| corte Z | `generar_corte_z()` | `corte_z()` | **cierre_caja_service** (más completo) |
| historial | — | `get_historial()` | cierre_caja_service |
| movimiento manual | `registrar_movimiento_manual()` | — | finance_service |
| estado turno | `get_estado_turno()` | `turno_activo()` | finance_service |

**Decisión:** Consolidar en `CajaApplicationService` como fuente única de verdad.

---

## 7. SQL Directo en UI (VIOLACIONES)

| Línea | Tabla | Descripción |
|-------|-------|-------------|
| 365 | `turnos_caja` | KPI bar: fondo + ventas |
| 373 | `movimientos_caja` | KPI bar: conteo movimientos |
| 378 | `cortes_z` | KPI bar: cortes hoy (tabla inexistente!) |
| 931-937 | `movimientos_caja` | Cargar movimientos del turno |
| 977 | `turnos_caja` | Obtener fondo_inicial |
| 1036-1042 | `cierres_caja` | Historial de cortes |
| 1064 | `cierres_caja` | Reimprimir corte |
| 1169 | `turno_actual` | Calcular arqueo (tabla no mantenida) |

---

## 8. Eventos Existentes y Faltantes

### Existentes:
- `CAJA_MOVIMIENTO` — publicado por CajaRepository.registrar_movimiento()

### Faltantes (a crear):
- `CAJA_TURNO_ABIERTO` — al abrir turno
- `CAJA_TURNO_CERRADO` — al cerrar turno
- `CAJA_CORTE_Z_GENERADO` — al ejecutar corte Z
- `CAJA_DIFERENCIA_DETECTADA` — si diferencia != 0

---

## 9. Código Muerto / Bugs

| Tipo | Ubicación | Descripción |
|------|-----------|-------------|
| Dead code | `_crear_caja_kpi_bar` líneas 398-403 | Código inalcanzable después de `return bar` |
| Bug scope | `_ejecutar_corte` línea 298 | `nav` no definido en este scope → NameError |
| Bug objectName | `_build_tab_arqueo` línea 1132-1133 | Double setObjectName: el segundo sobrescribe el primero, rompiendo findChild |
| Bug KPI | Línea 378 | Consulta tabla `cortes_z` que no existe (debería ser `cierres_caja`) |
| Bug cálculo | `generar_corte_z` línea 1186 | Suma todas las formas de pago en esperado (no solo efectivo) |
| Sin transacción | `generar_corte_z` completo | No usa SAVEPOINT, puede dejar estado inconsistente |
| Sin cierres | `generar_corte_z` completo | No inserta en `cierres_caja` → historial vacío |

---

## 10. Riesgos de Datos

| Riesgo | Severidad | Descripción |
|--------|-----------|-------------|
| Cálculo incorrecto de efectivo esperado | 🔴 CRÍTICO | Suma tarjeta/transferencia → diferencia incorrecta → desconfianza en cortes |
| Historial vacío | 🔴 CRÍTICO | No se insertan registros en cierres_caja → imposible auditar cierres pasados |
| Race condition en corte Z | 🟡 MEDIO | Sin SAVEPOINT dos cajeros pueden cerrar simultáneamente |
| turno_actual desincronizado | 🟡 MEDIO | CierreCajaService y finance_service usan tablas diferentes |
| Arqueo con datos falsos | 🟡 MEDIO | `_calcular_arqueo` lee de turno_actual que no se actualiza en el flujo principal |
| Tabla cortes_z inexistente | 🟠 ALTO | KPI bar hace SELECT en tabla que no existe → silenciado por except |

---

## 11. Fuente Única de Verdad (Fase 2)

**Ruta canónica establecida:**
```
UI (modulos/caja.py)
  → container.caja_service (CajaApplicationService)
      → CajaRepository (repositories/caja.py) para operaciones enterprise
      → finance_service.registrar_asiento() para asientos contables
      → event_bus.publish() para eventos de dominio
      → DB: turnos_caja (master), movimientos_caja (log), cierres_caja (historial)
```

**Integración en AppContainer:**
```python
from repositories.caja import CajaRepository
from application.services.caja_application_service import CajaApplicationService

self.caja_repo = CajaRepository(self.db)
self.caja_service = CajaApplicationService(
    db=self.db,
    caja_repo=self.caja_repo,
    finance_service=self.finance_service,
)
```

---

## 12. Archivos Modificados en Refactor

1. `core/events/event_bus.py` — agregar constantes CAJA_*
2. `application/services/caja_application_service.py` — NUEVO
3. `core/app_container.py` — registrar caja_repo y caja_service
4. `modulos/caja.py` — eliminar SQL, corregir bugs
5. `core/services/enterprise/finance_service.py` — corregir generar_corte_z
6. `core/services/caja_ticket_service.py` — NUEVO, extrae lógica de impresión
7. `tests/test_caja.py` — NUEVO, tests de regresión
