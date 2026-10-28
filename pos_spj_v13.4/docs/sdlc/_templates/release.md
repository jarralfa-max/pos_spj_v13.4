# <ID> — Liberación

- **Rama:** `sdlc/<id>` → `<rama base>`
- **Commits:** 
- **Nivel:** T0 | T1 | T2

## Qué cambia para el usuario

## Checklist pre-merge
- [ ] intent, spec y plan aprobados
- [ ] test-report sin fallos nuevos respecto a la línea base
- [ ] revisión independiente resuelta
- [ ] migraciones probadas sobre copia y con reversa documentada
- [ ] sin secretos, `.db` ni logs en el diff
- [ ] `MIGRATION_LOG.md` / documentación actualizada si aplica

## Instalación / actualización
¿Requiere nueva versión del instalador o del manifiesto de actualización? ¿Compatibilidad con terminales offline?

## Verificación posterior
Qué revisar en producción o en el piloto (logs, `scripts/health_check.py`, conteos) y quién lo hace.

## Plan de reversa

## Aprobación
- Merge aprobado por: ______ fecha: ______
- Release aprobado por (si aplica): ______ fecha: ______
