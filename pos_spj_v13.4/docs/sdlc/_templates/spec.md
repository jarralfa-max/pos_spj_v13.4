# <ID> — Especificación

- **Intent:** `items/<ID>/intent.md` (aprobado el <fecha>)
- **Nivel:** T0 | T1 | T2
- **Estado:** borrador | aprobado (fecha, por)

## Comportamiento esperado
Reglas de negocio y casos, incluidos los bordes (offline, concurrencia, reintento, permisos, multi-sucursal).

## Diseño
- Bounded context(s) y capas afectadas (`domain/`, `application/`, `infrastructure/`, `ui/`).
- Componentes existentes que se reutilizan (ruta) y por qué no se crea uno nuevo.
- Contratos: casos de uso, DTO, eventos, endpoints (nombre, entrada, salida, errores).
- Flujo de datos (diagrama Mermaid si ayuda).

## Datos y migraciones
Cambios de esquema SQLite/PostgreSQL, compatibilidad con datos existentes, plan de reversa.

## Seguridad y auditoría
Permisos requeridos (módulo/acción/ámbito), validación en backend, qué se registra en auditoría.

## Criterios de aceptación
Lista numerada; cada criterio se traduce en al menos una prueba que verifica efectos reales (BD, idempotencia, autorización, trazabilidad).

## Riesgos y alternativas descartadas

## Decisiones que requieren aprobación
