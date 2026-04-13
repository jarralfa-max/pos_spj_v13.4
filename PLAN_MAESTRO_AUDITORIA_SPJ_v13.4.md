# 📋 PLAN MAESTRO DE AUDITORÍA Y MEJORA — POS/ERP SPJ v13.4

## 🔍 RESUMEN EJECUTIVO DE HALLAZGOS

**Fecha de Auditoría:** Abril 2025  
**Alcance:** Módulo de Ventas, Servicios Core, Repositorios, Concurrencia  
**Metodología:** Revisión estática de código + Análisis arquitectónico + Comparativa con benchmarks de industria

---

## 🚨 BUGS CRÍTICOS IDENTIFICADOS

### 1. **Condiciones de Carrera en Validación de Stock (CRÍTICO - SEVERIDAD 1)**

**Ubicación:** `core/use_cases/venta.py` línea 291-310, `core/services/inventory_service.py` línea 82-84

**Problema:**
```python
# Patrón vulnerable encontrado:
current_stock = self.repo.get_current_stock(product_id, branch_id)  # LECTURA
if current_stock < qty:  # VALIDACIÓN
    raise ValueError(...)
# ... tiempo pasa entre validación y escritura ...
self.repo.update_inventory_cache(...)  # ESCRITURA
```

**Impacto:**
- Dos cajeros vendiendo simultáneamente el mismo producto pueden generar stock negativo
- Ejemplo: Stock=10, Cajero A vende 8, Cajero B vende 5 → Stock final = -3
- Violación de integridad de inventario

**Evidencia en Código:**
- No hay `SELECT ... FOR UPDATE` ni locking optimista
- La transacción usa SAVEPOINT pero no protege la lectura-validación
- El script `stress_test_concurrency.py` existe pero prueba InventoryEngine, NO SalesService

**Recomendación:**
```python
# Implementar locking optimista con versionado:
UPDATE inventario 
SET cantidad = cantidad - ?, version = version + 1 
WHERE producto_id = ? AND branch_id = ? 
AND cantidad >= ? AND version = ?
```

---

### 2. **Transacciones No Atómicas en Post-Procesamiento (ALTO - SEVERIDAD 2)**

**Ubicación:** `core/services/sales_service.py` líneas 316-450

**Problema:**
```python
# Transacción principal termina línea 289
self.db.execute(f"RELEASE SAVEPOINT {_sp}")

# Post-procesamiento FUERA de transacción (líneas 320+):
self.loyalty_service.process_loyalty_for_sale(...)  # Puede fallar
self.finance_service.register_income(...)  # Ya registrado dentro, pero...
self.sync_service.registrar_evento(...)  # Fuera de transacción
```

**Impacto:**
- Si falla post-procesamiento, la venta está registrada pero efectos secundarios incompletos
- Puntos de lealtad no acreditados pero venta ya completada
- Sync a nube no encolado → inconsistencia offline/online
- Violación de patrón Saga/Unit of Work

**Recomendación:**
- Implementar cola de trabajos asíncrona (Celery/RQ)
- Patrón compensatorio: si falla fidelidad, enqueue retry automático
- Transactional outbox pattern para sync events

---

### 3. **Manejo Silencioso de Excepciones con `pass` (MEDIO-ALTO - SEVERIDAD 2-3)**

**Ubicaciones Múltiples:**

| Archivo | Línea | Contexto | Riesgo |
|---------|-------|----------|--------|
| `modulos/ventas.py` | 920, 1808, 2056, 2064 | Hardware/I/O | Bajo |
| `modulos/ventas.py` | 2747 | Validación turno caja | **Alto** |
| `modulos/ventas.py` | 2775 | Límite crédito cliente | **Alto** |
| `modulos/ventas.py` | 2872 | Validación margen | Medio |
| `modulos/ventas.py` | 3311, 3429, 3446, 3451 | Varios | Variable |
| `core/services/sales_service.py` | 157, 310, 378, 390 | Guardias de negocio | Medio |

**Problema:**
```python
# Ejemplo crítico línea 2747:
try:
    turno = fin_svc.get_estado_turno(self.sucursal_id, usuario)
    if not turno:
        # Mostrar advertencia de caja cerrada
        return
except Exception:
    pass  # ❌ Si falla la consulta, PERMITE vender sin caja abierta!
```

**Impacto:**
- Ventas registradas sin turno de caja abierto → conciliación imposible
- Clientes exceden límite de crédito sin alerta
- Márgenes negativos no detectados
- Viola controles internos NIF y principios de auditoría

**Recomendación:**
```python
# Reemplazar con logging + política definida:
except Exception as e:
    logger.error("Validación turno falló: %s", e)
    # Opción A: Bloquear (fail-secure)
    QMessageBox.critical(self, "Error", "No se puede verificar estado de caja")
    return
    # Opción B: Permitir con alerta auditada (fail-operational)
    audit_write(usuario, "VENTA_SIN_VALIDACION_CAJA", {...})
```

---

### 4. **Falta de Idempotencia en Execute Sale (MEDIO - SEVERIDAD 2)**

**Ubicación:** `core/services/sales_service.py` línea 47-315

**Problema:**
```python
def execute_sale(self, branch_id, user, items, payment_method, amount_paid, ...):
    operation_id = str(uuid.uuid4())  # ❌ Genera NUEVO UUID cada llamada
    # ...
    # Si se llama 2 veces con mismos parámetros → 2 ventas creadas
```

**Impacto:**
- Doble cobro a cliente si UI reenvía petición
- Inventario descontado dos veces
- Reportes financieros inflados
- Comunes en redes lentas o timeouts de red

**Recomendación:**
```python
def execute_sale(self, ..., operation_id: str = None, ...):
    if operation_id:
        # Verificar si ya existe
        existing = self.db.execute(
            "SELECT id FROM ventas WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if existing:
            return self._replay_venta(existing['id'])  # Idempotencia
    
    operation_id = operation_id or str(uuid.uuid4())
    # ... continuar normalmente
```

---

### 5. **Inconsistencia en Campo de Costo para Márgenes (MEDIO - SEVERIDAD 2-3)**

**Ubicación:** 
- Validación: `core/services/enterprise/finance_service.py` línea 1142-1162
- Uso en ventas: `modulos/ventas.py` línea 2851-2855

**Problema:**
```python
# FinanceService usa 'precio_costo':
row = self.db.execute(
    "SELECT precio_costo FROM productos WHERE id=?", (producto_id,)
).fetchone()

# Pero UI lee 'precio_compra':
costo_row = self.container.db.execute(
    "SELECT precio_compra FROM productos WHERE id=?", (item['id'],)
).fetchone()
```

**Impacto:**
- Dos campos diferentes pueden tener valores distintos
- Validación de margen en UI usa costo diferente al del reporte financiero
- Utilidad bruta calculada incorrectamente
- Problemas en declaración de impuestos (SAT)

**Recomendación:**
- Unificar a un solo campo `precio_costo` (estándar contable)
- Migración de datos para consolidar
- Trigger de BD para mantener sincronizados si se requieren ambos

---

### 6. **Duplicación de Lógica de Procesamiento de Ventas (MEDIO - SEVERIDAD 3)**

**Ubicaciones:**
1. `modulos/ventas.py` → `finalizar_venta()` (UI directa)
2. `core/services/sales_service.py` → `execute_sale()`
3. `core/use_cases/venta.py` → `ProcesarVentaUC.ejecutar()`
4. `core/services/sales/unified_sales_service.py` (existe pero no usado consistentemente)

**Problema:**
- Mismo flujo replicado con variaciones menores
- Difícil mantener consistencia en actualizaciones
- Bug fixes deben aplicarse en 3-4 lugares
- Testing duplicado

**Recomendación:**
- Designar `ProcesarVentaUC` como única entrada oficial
- Deprecar `SalesService.execute_sale()` directo desde UI
- Refactorizar `modulos/ventas.py` para solo llamar UC

---

### 7. **Validación de Stock para Combos Incompleta (BAJO-MEDIO - SEVERIDAD 3)**

**Ubicación:** `core/use_cases/venta.py` línea 291-310

**Problema:**
```python
def _validar_stock(self, items, sucursal_id):
    for item in items:
        if item.es_compuesto:
            continue  # ❌ Salta validación para combos!
        # ... valida solo productos simples
```

**Impacto:**
- Combo puede venderse aunque ingredientes insuficientes
- Error ocurre durante descuento de inventario (después de cobrar)
- Experiencia negativa: reversión necesaria

**Recomendación:**
```python
if item.es_compuesto:
    recipe = self._recipe_repo.get_recipe(item.producto_id)
    for ingredient in recipe:
        qty_needed = ingredient.cantidad * item.cantidad
        disponible = self._inventory.get_stock(ingredient.producto_id, sucursal_id)
        if disponible < qty_needed:
            return f"Stock insuficiente para {ingredient.nombre} en combo"
```

---

## 📊 COMPARATIVA CON SISTEMAS POS/ERP DE REFERENCIA

### Benchmarks Analizados:
- **Square POS** (Líder en SMB retail)
- **Lightspeed Retail** (Inventario avanzado)
- **Odoo ERP** (Open-source, modular)
- **SAP Business One** (Enterprise)
- **Aspel COI/SAE** (México, cumplimiento SAT)

### Matriz de Capacidades:

| Característica | SPJ v13.4 | Square | Odoo | SAP B1 | Brecha |
|---------------|-----------|--------|------|--------|--------|
| **Atomicidad Transaccional** | ⚠️ Parcial (SAVEPOINT sin locking) | ✅ Completa (row-level locks) | ✅ Completa | ✅ Completa | 🔴 Alta |
| **Idempotencia** | ❌ No implementada | ✅ Token único por transacción | ✅ Referencia externa | ✅ Documento único | 🔴 Crítica |
| **Manejo de Concurrencia** | ⚠️ WAL mode sin locks explícitos | ✅ Optimistic locking | ✅ Row-level locks | ✅ Pessimistic locking | 🔴 Alta |
| **Trazabilidad de Costos** | ⚠️ FIFO opcional (LoteService) | ✅ FIFO/LIFO estándar | ✅ Múltiples métodos | ✅ Estándar IFRS/NIF | 🟡 Media |
| **Post-procesamiento Asíncrono** | ❌ Síncrono fuera de TX | ✅ Job queues (Sidekiq) | ✅ Job queues | ✅ Background jobs | 🟡 Media |
| **Validación de Márgenes** | ⚠️ En UI + servicio (duplicado) | ✅ Reglas globales servidor | ✅ Reglas configurables | ✅ Control central | 🟡 Media |
| **CFDI 4.0 México** | ⚠️ CFDIService existe | ❌ N/A | ⚠️ Módulo localización | ⚠️ Add-on | 🟡 Media |
| **Offline-First Sync** | ✅ Event-based sync | ✅ Sync nativo | ⚠️ Requiere configuración | ❌ Siempre online | 🟢 Ventaja |
| **Lealtad/Gamificación** | ✅ GrowthEngine + Loyalty | ✅ Square Loyalty | ⚠️ Módulo separado | ❌ Add-on | 🟢 Ventaja |

### Hallazgos Clave de Comparativa:

1. **Square POS**: Maneja 10K+ transacciones/hora con idempotencia garantizada vía `idempotency_key` en API
2. **Odoo**: Usa patrón CQRS completo con colas Celery para post-procesamiento
3. **SAP B1**: Blocking a nivel de base de datos con `SELECT FOR UPDATE` en validación de stock
4. **Aspel SAE**: Timbrado CFDI inmediato antes de completar venta (requisito SAT)

---

## 🎯 PLAN DE MEJORA POR FASES

### **FASE 1: ESTABILIZACIÓN CRÍTICA (Semanas 1-2)**
**Objetivo:** Eliminar bugs que causan pérdida financiera directa

#### Módulo: Ventas Core + Inventarios

**Acciones:**
1. **Implementar Idempotencia** (`core/services/sales_service.py`)
   - Agregar parámetro `operation_id` externo (desde UI)
   - Verificar existencia antes de crear venta
   - Tabla: `ventas.operation_id` UNIQUE INDEX

2. **Locking Optimista en Stock** (`core/services/inventory_service.py`)
   ```sql
   ALTER TABLE inventario ADD COLUMN version INTEGER DEFAULT 0;
   
   -- En deduct_stock:
   UPDATE inventario 
   SET cantidad = cantidad - ?, 
       version = version + 1 
   WHERE producto_id = ? AND branch_id = ? 
     AND version = ? AND cantidad >= ?
   ```

3. **Eliminar `pass` Silenciosos Críticos** (`modulos/ventas.py`)
   - Líneas 2747, 2775, 2872: Logging + política fail-secure/fail-operational
   - Agregar tests que verifiquen comportamiento

4. **Unificar Punto de Entrada** (`modulos/ventas.py` → `core/use_cases/venta.py`)
   - Refactorizar `finalizar_venta()` para usar solo `uc_venta.ejecutar()`
   - Deprecar llamada directa a `sales_service.execute_sale()`

**Entregables:**
- [ ] Test de concurrencia: 100 ventas simultáneas sin stock negativo
- [ ] Test de idempotencia: doble llamada = 1 venta creada
- [ ] Zero `pass` en validaciones de negocio críticas
- [ ] Cobertura de tests > 70% en módulo ventas

**KPIs de Éxito:**
- Stock negativo = 0 en producción
- Ventas duplicadas = 0 reportadas
- Tiempo de venta < 2s (sin degradación)

---

### **FASE 2: CONSISTENCIA CONTABLE Y FISCAL (Semanas 3-4)**
**Objetivo:** Cumplimiento NIF/SAT y precisión financiera

#### Módulo: Finanzas + CFDI + Reportes

**Acciones:**
1. **Unificar Campos de Costo**
   - Migración: Consolidar `precio_compra` → `precio_costo`
   - Actualizar todas las referencias en código
   - Trigger de auditoría si se modifican costos

2. **Trazabilidad de Costo por Venta**
   ```python
   # En detalles_venta agregar:
   ALTER TABLE detalles_venta ADD COLUMN costo_unitario DECIMAL(12,2);
   ALTER TABLE detalles_venta ADD COLUMN utilidad_bruta DECIMAL(12,2);
   
   # Al registrar venta:
   costo = get_costo_promedio(producto_id, branch_id)  # Del inventario
   utilidad = (precio_venta - costo) * cantidad
   ```

3. **Validación de Margen Bloqueante**
   - Configurable por categoría/producto
   - Roles: Gerente puede autorizar márgenes negativos
   - Auditoría: Registrar quién autorizó y por qué

4. **Integración CFDI 4.0 Pre-Venta**
   ```python
   # Antes de finalizar_venta():
   if cliente_id and rfc_cliente:
       cfdi_preview = cfdi_service.generar_comprobante(items, total)
       # Validar que timbre sea posible
       if not cfdi_preview.valido:
           raise ValidationError(cfdi_preview.error)
   ```

5. **Conciliación Automática Inventario-Contabilidad**
   - Job nocturno: Comparar `inventario.cantidad` vs suma `movimientos_inventario`
   - Alertas si diferencia > umbral configurable
   - Asientos contables automáticos por ajuste

**Entregables:**
- [ ] Reporte de utilidad bruta por venta/disponible
- [ ] CFDI 4.0 timbrado al completar venta (sandbox SAT)
- [ ] DIOT exportable en formato SAT
- [ ] Asientos contables generados automáticamente

**KPIs de Éxito:**
- Utilidad bruta calculada = realidad financiera
- 0 multas por CFDI mal timbrados
- Conciliación inventario < 1% discrepancia

---

### **FASE 3: ARQUITECTURA EMPRESARIAL (Semanas 5-6)**
**Objetivo:** Escalabilidad y mantenibilidad a largo plazo

#### Módulo: Arquitectura General + Infraestructura

**Acciones:**
1. **Saga Pattern para Post-Procesamiento**
   ```python
   class VentaSaga:
       steps = [
           RegistrarVenta(),      # Transaccional
           DescontarInventario(), # Transaccional
           RegistrarIngreso(),    # Transaccional
           AcumularPuntos(),      # Compensable
           GenerarTicket(),       # Reintentable
           EncolarSync(),         # Reintentable
           NotificarCliente(),    # Opcional
       ]
       
       def ejecutar(self):
           for step in self.steps:
               try:
                   step.execute()
               except CompensableError:
                   self._compensar_hasta_aqui()
                   raise
   ```

2. **Migrar a Colas de Trabajo Reales**
   - Instalar Redis + RQ (o Celery si ya existe)
   - Mover: fidelidad, tickets, sync, notificaciones
   - Retry con backoff exponencial

3. **Consolidar Servicios Duplicados**
   - Auditar: `SalesService` vs `UnifiedSalesService` vs `ProcesarVentaUC`
   - Designar ganador: `ProcesarVentaUC`
   - Crear adapters para código legacy

4. **CQRS Completo para Lecturas**
   - Separar modelos de lectura (reportes) vs escritura (transaccional)
   - Proyecciones materializadas para dashboard
   - Event sourcing para auditoría forense

**Entregables:**
- [ ] Post-procesamiento 100% asíncrono
- [ ] Tiempo de venta < 500ms (solo transaccional crítico)
- [ ] Cero dependencias circulares detectadas
- [ ] Documentación de arquitectura actualizada

**KPIs de Éxito:**
- P95 latencia de venta < 500ms
- Throughput > 100 ventas/minuto
- MTTR < 1 hora para bugs críticos

---

### **FASE 4: CUMPLIMIENTO FISCAL MÉXICANO (Semanas 7-8)**
**Objetivo:** Blindaje fiscal y auditoría SAT

#### Módulo: CFDI + Contabilidad + Reportes SAT

**Acciones:**
1. **Validación de RFC Antes de Crédito**
   ```python
   def validar_credito_cliente(cliente_id, monto):
       rfc = get_rfc_cliente(cliente_id)
       if not rfc or not sat_validar_rfc(rfc):
           raise ValidationError("RFC inválido para crédito")
       
       # Verificar lista negra SAT (opcional)
       if sat_en_lista_negra(rfc):
           logger.warning(f"Cliente {rfc} en lista negra SAT")
   ```

2. **Timbrado CFDI en Tiempo Real**
   - Integración PAC (Proveedor Autorizado de Certificación)
   - Fallback: guardar XML local si PAC cae
   - Reintento automático de timbrado

3. **Reportes DIOT Automatizados**
   - Extracción mensual de operaciones con proveedores
   - Formato exacto requerido por SAT
   - Validación previa al envío

4. **Auditoría Forense Habilitada**
   - Hash criptográfico por venta (SHA-256)
   - Encadenamiento: hash_venta_n incluye hash_venta_(n-1)
   - Inmutable: cualquier cambio invalida cadena

**Entregables:**
- [ ] CFDI 4.0 timbrado exitosamente (producción)
- [ ] DIOT Q1 2025 generado y validado
- [ ] Auditoría con hash criptográfico implementada
- [ ] Manual de procedimientos fiscales

**KPIs de Éxito:**
- 100% ventas con CFDI timbrado
- 0 observaciones en auditoría fiscal
- Tiempo de generación DIOT < 5 minutos

---

### **FASE 5: OPTIMIZACIÓN Y ESCALABILIDAD (Semanas 9-10)**
**Objetivo:** Performance y crecimiento sostenido

#### Módulo: Performance + Base de Datos + Infraestructura

**Acciones:**
1. **Índices de Base de Datos Faltantes**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_ventas_fecha_sucursal ON ventas(fecha, sucursal_id);
   CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
   CREATE INDEX IF NOT EXISTS idx_detalles_producto ON detalles_venta(producto_id);
   CREATE INDEX IF NOT EXISTS idx_movimientos_operacion ON movimientos_inventario(operation_id);
   CREATE INDEX IF NOT EXISTS idx_inventario_version ON inventario(producto_id, branch_id, version);
   ```

2. **Particionamiento de Tablas Históricas**
   - `ventas`: particionar por año
   - `movimientos_inventario`: particionar por trimestre
   - Archive data > 2 años a tablas `_archive`

3. **Caché de Lecturas Frecuentes**
   - Redis para: precios, stock, configuración
   - Invalidación por eventos (no TTL)
   - Fallback a BD si Redis cae

4. **Load Testing Automatizado**
   - Script: `scripts/stress_test_concurrency.py` extender a 1000 usuarios
   - CI/CD: correr en cada PR
   - Alerts: si P95 > 1s

**Entregables:**
- [ ] Query más lento < 100ms (p95)
- [ ] Soporta 100 usuarios concurrentes sin degradación
- [ ] Plan de particionamiento documentado e implementado
- [ ] Dashboard de performance en tiempo real

**KPIs de Éxito:**
- Throughput > 500 ventas/minuto
- CPU < 70% bajo carga máxima
- Memoria estable sin leaks

---

## 📈 ROADMAP RESUMEN

| Fase | Semanas | Bugs Mitigados | ROI Esperado | Complejidad |
|------|---------|----------------|--------------|-------------|
| **Fase 1** | 1-2 | Stock negativo, ventas duplicadas, excepciones silenciosas | **Inmediato** - Evita pérdidas directas | Baja |
| **Fase 2** | 3-4 | Multas SAT, utilidades mal calculadas | **Alto** - Cumplimiento fiscal | Media |
| **Fase 3** | 5-6 | Cuellos de botella, caídas en pico | **Medio** - Escalabilidad futura | Alta |
| **Fase 4** | 7-8 | Sanciones fiscales, cancelación de sellos | **Crítico** - Supervivencia negocio | Media-Alta |
| **Fase 5** | 9-10 | Lentitud, insatisfacción usuarios | **Medio** - Crecimiento sostenible | Media |

**Total Estimado:** 10 semanas (2.5 meses)  
**Recursos Requeridos:** 2 desarrolladores senior + 1 QA + 1 contador (Fase 2 y 4)

---

## ✅ CRITERIOS DE ACEPTACIÓN GENERALES

### Calidad de Código:
- [ ] Tests automatizados: Cobertura > 80% en módulos modificados
- [ ] Zero warnings de linter (flake8/pylint)
- [ ] Documentación actualizada (docstrings + README)

### Performance:
- [ ] No degradar tiempo de venta actual (< 2s)
- [ ] Throughput mínimo 100 ventas/minuto
- [ ] Memoria estable en pruebas de estrés (8 horas)

### Backward Compatibility:
- [ ] Migración de datos sin downtime
- [ ] Scripts de migración reversibles
- [ ] Feature flags para rollout gradual

### Seguridad:
- [ ] SQL injection scan (usar sqlmap)
- [ ] AuthZ verificada en todos los endpoints
- [ ] Logs sin datos sensibles (enmascarar RFC, tarjetas)

### Operaciones:
- [ ] Runbook de deployment actualizado
- [ ] Playbook de incidentes (qué hacer si X falla)
- [ ] Monitoreo: alerts configurados en Sentry/Prometheus

---

## 🔧 RECOMENDACIONES ADICIONALES

### Herramientas Sugeridas:

**Testing:**
```bash
pytest --cov=core/services --cov-report=html
pytest-xdist  # Para tests de concurrencia
locust        # Load testing
```

**Monitoreo:**
```python
# Sentry para tracking de excepciones
import sentry_sdk
sentry_sdk.init(dsn="...", traces_sample_rate=0.1)

# Prometheus métricas custom
from prometheus_client import Counter, Histogram
VENTAS_TOTAL = Counter('ventas_total', 'Total sales')
VENTAS_LATENCY = Histogram('ventas_latency_seconds', 'Sale latency')
```

**CI/CD:**
```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements.txt
      - run: pytest --cov-fail-under=80
      - run: python scripts/stress_test_concurrency.py --iterations 50
```

### Deuda Técnica Identificada (Fuera de Scope Inmediato):

1. **Python 2→3 migration remnants**: Algunos imports sugieren código legacy
2. **PyQt5 acoplamiento fuerte**: UI mezclada con lógica de negocio
3. **SQLite para enterprise**: Considerar PostgreSQL para multi-sucursal real
4. **Sincronización offline**: Algoritmo de conflict resolution básico

---

## 📝 CONCLUSIONES

### Fortalezas del Sistema Actual:
✅ Arquitectura por capas bien definida (repos, services, use_cases)  
✅ Inyección de dependencias vía AppContainer  
✅ Event bus para desacoplamiento  
✅ Offline-first con sync engine  
✅ Growth engine y lealtad avanzados  

### Áreas Críticas de Mejora:
🔴 Concurrencia no manejada adecuadamente  
🔴 Idempotencia inexistente  
🔴 Excepciones silenciosas en puntos críticos  
🔴 Duplicación de lógica de negocio  
🔴 Validación fiscal reactiva (no preventiva)  

### Riesgo de No Actuar:
- **Financiero:** Pérdida de inventario, multas SAT, conciliaciones imposibles
- **Operativo:** Caídas en horas pico, corrupción de datos
- **Legal:** Incumplimiento fiscal, auditorías negativas
- **Reputacional:** Clientes cobrados doble, stock incorrecto

---

**Elaborado por:** Arquitectura Senior de Software + CFO + COO  
**Revisión:** Pendiente con equipo de desarrollo  
**Aprobación:** Requiere validación de dirección general

---

*Documento vivo — Actualizar tras cada fase completada*
