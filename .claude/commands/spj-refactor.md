# SPJ ERP/POS Refactor Skill for Codex

> Archivo guía para ejecutar la reestructuración completa del ERP/POS SPJ con Codex de forma controlada, por fases y módulos, sin perder lógica de negocio funcional.

---

# REGLA CERO — UUIDv7 COMO ÚNICA IDENTIDAD

Esta regla es obligatoria y tiene prioridad sobre cualquier instrucción posterior de este skill.

## Decisión no negociable

Toda entidad persistente, relación funcional, evento, comando, DTO, caso de uso, repositorio, API y operación sincronizable debe utilizar **UUIDv7 como única identidad**.

Queda prohibido conservar dentro del runtime:

- IDs enteros funcionales.
- `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `legacy_id`.
- escritura dual.
- lectura dual.
- fallback de UUID a entero.
- tablas paralelas de compatibilidad.
- contratos `int | str`.
- conversiones `int(product_id)`, `int(sale_id)`, `int(branch_id)` o equivalentes.
- `lastrowid` como identidad de dominio.
- `MAX(id) + 1`.
- folios, SKU, códigos de barras o números de ticket como clave primaria.

## Generador obligatorio

Debe existir una sola fuente de generación:

```text
backend/shared/ids.py
```

Contrato:

```python
def new_uuid() -> str:
    """Return a canonical lowercase UUIDv7 string."""
```

Ningún widget PyQt, repositorio o motor de base de datos puede generar una identidad distinta para la misma entidad.

## Persistencia

SQLite:

```sql
id TEXT PRIMARY KEY
```

PostgreSQL:

```sql
id UUID PRIMARY KEY
```

Todas las claves foráneas funcionales deben almacenar UUID:

```sql
product_id TEXT NOT NULL
branch_id TEXT NOT NULL
sale_id TEXT NOT NULL
customer_id TEXT
reservation_id TEXT
```

## Migración obligatoria

La migración a UUID debe ejecutarse como un **corte total, global y atómico**:

1. cerrar la aplicación;
2. crear backup completo;
3. bloquear otras instancias;
4. abrir transacción exclusiva;
5. crear tablas nuevas con UUIDv7;
6. usar mapas temporales `old_id → uuid` solo durante la migración;
7. copiar y reescribir todas las PK y FK;
8. validar conteos y referencias;
9. eliminar tablas antiguas;
10. renombrar tablas nuevas;
11. ejecutar `PRAGMA foreign_key_check`;
12. confirmar la transacción;
13. eliminar mapas temporales;
14. iniciar únicamente con el esquema UUID.

Si algo falla:

- rollback;
- restaurar backup;
- bloquear el inicio normal;
- registrar el error.

No se permite dejar una migración parcial.

## Criterio de terminado

Un módulo no puede declararse migrado al 100% mientras:

- use IDs enteros;
- tenga PK o FK funcionales enteras;
- use `AUTOINCREMENT`;
- use `lastrowid`;
- convierta IDs con `int(...)`;
- exponga IDs enteros en UI, eventos o API;
- mantenga compatibilidad legacy;
- carezca de tests de integridad UUIDv7.

---

## 0. Propósito

Este archivo debe usarse como instrucción permanente para Codex durante la migración/refactor del repositorio.

El objetivo es transformar el proyecto en una arquitectura limpia, mantenible, preparada para:

- Desktop PyQt instalable como `.exe`
- Actualizaciones de versión
- SQLite actual
- PostgreSQL futuro
- API FastAPI futura
- Webapp futura
- Backend en inglés
- Frontend visible al usuario en español
- Cero SQL en UI
- Cero lógica de negocio en UI
- Cero rutas duplicadas para operaciones críticas
- Componentes UI estándar
- Módulos interconectados por Application Services + EventBus

---

## 1. Reglas maestras obligatorias

Estas reglas son no negociables.

**Prioridad absoluta:** la REGLA CERO de UUIDv7 prevalece sobre cualquier contrato, tabla o implementación existente.

1. Backend en inglés.
2. Frontend visible al usuario en español.
3. La app está en desarrollo: código muerto, duplicado o legacy inútil debe eliminarse.
4. No modificar lógica de negocio funcional sin pruebas de protección.
5. No romper flujos existentes.
6. No introducir regresiones.
7. SQLite actual, PostgreSQL futuro.
8. PyQt no debe ejecutar SQL.
9. PyQt no debe hacer `commit()` ni `rollback()`.
10. Servicios no deben crear ni alterar schema.
11. Solo `migrations/` puede modificar schema.
12. Toda operación crítica debe pasar por Use Case / Application Service.
13. Toda lectura para UI debe pasar por QueryService.
14. PyQt y futura API FastAPI deben usar los mismos Use Cases.
15. No pasar `AppContainer` completo a servicios.
16. Toda dependencia debe inyectarse explícitamente.
17. Toda mutación crítica debe emitir evento de dominio con `operation_id`.
18. Toda la app debe estar interconectada: ventas, inventario, caja, finanzas, fidelidad, delivery, WhatsApp, BI, compras, producción, merma, transferencias, tickets y notificaciones.
19. Todo teléfono debe usar estándar WhatsApp/E.164.
20. Donde se seleccione producto, cliente, proveedor, empleado, receta, activo, sucursal o repartidor debe usarse barra de búsqueda/autocomplete, no listas largas.
21. Donde se capture dirección debe usarse componente con API de mapas/autocomplete y fallback manual.
22. Todo campo numérico de captura debe iniciar en cero absoluto o vacío.
23. Prohibido usar defaults arbitrarios en UI como `1`, `7`, `10`, `30`, `50`, `100`.
24. Si un default funcional es necesario, debe venir desde `SystemSettingsService` o `ModuleSettingsService`.
25. El `.exe` debe permitir actualización de versiones.
26. Antes de actualizar versión debe hacerse backup automático de SQLite.
27. No usar rutas relativas sueltas; usar `AppPaths`.
28. No usar SQL exclusivo de SQLite en código nuevo si puede afectar PostgreSQL futuro.
29. No duplicar rutas para la misma operación.
30. Cada módulo refactorizado debe quedar cubierto por tests unitarios, integración, arquitectura y checklist manual.
31. Toda nueva carpeta del refactor (`backend/`, `frontend/`, `tests/`, `docs/`, etc.) debe crearse dentro de `pos_spj_v13.4/pos_spj_v13.4/`; está prohibido crear duplicados en la raíz externa del repositorio.
32. Toda entidad persistente y toda relación funcional debe usar UUIDv7 como única identidad.
33. SQLite almacena UUID como `TEXT`; PostgreSQL debe usar el tipo nativo `UUID`.
34. Está prohibido crear nuevas PK funcionales `INTEGER PRIMARY KEY AUTOINCREMENT`.
35. Está prohibido mantener `legacy_id`, escritura dual, lectura dual, fallback de UUID a entero o tablas paralelas de compatibilidad.
36. Está prohibido usar `lastrowid`, `MAX(id) + 1` o secuencias locales como identidad de dominio.
37. Está prohibido convertir identificadores de dominio con `int(product_id)`, `int(sale_id)`, `int(branch_id)` o equivalentes.
38. Folios, SKU, códigos de barras, números de ticket y códigos visibles no sustituyen al UUID.
39. Toda migración de identidad debe ser directa, global, atómica, respaldada y validada antes de iniciar la aplicación.
40. Toda entidad, Command, DTO, Use Case, QueryService, Repository, evento, outbox y futura API debe transportar UUID.
41. `operation_id`, `event_id` y `entity_id` son UUID distintos y no deben reutilizarse entre sí.
42. Un módulo no puede considerarse migrado mientras use IDs enteros o referencias funcionales enteras.

---

## 2. Arquitectura objetivo

```text
SPJ ERP
│
├── frontend/
│   └── desktop/
│       ├── modules/
│       ├── components/
│       ├── i18n/
│       └── themes/
│
├── backend/
│   ├── domain/
│   ├── application/
│   │   ├── use_cases/
│   │   ├── commands/
│   │   ├── dto/
│   │   ├── queries/
│   │   └── event_handlers/
│   ├── infrastructure/
│   │   ├── db/
│   │   ├── hardware/
│   │   ├── maps/
│   │   ├── printers/
│   │   ├── whatsapp/
│   │   └── updater/
│   ├── api/
│   └── shared/
│       ├── events/
│       ├── errors/
│       ├── result.py
│       ├── app_paths.py
│       └── ids.py
│
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── architecture/
│   └── e2e/
│
├── installer/
│   └── windows/
│
└── docs/
    └── architecture/
```

---

## 3. Principio central

```text
Una sola operación.
Una sola ruta canónica.
Una sola fuente de verdad.
```

---

## 4. Flujo obligatorio de trabajo

Codex debe trabajar en ciclos pequeños:

1. Leer este archivo completo.
2. Leer `docs/architecture/*` si existen.
3. Identificar archivos afectados.
4. Crear o actualizar tests de protección antes de tocar lógica crítica.
5. Extraer lecturas a QueryService.
6. Extraer mutaciones a Use Case / Application Service.
7. Conservar lógica de negocio funcional.
8. Eliminar código legacy solo cuando la ruta nueva esté cubierta por tests.
9. Ejecutar pruebas.
10. Reportar: archivos creados/modificados/eliminados, tests agregados, riesgos, regresiones, siguiente paso.

---

## 5. Fases del refactor

- FASE 0: Documentación base (`docs/architecture/`)
- FASE 1: Tests de arquitectura (`tests/architecture/`)
- FASE 2: Infraestructura base (`backend/shared/`, `backend/infrastructure/`, `backend/api/`)
- FASE 2.5: Corte total UUID (`backend/shared/ids.py`, migración atómica)
- FASE 3: Componentes UI estándar (`frontend/desktop/components/`)
- FASE 4: Event Catalog y contratos (`backend/shared/events/`)
- FASE 5: Query Services base (`backend/application/queries/`)
- FASE 6: Use Cases / Application Services (`backend/application/use_cases/`)
- FASE 7: Refactor por módulos (orden: config, merma, productos, cárnico, transferencias, delivery, caja, BI, compras, cotizaciones, fidelidad, activos, clientes, tickets, hardware, notificaciones, WhatsApp, finanzas, RRHH, compras, ventas)

---

## 6. Checklist obligatorio por módulo

```text
[ ] Backend en inglés.
[ ] UI en español.
[ ] Sin SQL en UI.
[ ] Sin commit/rollback en UI.
[ ] Sin schema changes fuera de migrations.
[ ] Sin AppContainer completo en servicios.
[ ] Sin listas largas para entidades.
[ ] Usa SearchSelector donde aplica.
[ ] Usa PhoneInput donde aplica.
[ ] Usa AddressInput donde aplica.
[ ] Campos numéricos en 0 o vacío.
[ ] Sin defaults arbitrarios hardcodeados.
[ ] Usa QueryService para lecturas.
[ ] Usa UseCase/ApplicationService para mutaciones.
[ ] Emite eventos con operation_id.
[ ] Compatible con SQLite/PostgreSQL.
[ ] Preparado para API futura.
[ ] Tests unitarios.
[ ] Tests de integración.
[ ] Tests de arquitectura.
[ ] Validación manual documentada.
[ ] Código legacy eliminado.
[ ] Todas las entidades usan UUIDv7 como única identidad.
[ ] Todas las FK funcionales usan UUID.
[ ] Sin PK `INTEGER AUTOINCREMENT`.
[ ] Sin `lastrowid` para identidad.
[ ] Sin casts `int(..._id)`.
[ ] Sin `legacy_id`, escritura dual o fallback.
[ ] Eventos, DTO, Commands, UseCases y API usan UUID.
[ ] Migración UUID validada con integridad referencial.
```

---

## 14. Frase de control

```text
No parchar.
No duplicar.
No ocultar legacy.
Un UUID por entidad.
Cero identidad dual.
Proteger, extraer, probar, eliminar.
```
