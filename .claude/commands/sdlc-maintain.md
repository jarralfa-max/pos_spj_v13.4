---
description: "SDLC etapa 6 — Maintain: salud de la app, incidentes y regresiones → nuevos intents (uso: /sdlc-maintain [área|incidente])"
argument-hint: "[área | descripción de incidente]"
---

Etapa **Maintain**. Cierra el ciclo: lo que falle en operación se convierte en intents nuevos. Argumento opcional: `$ARGUMENTS`. No modificas código de producción en esta etapa.

## Trabajo

1. **Liberados recientes.** En `BACKLOG.md`, revisa los ítems `liberado` desde la última ejecución y su sección "Verificación posterior" de `release.md`. Pregúntame por lo que solo yo puedo observar en sucursal.
2. **Señales de salud** (desde `pos_spj_v13.4/`, siempre sobre una **copia** de la base en el scratchpad, nunca la real):
   - `python scripts/health_check.py`, `python scripts/validate_system_integrity.py`, `python scripts/nightly_integrity_check.py`, `python scripts/check_inventory_projection_drift.py`, `python scripts/audit_migrations.py` (revisa su `--help` antes; omite los que necesiten una BD que no tengas y dilo).
   - Logs: busca `ERROR`, `CRITICAL`, `Traceback` en los logs más recientes de `logs/` y agrúpalos por causa.
   - Regresión: `python -m pytest tests/architecture -q` y los segmentos de las áreas liberadas; compara con la última línea base de `docs/sdlc/baseline/`.
3. **Incidente puntual.** Si `$ARGUMENTS` describe un incidente, diagnostica la causa con evidencia (código + log + reproducción en prueba).
4. **Regresiones permanentes.** Cada incidente real confirmado debe terminar con una prueba que lo reproduzca; propónla en el intent (se implementa en Build) bajo `tests/regression/incidents/`.
5. **Nuevos intents.** Por cada problema: busca duplicados en el backlog; crea `docs/sdlc/items/<ID>/intent.md` (origen `maintain` o `incidente`) y su fila con prioridad y nivel.
6. Guarda el resumen en `docs/sdlc/baseline/<fecha>-maintain.md`. Commit `sdlc(maintain): …` solo de `docs/sdlc/`.

## Al terminar

Estado de salud en pocas líneas, intents nuevos con prioridad, y la sugerencia de qué ítem abordar después.
