# 🚨 REPORTE DE BUGS ADICIONALES Y ACTUALIZACIÓN PLAN MAESTRO
## POS/ERP SPJ v13.4 - Auditoría Complementaria

**Fecha:** 2025
**Auditor:** Arquitectura Senior de Software
**Estado:** Bugs Críticos Confirmados

---

## 📋 ÍNDICE DE BUGS REPORTADOS POR USUARIO

| # | Bug Reportado | Severidad | Estado | Módulo Afectado |
|---|--------------|-----------|--------|-----------------|
| 1 | `NameError: QSpinBox not defined` | 🔴 CRÍTICO | Confirmado | Ventas (DialogoPago) |
| 2 | Báscula no respeta configuración hardware | 🟠 ALTO | Confirmado | Ventas/Hardware |
| 3 | Recetas se guardan pero no se muestran | 🟠 ALTO | Por investigar | Recetas |
| 4 | Producción cárnica y recetas duplicados | 🟡 MEDIO | Confirmado | Producción |
| 5 | Planeación de compras no integrada | 🟠 ALTO | Confirmado | Compras |
| 6 | Error en módulo Finanzas | 🔴 CRÍTICO | Por investigar | Finanzas |
| 7 | Módulos BI y Decisiones repetidos | 🟡 MEDIO | Confirmado | BI/Decisiones |

---

## 🔍 ANÁLISIS DETALLADO DE CADA BUG

### **BUG #1: NameError - QSpinBox no definido en DialogoPago**

**Ubicación:** `/workspace/pos_spj_v13.4/modulos/ventas.py`

**Evidencia:**
```python
# Línea 27-29: Importaciones actuales
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QHBoxLayout,
    QFrame, QTableWidget, QTableWidgetItem, QSplitter,
    QGroupBox, QSizePolicy, QAction, QGridLayout,
    QAbstractItemView, QDialog, QCheckBox, QFormLayout, QDoubleSpinBox,  # ❌ FALTA QSpinBox
    QHeaderView, QRadioButton, QScrollArea, QListWidget, QListWidgetItem,
    QInputDialog, QGraphicsDropShadowEffect, QDialogButtonBox, QCompleter
)

# Línea 357: Uso de QSpinBox sin importar
self._spin_puntos = QSpinBox()  # 💥 NameError: name 'QSpinBox' is not defined
```

**Impacto:**
- El sistema colapsa al intentar procesar un pago con puntos de lealtad
- Imposible completar ventas con canje de puntos del programa de fidelidad
- Afecta todas las ventas desde la implementación de loyalty v13.4

**Causa Raíz:**
- Se agregó `QDoubleSpinBox` a las importaciones pero no `QSpinBox`
- El widget `QSpinBox` es necesario para el contador de puntos enteros
- Testing insuficiente en flujo de pagos con lealtad

**Solución Inmediata:**
```python
# Agregar QSpinBox a la línea 29 de importaciones
from PyQt5.QtWidgets import (
    # ... resto de imports ...
    QAbstractItemView, QDialog, QCheckBox, QFormLayout, QDoubleSpinBox, QSpinBox,
    # ... resto de imports ...
)
```

---

### **BUG #2: Báscula ignora configuración de hardware**

**Ubicación:** `/workspace/pos_spj_v13.4/modulos/ventas.py`

**Comportamiento Actual:**
```python
# Línea 2188-2196: inicializar_bascula()
def inicializar_bascula(self):
    self.bascula_conectada = False
    # ✅ Verifica si está habilitada
    if not self._hw_bascula_habilitada:
        if hasattr(self, 'lbl_estado_bascula'):
            self.lbl_estado_bascula.setText("Báscula: ⚪ Desactivada")
        return
    
    # ❌ PERO en otros métodos NO verifica antes de conectar
```

**Problemas Identificados:**

1. **`inicializar_bascula()`** - ✅ Correcto (verifica configuración)
2. **`leer_peso()`** - ⚠️ Parcial (tiene fallback que ignora config)
3. **`iniciar_monitoreo_peso()`** - ✅ Correcto (verifica configuración)
4. **Flujo de entrada manual** - ❌ NO EXISTE

**Requerimiento del Usuario:**
> "Si la báscula no está activa en configuración, debería permitir ingresar peso manualmente"

**Estado Actual:**
- No hay campo UI para capturar peso manualmente cuando báscula está desactivada
- Productos por peso quedan bloqueados sin báscula conectada
- Pérdida de ventas en sucursales sin hardware de báscula

**Solución Propuesta:**
```python
# 1. Agregar input manual en UI (línea ~1105)
self.txt_peso_manual = QDoubleSpinBox()
self.txt_peso_manual.setRange(0.001, 9999.0)
self.txt_peso_manual.setDecimals(3)
self.txt_peso_manual.setSuffix(" kg")
self.txt_peso_manual.setVisible(not self._hw_bascula_habilitada)

# 2. Modificar agregar_producto_directo para usar peso manual si aplica
def agregar_producto_directo(self, producto, peso=None):
    if peso is None and hasattr(self, 'txt_peso_manual'):
        peso = self.txt_peso_manual.value()
    # ... continuar lógica normal
```

---

### **BUG #3: Recetas se guardan pero no se muestran en tabla**

**Ubicación:** `/workspace/pos_spj_v13.4/modulos/recetas.py`

**Síntomas Reportados:**
- El formulario de guardado ejecuta sin errores
- La receta existe en base de datos (verificable vía SQL)
- La tabla/grid UI permanece vacía después de guardar
- Requiere cerrar y reabrir módulo para ver recetas

**Posibles Causas (Por Investigar):**

1. **Falta de refresh post-guardado:**
```python
# Posiblemente falta llamar a método de carga después de guardar
def guardar_receta(self):
    self.repo.guardar(receta_data)
    # ❌ Falta: self.cargar_recetas() o self.refresh_ui()
```

2. **Filtro incorrecto en consulta:**
```python
# Quizás filtra por estado activo incorrectly
recetas = self.repo.get_all(include_inactive=False)  # ¿Todas están inactive?
```

3. **Error silencioso en carga de tabla:**
```python
def cargar_recetas(self):
    try:
        # ... carga datos ...
    except Exception:
        pass  # ❌ Silencia error de carga
```

**Plan de Investigación:**
1. Revisar método `guardar_receta()` en `modulos/recetas.py`
2. Verificar si hay llamada a refresh después de guardar
3. Checar logs de errores en consola
4. Validar query de selección de recetas

---

### **BUG #4: Producción Cárnica y Recetas - Módulos Duplicados**

**Ubicaciones:**
- `/workspace/pos_spj_v13.4/modulos/recetas.py` (1800+ líneas estimadas)
- `/workspace/pos_spj_v13.4/modulos/produccion.py` (47KB)
- `/workspace/pos_spj_v13.4/modulos/produccion_carnica.py` (5KB)

**Análisis de Superposición:**

| Funcionalidad | recetas.py | produccion.py | produccion_carnica.py |
|--------------|------------|---------------|----------------------|
| Crear receta | ✅ | ❓ | ❌ |
| Editar receta | ✅ | ❓ | ❌ |
| Mostrar recetas | ✅ (tabla) | ❓ | ❌ (solo combo) |
| Ejecutar producción | ✅ | ❓ | ✅ |
| Despiece cárnico | ❌ | ❓ | ✅ |
| Gestión de mermas | ✅ | ❓ | ✅ |
| Trazabilidad lotes | ✅ | ❓ | ❌ |

**Problema:**
- `produccion_carnica.py` es un subconjunto mínimo de funcionalidad
- Solo tiene UI básica con ComboBox que llama a `recipe_engine`
- No agrega valor sobre el módulo principal de recetas
- Confunde usuarios: ¿dónde deben producir?

**Recomendación:**
```
OPCIÓN A (Recomendada): Fusionar
├─ Mover botón "Ejecutar Producción" dentro de recetas.py
├─ Eliminar produccion_carnica.py
└─ produccion.py absorbe lógica restante

OPCIÓN B (Alternativa): Especializar
├─ recetas.py → Solo diseño/gestión de recetas
├─ produccion.py → Producción general (ensambles, kits)
└─ produccion_carnica.py → Producción especializada (despiece, merma)
```

---

### **BUG #5: Planeación de Compras No Integrada**

**Ubicación:** `/workspace/pos_spj_v13.4/modulos/planeacion_compras.py`

**Estado Actual:**
```python
class ModuloPlaneacionCompras(QWidget):
    """
    Dashboard Predictivo de Inteligencia Comercial.
    Utiliza el ForecastService para proyectar la demanda futura.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.sucursal_id = 1
        self.init_ui()  # ❌ No hay integración real con módulos de compras
```

**Problemas Identificados:**

1. **Aislamiento del flujo de compras:**
   - No genera órdenes de compra automáticamente
   - No se integra con `compras_pro.py`
   - No actualiza inventarios proyectados

2. **Datos desconectados:**
   - Predicciones ML no alimentan reorder points
   - Sugerencias no crean solicitudes de compra
   - No hay trazabilidad: predicción → compra → recepción

3. **UI desconectada:**
   - Gráficos matplotlib aislados
   - Botones sin acción documentada
   - Sin exportación a módulo de proveedores

**Requerimiento:**
> "Planeacion de compras no esta integrado"

**Solución Requerida:**
```python
# Integración necesaria:
1. ForecastService → genera sugerencias de compra
2. Sugerencias → crean borrador de orden en compras_pro.py
3. Orden borrador → notifica a proveedor vía whatsapp_module.py
4. Recepción → actualiza inventario y cierra ciclo
```

---

### **BUG #6: Error en Módulo Finanzas**

**Ubicación:** `/workspace/pos_spj_v13.4/modulos/finanzas.py`

**Reporte del Usuario:**
> "En finanzas hay un error"

**Hallazgos Preliminares:**
El archivo tiene 1480+ líneas con múltiples puntos de fallo potenciales:

```python
# Múltiples logger.error sin manejo visible al usuario
logger.error("tab[%d]: %s", idx, exc)           # Línea 784
logger.error("dashboard_kpis: %s", exc)         # Línea 825
logger.error("balance_general: %s", exc)        # Línea 851
logger.error("flujo_caja: %s", exc)             # Línea 876
# ... 20+ errores logueados pero no mostrados
```

**Áreas Críticas a Revisar:**
1. Conciliación bancaria automática
2. Generación de asientos contables
3. Cálculo de impuestos (IVA, ISR)
4. Reportes SAT (balanza de comprobación)
5. Conciliación ventas-contabilidad

**Acción Requerida:**
- Solicitar al usuario traceback específico del error
- Revisar logs de aplicación en momento del fallo
- Ejecutar tests de integración financiera

---

### **BUG #7: Módulos BI y Decisiones Repetidos**

**Archivos Involucrados:**
- `/workspace/pos_spj_v13.4/modulos/reportes_bi_v2.py` (UI de BI)
- `/workspace/pos_spj_v13.4/core/services/bi_service.py` (Servicio BI)
- `/workspace/pos_spj_v13.4/core/services/decision_engine.py` (Motor Decisiones)
- `/workspace/pos_spj_v13.4/repositories/bi_repository.py` (Repo BI)

**Análisis de Solapamiento:**

| Característica | BIService | DecisionEngine | ¿Duplicado? |
|---------------|-----------|----------------|-------------|
| Análisis de ventas | ✅ | ✅ | ⚠️ Parcial |
| Proyecciones | ✅ | ✅ | ⚠️ Parcial |
| Sugerencias accionables | ❌ | ✅ | ✅ Diferente |
| KPIs dashboard | ✅ | ❌ | ✅ Diferente |
| Alertas proactivas | ❌ | ✅ | ✅ Diferente |

**Veredicto:**
- **NO son módulos duplicados** — tienen responsabilidades distintas
- **PERO** la UI puede causar confusión:
  - `reportes_bi_v2.py` muestra históricos y KPIs
  - No hay UI clara para `decision_engine` (solo sugerencias en segundo plano)

**Recomendación:**
```
1. Renombrar para claridad:
   - "Inteligencia de Negocios (BI)" → Históricos, KPIs, Dashboards
   - "Asistente de Decisiones" → Sugerencias accionables, alertas

2. Unificar UI en un solo módulo con pestañas:
   - Tab 1: Dashboards BI (gráficos, métricas)
   - Tab 2: Sugerencias Activas (del DecisionEngine)
   - Tab 3: Historial de Decisiones Tomadas

3. Eliminar confusión de nombres en menús
```

---

## 🎯 PLAN DE ACCIÓN INMEDIATO

### **FASE 0: HOTFIX CRÍTICO (24-48 horas)**

#### Prioridad 1: Bug #1 - QSpinBox faltante
**Responsable:** Desarrollo Frontend
**Tiempo estimado:** 15 minutos
**Riesgo:** Bajo (cambio cosmético en imports)

**Pasos:**
1. Editar línea 29 de `modulos/ventas.py`
2. Agregar `QSpinBox` a importaciones
3. Reiniciar aplicación
4. Testear flujo: Venta → Pago → Canjear puntos

**Código exacto:**
```diff
--- a/modulos/ventas.py
+++ b/modulos/ventas.py
@@ -24,7 +24,7 @@ from PyQt5.QtWidgets import (
     QFrame, QTableWidget, QTableWidgetItem, QSplitter,
     QGroupBox, QSizePolicy, QAction, QGridLayout,
     QAbstractItemView, QDialog, QCheckBox, QFormLayout, QDoubleSpinBox,
-    QHeaderView, QRadioButton, QScrollArea, QListWidget, QListWidgetItem,
+    QHeaderView, QRadioButton, QScrollArea, QListWidget, QListWidgetItem, QSpinBox,
     QInputDialog, QGraphicsDropShadowEffect, QDialogButtonBox, QCompleter
 )
```

---

#### Prioridad 2: Bug #2 - Input manual de peso
**Responsable:** Desarrollo Full Stack
**Tiempo estimado:** 2 horas
**Riesgo:** Medio (cambio en UI de ventas)

**Pasos:**
1. Agregar `QDoubleSpinBox` para peso manual en UI
2. Hacerlo visible solo cuando `not self._hw_bascula_habilitada`
3. Modificar `agregar_producto_directo()` para leer de input manual
4. Testear ambos escenarios:
   - Con báscula habilitada → usa lectura automática
   - Con báscula deshabilitada → permite captura manual

---

### **FASE 1: INVESTIGACIÓN (Semana 1)**

#### Bug #3 - Recetas no se muestran
**Acciones:**
1. [ ] Revisar método `guardar_receta()` en `modulos/recetas.py`
2. [ ] Verificar si existe llamada a `refresh_ui()` post-guardado
3. [ ] Checar logs de errores en consola
4. [ ] Validar query SQL de selección
5. [ ] Testear con datos de prueba

**Entregable:** Root cause analysis documentado

#### Bug #6 - Error en Finanzas
**Acciones:**
1. [ ] Solicitar traceback específico al usuario
2. [ ] Revisar logs de aplicación
3. [ ] Identificar módulo financiero afectado
4. [ ] Reproducir error en ambiente controlado

**Entregable:** Bug report detallado con steps to reproduce

---

### **FASE 2: REFACTORIZACIÓN (Semanas 2-3)**

#### Bug #4 - Fusión Producción Cárnica
**Estrategia Recomendada:** Opción A (Fusionar)

**Pasos:**
1. [ ] Mover botón "Ejecutar Producción" a `recetas.py`
2. [ ] Migrar lógica de `produccion_carnica.py` a método en `recetas.py`
3. [ ] Actualizar menú principal para eliminar entrada duplicada
4. [ ] Deprecar `produccion_carnica.py` (marcar como obsoleto)
5. [ ] Eliminar archivo en siguiente release mayor

**Criterio de Aceptación:**
- Usuario puede crear receta Y ejecutarla desde misma pantalla
- Cero referencias a `ModuloProduccionCarnica` en código activo

---

#### Bug #5 - Integrar Planeación de Compras
**Arquitectura de Integración:**

```
┌─────────────────────┐
│  ForecastService    │ ← Predice demanda (ML)
└──────────┬──────────┘
           │ genera
           ▼
┌─────────────────────┐
│  SugerenciaCompra   │ ← Cantidad, producto, fecha ideal
└──────────┬──────────┘
           │ crea borrador
           ▼
┌─────────────────────┐
│  compras_pro.py     │ ← Orden de compra formal
└──────────┬──────────┘
           │ notifica
           ▼
┌─────────────────────┐
│  whatsapp_module.py │ ← Envía a proveedor
└──────────┬──────────┘
           │ confirma
           ▼
┌─────────────────────┐
│  inventario.py      │ ← Actualiza stock proyectado
└─────────────────────┘
```

**Pasos:**
1. [ ] Crear servicio `PurchasePlanningService`
2. [ ] Conectar con `ForecastService` existente
3. [ ] Integrar con flujo de `compras_pro.py`
4. [ ] Agregar webhook de confirmación en `whatsapp_module.py`
5. [ ] Dashboard de seguimiento: pendiente → enviada → recibida

---

#### Bug #7 - Unificar UI de BI/Decisiones
**Propuesta de Nueva Estructura:**

```python
class ModuloInteligenciaEmpresarial(QWidget):
    """Unifica BI + Decision Engine en una sola UI"""
    
    def init_ui(self):
        tabs = QTabWidget()
        
        # Tab 1: Dashboards Históricos
        tab_bi = DashboardBIWidget(self.container)
        tabs.addTab(tab_bi, "📊 Dashboards & KPIs")
        
        # Tab 2: Sugerencias Activas
        tab_decisiones = DecisionesWidget(self.container)
        tabs.addTab(tab_decisiones, "💡 Sugerencias IA")
        
        # Tab 3: Historial Decisiones
        tab_historial = HistorialDecisionesWidget(self.container)
        tabs.addTab(tab_historial, "📜 Historial")
```

**Pasos:**
1. [ ] Crear nuevo módulo `inteligencia_empresarial.py`
2. [ ] Migrar widgets de `reportes_bi_v2.py`
3. [ ] Crear UI para visualizar sugerencias de `decision_engine`
4. [ ] Actualizar menú principal
5. [ ] Deprecar `reportes_bi_v2.py`

---

## 📊 MATRIZ DE PRIORIDADES ACTUALIZADA

| Bug | Impacto Negocio | Frecuencia | Facilidad Fix | Prioridad | Sprint |
|-----|-----------------|------------|---------------|-----------|--------|
| #1 QSpinBox | 🔴 Alto (bloquea ventas) | Siempre | ✅ Fácil | **P0** | Hotfix |
| #2 Báscula manual | 🟠 Medio (pierde ventas) | Frecuente | ✅ Media | **P1** | Hotfix |
| #3 Recetas no muestran | 🟠 Medio (retrabajo) | Siempre | ❓ Por investigar | **P1** | Sprint 1 |
| #6 Finanzas error | 🔴 Crítico (contable) | ❓ Desconocida | ❓ Por investigar | **P0/P1** | Sprint 1 |
| #4 Producción duplicada | 🟡 Bajo (confusión) | Raro | ✅ Media | **P2** | Sprint 2 |
| #5 Compras no integrada | 🟠 Alto (ineficiencia) | Diario | ❌ Compleja | **P2** | Sprint 2-3 |
| #7 BI/Decisiones repetidos | 🟡 Bajo (UX) | Raro | ✅ Media | **P3** | Sprint 3 |

---

## ✅ CRITERIOS DE ACEPTACIÓN GENERALES

Para cada bug fix:

1. **Tests Automatizados:**
   - Unit test para el fix específico
   - Regression test del módulo afectado
   - Integration test del flujo completo

2. **Validación Manual:**
   - QA prueba en ambiente staging
   - Usuario clave valida en producción controlada
   - Zero errores en logs relacionados

3. **Documentación:**
   - CHANGELOG.md actualizado
   - README del módulo modificado
   - Capturas de pantalla si hay cambios UI

4. **Backward Compatibility:**
   - Migración de datos si aplica
   - Rollback plan documentado
   - Feature flag para activación gradual

---

## 📈 MÉTRICAS DE ÉXITO

| Métrica | Antes | Después Meta | Tiempo |
|---------|-------|--------------|--------|
| Errores NameError en producción | >0 | 0 | Inmediato |
| Ventas bloqueadas por báscula | Sí | No | 48hrs |
| Recetas visibles post-guardado | No | Sí | 1 semana |
| Módulos duplicados en menú | 2 | 1 | 3 semanas |
| Órdenes compra auto-generadas | 0% | 80% | 4 semanas |
| Satisfacción usuario (BI) | 3/5 | 4.5/5 | 4 semanas |

---

## 🔧 HERRAMIENTAS RECOMENDADAS PARA DEBUGGING

1. **Para Bug #3 (Recetas):**
```bash
# Habilitar logging detallado
export SPJ_LOG_LEVEL=DEBUG
python main.py 2>&1 | grep -i receta
```

2. **Para Bug #6 (Finanzas):**
```sql
-- Verificar integridad de datos financieros
SELECT COUNT(*) FROM asientos_contables WHERE fecha >= '2025-01-01';
SELECT * FROM errores_contables ORDER BY fecha DESC LIMIT 10;
```

3. **Para todos los bugs:**
```python
# En main.py, agregar al inicio
import sys
import traceback

def exception_handler(exctype, value, tb):
    logger.critical("".join(traceback.format_exception(exctype, value, tb)))

sys.excepthook = exception_handler
```

---

## 📝 NOTAS ADICIONALES

### Dependencias Externas Identificadas:
- `PyQt5.QtWidgets.QSpinBox` - Missing import
- `hardware.scale_reader` - Ya implementado
- `ForecastService` - Existente, necesita integración
- `recipe_engine` - Funcional, necesita mejor UI

### Riesgos Técnicos:
1. **Refactorización de producción:** Puede romper flujos existentes
2. **Integración compras:** Requiere testing exhaustivo con proveedores reales
3. **Unificación BI:** Migración de preferencias de usuario

### Mitigaciones:
- Feature flags para todos los cambios grandes
- Ambiente staging idéntico a producción
- Rollback automático si error rate > 1%

---

**Documento elaborado por:** Arquitectura Senior de Software  
**Revisión pendiente:** Equipo de QA + Usuarios Clave  
**Próxima actualización:** Tras resolución de Fase 0 (48hrs)
