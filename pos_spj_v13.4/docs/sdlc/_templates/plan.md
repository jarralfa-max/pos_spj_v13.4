# <ID> — Plan de implementación

- **Spec:** `items/<ID>/spec.md` (aprobado el <fecha>)
- **Rama:** `sdlc/<id>` desde `<rama base>` @ `<commit>`
- **Estado:** borrador | aprobado (fecha, por)

## Línea base
Comando(s) de prueba ejecutados antes de cambiar nada y su resultado real (incluidos fallos previos).

## Pasos
| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | | Prueba de regresión que fija el comportamiento actual | `python -m pytest …` falla/pasa como se espera |
| 2 | | | |

## Archivos que NO se tocan
Y por qué (shims intencionales, legacy fuera de alcance, etc.).

## Migraciones
Script, cómo se prueba sobre copia, cómo se revierte.

## Criterio de terminado
Mapeo criterio de aceptación → prueba.
