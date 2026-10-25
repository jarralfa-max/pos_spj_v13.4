# 00 — Línea base del repositorio

**Fecha:** 2026-10-23 · **Fase:** 0 (auditoría; sin cambios de código).

## Estado de Git (medido)

| Dato | Valor |
|---|---|
| Raíz | `C:/Users/Diego Rodriguez/Downloads/pos_spj_v13.4` (el `.git` real; ojo: `pos_spj_v13.4/pos_spj_v13.4/` tiene un `.git` anidado ajeno) |
| Rama | `claude/erp-financial-bounded-context-uqxz6b` |
| HEAD | `0495f56cc48afee9eddaba1760dc21fecd399bb8` |
| Divergencia con `origin/<rama>` | 0 adelante / 0 atrás (tras `git fetch`) |
| Archivos sin commitear | **567** (354 modificados, 19 borrados, 194 nuevos) |
| `main` | Historia **no relacionada** (no hay merge-base); 24 commits propios con la arquitectura heredada (`modulos/`, `interfaz/`, `core/`) |

Los 567 archivos sin commitear son trabajo de rondas de auditoría previas (PERM-AUD 968e0bc, FID 968e0bc sin cerrar, FIN-ERP, TICKET-AUD, CASH-AUD, LOG-INT…). **No se descartan ni se sobrescriben.** Esta fase sólo agrega documentos en esta carpeta.

## Bloqueos y conflictos detectados

1. **Ronda de Fidelidad 968e0bc sin cerrar.** Sus cambios dejan rojas pruebas ajenas a esta migración (canje → `MARGIN_PROTECTED`, `checkout_use_cases.py` −93 líneas, costo promedio de Procesamiento). No impide auditar; sí impide declarar «verde» cualquier slice que toque Ventas hasta cerrarla.
2. **`tests/ui/test_module_workspace_layout.py`** tiene un error de sintaxis por una edición sin commitear ajena.
3. **Paquetes borrados que algunas pruebas aún importan** (`core`, `repositories`, `modulos`, `sync`): ~20 pruebas no colectan. Preexistente.

## Documentación previa que esta carpeta NO duplica

El modelo híbrido ya está *propuesto* (no implementado) en:

- `docs/product/MASTER_BLUEPRINT.md` — «SQLite local por instalación/sucursal… servicio central con PostgreSQL… La elección de PostgreSQL central es **propuesta**».
- `docs/product/TRD.md` §6 (offline y consistencia), §9 (núcleo central y sincronización), §10 (contratos HTTP por área).
- `docs/product/BACKEND_SCHEMA.md` (tipos en PostgreSQL: UUID, NUMERIC por dominio, timestamptz).
- `docs/architecture/DATABASE_COMPATIBILITY.md` (reglas de SQL portable, ya vigentes).

Esta carpeta es la **auditoría contra el código real** y el plan de ejecución; las especificaciones funcionales siguen viviendo en `docs/product/`.

## Entorno de esta auditoría

Windows 11, Python 3.13, sin Docker ni PostgreSQL instalados en la estación. Todas las mediciones de esquema se hicieron sobre una **copia** de `data/spj_pos_database.db` (la base real no se modificó).
