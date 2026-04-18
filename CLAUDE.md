# CLAUDE.md — pos_spj v13.4 → ERP Transformation Pipeline

Guías de desarrollo para Claude Code en este proyecto.

## 🎯 CONTEXTO: TRANSFORMACIÓN POS → ERP

Este documento establece las reglas para la transformación del sistema POS actual en un **ERP modular, escalable y listo para producción**, siguiendo el pipeline definido en `ERP_TRANSFORMATION_DIAGNOSIS.md`.

## Reglas absolutas (no negociables)

### 🔴 PRIORIDAD 0 — PRESERVACIÓN DE LÓGICA DE NEGOCIO

1. **NO perder lógica de negocio durante refactorización.** Antes de extraer/mover código:
   - Identificar TODA la lógica de negocio en el módulo original
   - Crear tests que verifiquen el comportamiento actual
   - Extraer mantiendo la misma funcionalidad
   - Verificar con tests que el comportamiento es idéntico

2. **Refactorización controlada permitida :**
   - ✅ EXTRAER lógica de UI a `domain/` y `application/`
   - ✅ MOVER servicios a arquitectura limpia (domain/application/infrastructure/ui)
   - ✅ ELIMINAR código muerto detectado en auditoría
   - ✅ ELIMINAR duplicación identificada
   - ✅ AGREGAR type hints progresivamente
   - ❌ NO eliminar funcionalidad operativa sin migración completa

3. **Cambios incrementales con trazabilidad:**
   - Cada refactor debe documentarse en `migrations/MIGRATION_LOG.md`
   - Cada módulo refactorizado debe tener tests de regresión
   - Usar feature flags para transición gradual si es necesario

### 🟡 ARQUITECTURA OBJETIVO 

```
pos_spj_v13.4/
├── domain/           # Lógica pura de negocio (entities, value objects)
├── application/      # Casos de uso, services orchestrators
├── infrastructure/   # DB, APIs externas, repositories implementation
├── ui/               # PyQt5, presentación (SIN lógica de negocio)
├── core/             # Legacy compatible (shims, event bus)
└── tests/            # Tests unitarios + integración + regresión
```

### 🟢 REGLAS ESPECÍFICAS POR CAPA

4. **Capa `domain/` (lógica pura):**
   - Sin dependencias de frameworks, UI, o infraestructura
   - Entities con validaciones de negocio
   - Value objects inmutables
   - Domain services para lógica cross-entity

5. **Capa `application/` (casos de uso):**
   - Orquestan domain services + repositories
   - Sin dependencias de UI o infraestructura directa
   - Transacciones atómicas
   - Logging estructurado

6. **Capa `infrastructure/` (acceso a datos/APIs):**
   - Implementaciones concretas de repositories
   - Conexiones DB, APIs externas, mensajería
   - Dependencias externas aisladas aquí

7. **Capa `ui/` (presentación):**
   - SOLO presentación y manejo de eventos UI
   - Delegar TODA lógica a application layer
   - Sin SQL directo
   - Sin reglas de negocio

### 🔵 SHIMS Y COMPATIBILIDAD

8. **Shims de compatibilidad (preservar durante transición):**
   - Finance: `core/services/finance_service.py` → re-exporta desde `enterprise/`
   - WhatsApp: `services/whatsapp_service.py` y `integrations/whatsapp_service.py`

9. **Preservar los 3 shims de WhatsApp (son intencionales para legacy):**
   - `pos_spj_v13.4/services/whatsapp_service.py` (SHIM v12)
   - `pos_spj_v13.4/integrations/whatsapp_service.py` (SHIM v12)
   - `whatsapp_service/webhook/whatsapp.py` (webhook handler)

10. **EventBus: evolución controlada:**
    - El archivo `core/events/event_bus.py` PUEDE ser refactorizado en FASE 3
    - Mantener backward compatibility con aliases durante transición
    - Documentar cambios en `MIGRATION_LOG.md`

### 🟣 INTEGRIDAD FINANCIERA Y AUDITORÍA

11. **Todo impacto financiero debe tener asiento contable (debe = haber).**
    Cualquier operación que mueva dinero debe llamar a `finance_service.registrar_asiento()`
    con campos `cuenta_debe`, `cuenta_haber` y `monto` balanceados.

12. **Audit trail: toda operación financiera debe loguear en `financial_event_log`.**
    Usar `finance_service.registrar_asiento()` que escribe en esta tabla automáticamente.
13. **SQL seguro:**
    - ❌ NUNCA SQL directo en UI
    - ✅ Usar repositories con queries parametrizados
    - ✅ Validar inputs antes de construir queries

### 🟤 MICROSERVICIO WHATSAPP

14. **Microservicio WhatsApp es CORE del ERP:**
    - Arquitecto como servicio independiente (`/workspace/whatsapp_service/`)
    - Comunicación vía REST + EventBus
    - Flujos conversacionales: pedido, registro, menú, cotización, pago, estado, puntos
    - Integración con ERP Bridge (`whatsapp_service/erp/bridge.py`)

15. **Patrones de integración:**
    - Event-driven para operaciones asíncronas
    - REST síncrono para consultas rápidas
    - Cola de mensajes para retries (pendiente implementar)

### ⚪ VALIDACIÓN Y TESTS

16. **Cada cambio debe tener tests:**
    - Unitarios para domain layer
    - Integración para application + infrastructure
    - End-to-end para flujos críticos (ventas, inventario, finanzas)
    - Regresión antes de refactorizar

17. **Checklist pre-merge:**
    - [ ] No se perdió lógica de negocio
    - [ ] No hay duplicación nueva
    - [ ] No hay SQL inválido
    - [ ] UI separada de lógica
    - [ ] Tests passing
    - [ ] Documentación actualizada

## 📋 PROCESO DE REFACTORIZACIÓN 

### Paso a paso para refactorizar un módulo:

1. **AUDITAR:** Identificar lógica de negocio vs UI
2. **TESTEAR:** Crear tests que capturen comportamiento actual
3. **EXTRAER:** Mover lógica a `domain/` o `application/`
4. **REEMPLAZAR:** UI llama a application 
5. **VALIDAR:** Tests deben pasar igual que antes
6. **LIMPIAR:** Eliminar código duplicado/muerto
7. **DOCUMENTAR:** Actualizar `MIGRATION_LOG.md`

### Ejemplo de extracción:

```python
# ANTES (en UI):
class VentaWindow(QMainWindow):
    def guardar_venta(self):
        # 50 líneas de lógica de negocio + validaciones + SQL

# DESPUÉS (separado):
# domain/services/sale_domain_service.py
class SaleDomainService:
    def calcular_totales(self, items): ...
    def validar_stock(self, items): ...

# application/use_cases/create_sale_use_case.py
class CreateSaleUseCase:
    def execute(self, sale_data): ...

# ui/windows/sale_window.py
class VentaWindow(QMainWindow):
    def guardar_venta(self):
        use_case = CreateSaleUseCase(self.domain_service, self.repo)
        use_case.execute(self.sale_data)
```

## 📊 MÉTRICAS DE PROGRESO


| Fase | Estado | Completitud |
|------|--------|-------------|
| FASE 0: Ingesta | ✅ Completa | 100% |
| FASE 1: Auditoría | ✅ Completa | 100% |
| FASE 2: Benchmark ERP | ✅ Completa | 100% |
| FASE 3: Rearquitectura | 🔄 En curso | Planificada |
| FASE 4: Refactor | 🔄 En curso | Pendiente |
| FASE 5: Microservicios | ✅ WhatsApp OK | 80% |
| FASE 6: Integración | ⏳ Pendiente | 0% |
| FASE 7: Validación | ⏳ Pendiente | 0% |

## Arquitectura del proyecto (ACTUAL → OBJETIVO)

### Arquitectura ACTUAL (legacy):

```
pos_spj_v13.4/
├── pos_spj_v13.4/
│   ├── core/
│   │   ├── services/          # Servicios canónicos (DDD)
│   │   │   └── enterprise/    # Servicios ERP completos
│   │   ├── events/            # EventBus + wiring de handlers
│   │   ├── db/                # Pool de conexiones SQLite
│   │   └── use_cases/         # CQRS
│   ├── modulos/               # UI PyQt5 (CONTIENE lógica de negocio - A REFACTORIZAR)
│   ├── repositories/          # Acceso a datos
│   ├── migrations/
│   │   ├── engine.py          # Ejecutor de migraciones (lista hardcodeada)
│   │   ├── m000_base_schema.py
│   │   ├── standalone/        # Migraciones incrementales 016-054
│   │   └── MIGRATION_LOG.md   # Log de decisiones
│   ├── sync/                  # Motor de sincronización offline-first
│   └── tests/                 # Suite de tests
└── whatsapp_service/          # Microservicio FastAPI independiente
    └── erp/bridge.py          # Puente ERP ↔ WhatsApp
```


### Arquitectura OBJETIVO (ERP - FASE 3):
```
pos_spj_v13.4/
├── domain/                    # NEW - Lógica pura de negocio
│   ├── entities/              # Entidades core (Sale, Product, Customer, etc.)
│   ├── value_objects/         # Objetos de valor (Money, Quantity, etc.)
│   └── services/              # Domain services (reglas cross-entity)
│
├── application/               # NEW - Casos de uso y orquestación
│   ├── use_cases/             # Casos de uso (CreateSale, UpdateInventory, etc.)
│   ├── services/              # Application services
│   └── dtos/                  # Data Transfer Objects
│
├── infrastructure/            # NEW - Implementaciones concretas
│   ├── persistence/           # Repositories implementations
│   ├── messaging/             # EventBus, colas, webhooks
│   └── external_apis/         # APIs externas (Twilio, SAP, etc.)
│
├── ui/                        # NEW - Presentación (PyQt5, Web)
│   ├── qt5/                   # Ventanas PyQt5 (SIN lógica de negocio)
│   └── web/                   # Dashboard web (pendiente)
│
├── core/                      # LEGACY COMPATIBILITY LAYER
│   ├── events/                # EventBus (migrar gradualmente)
│   ├── services/              # Shims hacia nueva arquitectura
│   └── db/                    # Pool connections (migrar a infrastructure)
│
├── repositories/              # TRANSICIÓN → infrastructure/persistence/
├── migrations/                # Se mantiene (infraestructura DB)
├── sync/                      # TRANSICIÓN → infrastructure/messaging/
├── integrations/              # TRANSICIÓN → infrastructure/external_apis/
└── tests/                     # Tests unitarios + integración + e2e
```

### Notas sobre transición:
- `core/` actúa como capa de compatibilidad durante la migración
- Los shims redirigen gradualmente de legacy → nueva arquitectura
- Cada módulo refactorizado mueve su lógica a `domain/` o `application/`
- La UI (`modulos/`) se vacía de lógica progresivamente

## Convenciones de migraciones

- Numeración secuencial: `NNN_nombre_descriptivo.py`
- Función de entrada: `run(conn)` o `crear_tablas(conn)`
- Siempre usar `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- Registrar en `engine.py` en la lista `MIGRATIONS` antes de hacer commit
- Documentar en `MIGRATION_LOG.md`

## EventBus — orden de prioridades

| Prioridad | Uso |
|-----------|-----|
| 100 | Sync inmediato (inventario, ventas) |
| 80  | Operaciones críticas de negocio |
| 50  | Contabilidad / ledger |
| 30  | Auditoría |
| 10  | Notificaciones secundarias |
| 5   | Analytics / BI |

## Tests

```bash
# Correr todos los tests
cd pos_spj_v13.4 && python -m pytest tests/ -v

# Correr solo tests de una fase
python -m pytest tests/test_event_bus_aliases.py -v

# Verificar sintaxis de todos los archivos .py
python -c "
import ast, os, sys
errors = []
for root, _, files in os.walk('pos_spj_v13.4'):
    if '.venv' in root or '.git' in root: continue
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        try: ast.parse(open(path).read())
        except SyntaxError as e: errors.append(f'{path}: {e}')
print('\n'.join(errors) if errors else 'SIN errores de sintaxis')
"
```

## Scripts de diagnóstico

```bash
# Auditar migraciones
python scripts/audit_migrations.py

# Verificar tablas en la DB
python scripts/verify_tables.py --db pos_spj.db

# Bootstrap DB desde cero
python scripts/bootstrap_db.py --db /tmp/test.db
```
