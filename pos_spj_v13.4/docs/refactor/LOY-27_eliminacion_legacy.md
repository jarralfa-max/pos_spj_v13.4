# LOY-27 — Eliminación de legacy

Fecha: 2026-08-31
Alcance: master prompt (fase LOY-27, "Eliminación de legacy: solo después de que el dominio nuevo
reemplace por completo la funcionalidad legacy").

## Veredicto principal: la condición de la propia fase NO se cumple todavía

La fase LOY-27, por su propio nombre y orden en el pipeline, exige que el dominio nuevo YA reemplace
completamente al legacy antes de borrar nada — la misma Prioridad 0 de CLAUDE.md ("❌ NO eliminar
funcionalidad operativa sin migración completa"). Se auditó cada pieza legacy identificada originalmente
en LOY-0 con evidencia FRESCA (no solo la memoria de esa auditoría), y la conclusión es inequívoca: **la
condición no se cumple**. `interfaz/main_window.py` sigue apuntando el menú real en vivo directamente al
legacy:

```
main_window.py:672-673
self._conectar("GROWTH_ENGINE",      ModuloFidelidadConfig, "⭐ Fidelización")
self._conectar("TARJETAS_FIDELIDAD", ModuloTarjetas,        "💳 Tarjetas Fidelidad")
```

Esto no es una decisión de esta fase — es una decisión YA tomada, explícitamente, en LOY-25 (ver
`docs/refactor/LOY-25_ui_ux.md`): los dos módulos PyQt5 nuevos existen y funcionan, pero deliberadamente
no se conectaron al menú real porque solo 9 de ~23 rutas tienen página funcional. Borrar el legacy ahora
eliminaría, sin reemplazo, funcionalidad que las personas usuarias siguen usando hoy a través de ese menú.

## Auditoría pieza por pieza (evidencia fresca, no solo memoria de LOY-0)

| Pieza legacy | ¿Referenciada hoy por el menú real? | Veredicto |
|---|---|---|
| `modulos/fidelidad_config.py` (`ModuloFidelidadConfig`) | Sí — `main_window.py:672`, wireado en vivo | **NO ELIMINAR.** Cubre metas/misiones/Growth Engine/referidos/cumpleaños/clientes en riesgo — ninguna de esas secciones tiene página real en el módulo nuevo todavía. |
| `modulos/tarjetas.py` (`ModuloTarjetas`) | Sí — `main_window.py:673`, wireado en vivo | **NO ELIMINAR.** Envuelve `modulos/loyalty_card_designer.py` (diseñador CR80 en vivo, config QR, generación de lote PDF) — el módulo nuevo (LOY-18/22) solo tiene un validador de esquema y renderizado de PDF, sin UI de diseño ni flujo de lote conectado a un botón real. |
| `modulos/loyalty_card_designer.py` | Sí — importado por `modulos/tarjetas.py`, 10 sitios de uso interno de `LoyaltyCardDesignerService` | **NO ELIMINAR** (mismo motivo que arriba). |
| `modulos/modulo_growth_engine.py` | Sí — importado en vivo por `modulos/fidelidad_config.py:138` (una pestaña de su interfaz unificada) | **NO ELIMINAR.** Se encontró y limpió una importación HUÉRFANA de este mismo módulo en `main_window.py` (líneas 1559-1562, un `try/except` a nivel de módulo, nunca usado, al final del archivo) — corregida esta fase; el archivo real (`modulos/modulo_growth_engine.py`) sigue vivo vía `fidelidad_config.py`. |
| `core/services/loyalty_service.py` | Sí, extensamente — `sales_loyalty_client.py`, `sales_sweepstakes_client.py`, `core/app_container.py`, `core/services/ventas_facade.py`, +15 archivos de test | **NO ELIMINAR.** 67 métodos, es el dueño real de las reglas de negocio de rifas legacy que `SalesSweepstakesClient` sigue invocando en producción (LOY-24 solo AGREGÓ el nuevo camino de sorteos, sin retirar este). |
| `core/services/loyalty_card_designer_service.py` | Sí — 10 sitios de importación inline dentro de `modulos/loyalty_card_designer.py` | **NO ELIMINAR** (mismo motivo). Nota de LOY-0: su propio docstring admite referenciar columnas legacy que ya fallan en runtime en ciertos flujos — sigue siendo "roto pero alcanzable desde el menú real", lo cual es peor para borrarlo sin reemplazo (produciría un `ImportError` inmediato en vez de una falla acotada a una acción específica). |
| `core/services/card_batch_engine.py` | **No** — ningún módulo de `modulos/` ni `core/services/loyalty_card_designer_service.py` lo importa | **NO ELIMINAR TODAVÍA, con reserva.** Huérfano de la UI en vivo, pero sigue cubierto por tests reales (`tests/integration/test_card_batch_engine_lifecycle.py`, `tests/architecture/test_clean_birth_guardrails.py`, `tests/test_card_subsystem_born_clean.py`, `tests/test_uuid_only_guard_rails.py`) — borrarlo exige también reconciliar esos 4 archivos de test, un cambio más invasivo que esta fase no debe apresurar sin confirmar primero que ningún script/CLI lo invoca dinámicamente. |
| `repositories/tarjetas.py` | **No** — solo se referencia a sí mismo y a `tests/test_card_subsystem_born_clean.py` | **NO ELIMINAR TODAVÍA**, misma reserva que `card_batch_engine.py`. |
| Tablas legacy Growth Engine (`raffles`, `raffle_tickets`, etc., migración 113) | Sí — `LoyaltyService.process_raffles_for_sale()` sigue escribiendo en ellas en cada venta con sorteo activo | **NO ELIMINAR.** Confirmado en LOY-15/LOY-24: coexisten deliberadamente con las tablas nuevas `sweepstakes_*` hasta que el nuevo dominio emita boletos automáticamente desde una venta (hoy solo otorga "derechos", LOY-24's propia brecha señalada). |

## La única limpieza seguramente correcta que se hizo esta fase

Una importación a nivel de módulo, completamente huérfana, al final de `interfaz/main_window.py`:

```python
try:
    from modulos.modulo_growth_engine import ModuloGrowthEngine
except Exception:
    ModuloGrowthEngine = None
```

Nunca se usaba en ningún otro punto de `main_window.py` (el archivo real `modulo_growth_engine.py` sigue
vivo e importado correctamente desde `modulos/fidelidad_config.py`, un punto de entrada completamente
distinto) — eliminar estas 4 líneas no cambia ningún comportamiento observable, verificado con un chequeo
de sintaxis limpio tras el cambio.

## Lo que realmente haría segura la eliminación (checklist concreto)

1. Completar las 14 rutas restantes de `frontend/desktop/modules/fidelidad/` y
   `frontend/desktop/modules/tarjetas_fidelidad/` marcadas como "en construcción" en LOY-25, con paridad
   funcional real frente al legacy (diseñador visual, generación de lote PDF conectada a un botón,
   configuración de niveles/retos/referidos/cumpleaños/campañas).
2. Migrar `SalesSweepstakesClient.issue_tickets_for_sale()` para emitir boletos reales (no solo derechos)
   desde el nuevo dominio `sweepstakes`, retirando la llamada a `LoyaltyService.process_raffles_for_sale()`.
3. Confirmar que ningún script/CLI invoca `core/services/card_batch_engine.py` o `repositories/tarjetas.py`
   dinámicamente, y entonces retirarlos junto con sus tests dedicados.
4. Solo entonces: cambiar `main_window.py:672-673` para apuntar `GROWTH_ENGINE`/`TARJETAS_FIDELIDAD` a
   `ModuloFidelidadEnterprise`/`ModuloTarjetasFidelidadEnterprise` (LOY-25's propios bridges, ya
   construidos y probados, solo no conectados) — el mismo patrón de corte que CRM-24 ya estableció en este
   mismo repositorio.
5. Después del corte, y solo después: borrar los archivos legacy listados arriba y las tablas
   `raffle_*`/Growth Engine legacy.

## Alcance honesto

- No se borró ningún archivo de negocio legacy esta fase — la condición de la fase misma lo prohíbe hoy.
- La única acción de "eliminación" real fue una importación huérfana de 4 líneas, verificada con sintaxis
  limpia.
- El checklist de arriba es el trabajo real pendiente antes de que una futura fase de eliminación sea
  segura — no un placeholder vacío.

## Tests

Ningún test nuevo (no se construyó funcionalidad nueva) — se verificó sintaxis limpia en todo el repo tras
el único cambio, y se corrió la batería completa de Fidelidad/Comercial/Sorteos/Tarjetas + UI para
confirmar cero regresiones.

## Pendiente para fases futuras

- LOY-28 (Validación final): auditoría UUIDv7/Decimal/SQL-en-UI/legacy, bootstrap limpio, verificación de
  allowlist — el trabajo real de "eliminación" queda documentado aquí como una decisión futura explícita,
  no ejecutada por esta sesión.
