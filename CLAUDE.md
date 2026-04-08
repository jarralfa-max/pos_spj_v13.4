# CLAUDE.md — pos_spj v13.4

Guías de desarrollo para Claude Code en este proyecto.

## Reglas absolutas (no negociables)

1. **NO modificar lógica existente que funcione.** Si un módulo funciona, no lo toques.
   Solo agrega código nuevo; nunca refactorices, renombres ni reorganices código operativo.

2. **Cambios SIEMPRE incrementales y aditivos.** Shims, adaptadores y wrappers antes que
   reescrituras. Si necesitas un nuevo comportamiento, agrégalo sin romper el antiguo.

3. **Cada cambio debe tener su test unitario.** Todo archivo nuevo o modificado debe tener
   un test correspondiente en `pos_spj_v13.4/tests/`. Sin test = sin merge.

4. **Shims de compatibilidad para re-exports.** Los shims ya existen para:
   - Finance: `core/services/finance_service.py` → re-exporta desde `enterprise/`
   - WhatsApp: `services/whatsapp_service.py` y `integrations/whatsapp_service.py`
   Nunca elimines ni modifiques estos shims.

5. **Documentar en `migrations/MIGRATION_LOG.md` cada decisión sobre migraciones.**
   Antes de crear, renombrar o fusionar cualquier migración, agrega una entrada al log.

6. **Preservar los 3 shims de WhatsApp (son intencionales para legacy):**
   - `pos_spj_v13.4/services/whatsapp_service.py` (SHIM v12)
   - `pos_spj_v13.4/integrations/whatsapp_service.py` (SHIM v12)
   - `whatsapp_service/webhook/whatsapp.py` (webhook handler)

7. **EventBus: solo agregar aliases/constantes, no cambiar el core.**
   El archivo `core/events/event_bus.py` solo puede recibir nuevas constantes o aliases.
   Nunca modifiques la clase EventBus, sus métodos, ni el orden de constantes existentes.

8. **Todo impacto financiero debe tener asiento contable (debe = haber).**
   Cualquier operación que mueva dinero debe llamar a `finance_service.registrar_asiento()`
   con campos `cuenta_debe`, `cuenta_haber` y `monto` balanceados.

9. **Audit trail: toda operación financiera debe loguear en `financial_event_log`.**
   Usar `finance_service.registrar_asiento()` que escribe en esta tabla automáticamente.

## Arquitectura del proyecto

```
pos_spj_v13.4/
├── pos_spj_v13.4/
│   ├── core/
│   │   ├── services/          # Servicios canónicos (DDD)
│   │   │   └── enterprise/    # Servicios ERP completos
│   │   ├── events/            # EventBus + wiring de handlers
│   │   ├── db/                # Pool de conexiones SQLite
│   │   └── use_cases/         # CQRS
│   ├── modulos/               # UI PyQt5 (NO contiene lógica de negocio)
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
