# LOY-25 — UI/UX

Fecha: 2026-08-31
Alcance: master prompt §63-65 (Sidebar, ~35 páginas, Design System), fase LOY-25.

## Alcance real entregado, no las ~35 páginas completas

Esta fase construyó DOS módulos PyQt5 nuevos y completos —
`frontend/desktop/modules/fidelidad/` (Loyalty + Commercial Instruments + Sweepstakes, reflejando el
menú legacy "⭐ Fidelización" / `GROWTH_ENGINE`) y `frontend/desktop/modules/tarjetas_fidelidad/`
(Loyalty Cards, reflejando "💳 Tarjetas Fidelidad" / `TARJETAS_FIDELIDAD`) — con **9 páginas reales,
funcionales y verificadas contra una base de datos real** (Resumen/Programas/Perfil de miembro/
Recompensas/Cupones/Vales/Sorteos en Fidelidad; Resumen/Tarjetas/Plantillas en Tarjetas Fidelidad) y
**14 rutas adicionales declaradas** como marcadores de posición navegables (`ViewState.EMPTY`), listas
para que fases futuras las completen una por una — el mismo patrón de construcción incremental que
`customers_crm` (10 fases) y `orders_delivery` ya establecieron en este mismo repositorio, no un atajo
inventado para esta fase.

## Investigación de convenciones ANTES de escribir código

Antes de crear ningún archivo se investigó a fondo `frontend/desktop/modules/customers_crm/` (el módulo
más maduro del repo) para entender: la forma exacta de un composition root ("nunca recibe el contenedor
completo de la app", solo `connection`/`session_context` ya desempaquetados), el patrón Presenter
(diccionarios `query_services`/`command_handlers` inyectados, degradar a un resultado seguro cuando algo
no está conectado en vez de lanzar una excepción), el shell de navegación (`PageHeader` + `SideNav` +
`QStackedWidget`, rutas declaradas con capacidades gruesas por grupo), y el punto de entrada real hacia
la app (`interfaz/main_window.py::_conectar()` + un archivo puente en `modulos/`). Todo lo construido
aquí sigue esa forma exactamente, sin inventar un patrón nuevo.

## Descubrimiento real: no había capa de lectura (query services) construida

Las 24 fases anteriores (LOY-1..24) construyeron una capa de ESCRITURA completa y rigurosa (casos de uso
con permisos, validación de dominio, eventos) pero ningún query service de lectura tipo "directorio"/
"perfil 360" — los repositorios solo tenían los métodos que sus propios casos de uso necesitaban
(`get`/`get_by_code`/`list_active`/`list_for_account`, etc.), no un "listar todo para mostrar en una
tabla". Se construyó `backend/application/loyalty/queries/member_profile_query_service.py`
(`LoyaltyMemberProfileQueryService`) — un ensamblado de solo lectura sobre repositorios YA EXISTENTES
(cuenta, membresías, saldo vía `LoyaltyBalancePolicy` ya construida en LOY-2, recompensas disponibles),
mismo rol que `Customer360QueryService` cumple para Clientes. No se tocó ningún repositorio existente
para construir esto — todos los métodos que usa ya existían.

## Decisión deliberada: construido pero NO conectado al menú real todavía

Ambos módulos son completamente instanciables, probados de punta a punta contra una base de datos SQLite
real (no solo con dobles de prueba) — pero **`interfaz/main_window.py` sigue apuntando a los módulos
legacy** (`ModuloFidelidadConfig`/`ModuloTarjetas`) para los códigos `GROWTH_ENGINE`/`TARJETAS_FIDELIDAD`.
Se creó `modulos/fidelidad_enterprise.py`/`modulos/tarjetas_fidelidad_enterprise.py` (mismo puente que
`modulos/clientes_crm.py`) pero deliberadamente NO se modificó `_conectar()` en `main_window.py`.

**Por qué**: de las ~23 rutas totales entre ambos módulos, solo 9 tienen página real — cambiar el menú
real HOY reemplazaría pantallas legacy que sí funcionan (aunque con lógica de negocio mezclada con SQL)
por un módulo nuevo donde la mayoría de las secciones muestran "en construcción". Eso sería una
regresión real y visible de funcionalidad para cualquier persona que hoy usa "Configurar cumpleaños",
"Diseñador de tarjetas", etc. — exactamente lo que la Prioridad 0 de CLAUDE.md prohíbe ("❌ NO eliminar
funcionalidad operativa sin migración completa"). El precedente de este mismo repositorio (CRM: `main_window.py:648-652`
documenta que el corte real de Clientes solo ocurrió en CRM-24, después de que el nuevo módulo ya cubría
el reemplazo funcional) confirma que "construir" y "cortar" son decisiones separadas — esta fase hizo la
primera; la segunda queda para cuando la cobertura de páginas lo justifique, o para una decisión explícita
del usuario.

## Qué se construyó (por módulo)

**Fidelidad** (`frontend/desktop/modules/fidelidad/`): `composition.py` (17 casos de uso reales
conectados: programas, puntos, recompensas, cupones, vales, sorteos), `fidelidad_presenter.py`,
`fidelidad_routes.py` (15 rutas, 6 con página real), `fidelidad_workspace.py`, y páginas
`overview_page.py`/`programs_page.py`/`member_profile_page.py`/`rewards_page.py`/
`coupons_vouchers_page.py`/`sweepstakes_page.py`.

**Tarjetas Fidelidad** (`frontend/desktop/modules/tarjetas_fidelidad/`): `composition.py` (9 casos de uso
reales: tarjetas + plantillas), `tarjetas_fidelidad_presenter.py`, `tarjetas_fidelidad_routes.py` (8
rutas, 3 con página real), `tarjetas_fidelidad_workspace.py`, y páginas
`overview_page.py`/`cards_page.py`/`templates_page.py`.

Se agregaron dos íconos nuevos al catálogo compartido (`frontend/desktop/components/icons.py`):
`Icons.LOYALTY`/`Icons.LOYALTY_CARDS` — cambio aditivo, sin tocar ningún ícono existente.

## Verificación real, no solo unitaria

Cada flujo completo se verificó dos veces: (1) un script de humo manual contra SQLite real ANTES de
escribir ningún test formal (creación de programa → aprobar → activar → inscribir membresía → acreditar
puntos → ver saldo actualizado; campaña de sorteo → aprobar → activar → agregar premio → otorgar derecho
→ emitir boleto; emisión de cupón; emisión/activación/bloqueo/desbloqueo de tarjeta; plantilla → versión →
aprobar → activar), y (2) los mismos flujos formalizados como tests de integración reales
(`tests/integration/test_fidelidad_composition_root.py`,
`tests/integration/test_tarjetas_fidelidad_composition_root.py`).

## Bug real encontrado por el propio script de humo (no por revisión)

El primer intento del script de verificación usó una sesión simulada SIN el atributo `is_active` —
`LoyaltySessionPermissionChecker`/`LoyaltyCardsSessionPermissionChecker` (LOY-1) niegan el permiso por
defecto cuando falta ese atributo (fail closed, por diseño). El fallo resultante ("el usuario no tiene el
permiso GROWTH_ENGINE.programa.crear") confirmó — de la forma más directa posible — que la cadena
completa de autorización de sesión real (no solo un doble de prueba permisivo) efectivamente bloquea una
sesión inválida de punta a punta a través de la UI nueva. Corregido en el script de prueba, no en el
código de la aplicación.

Un segundo hallazgo real (esperado, no un bug): aprobar una campaña de sorteo con el MISMO usuario que la
creó fue rechazado por la regla de segregación de funciones de LOY-15 — confirmando que esa regla de
negocio se respeta correctamente incluso cuando se invoca desde la UI nueva, no solo desde un test aislado
del backend.

## Alcance honesto

- 14 rutas totales quedan como marcador de posición: Niveles, Retos, Referidos, Cumpleaños, Campañas,
  Sorteo y Ganadores, Antifraude, Configuración (Fidelidad); Tarjeta digital, Diseñador, Pliegos, Lotes,
  Impresión (Tarjetas Fidelidad).
- `MemberProfilePage`/`RewardsPage`/páginas de Cupones/Vales/Tarjetas piden un `customer_id`/
  `card_number`/`definition_id` como texto plano — ningún selector de búsqueda (`CustomerSearchBox` u
  homólogo) está conectado; ese componente exige su propio `SearchProvider` contra Customer Master, fuera
  de alcance de esta fase.
- `AdjustLoyaltyPointsUseCase` (ajuste de puntos con doble autorización) no tiene página — su flujo de
  autorización en caliente con un segundo usuario no tiene todavía un patrón de diálogo establecido en
  este repositorio para replicar.
- Ningún test de arquitectura tipo "CRM-1" (sin SQL en UI, sin estilos inline, rutas estables) se escribió
  para estos dos módulos nuevos — se verificó manualmente (grep) que ninguna de las dos reglas se viola,
  pero no quedó codificado como guardrail automatizado.
- El corte real hacia el menú en vivo (`main_window.py`) no se hizo — ver la sección de arriba.

## Tests

26 tests nuevos: `test_fidelidad_presenter.py` (9), `test_fidelidad_workspace.py` (3),
`test_tarjetas_fidelidad_presenter.py` (5), `test_tarjetas_fidelidad_workspace.py` (3),
`test_fidelidad_composition_root.py` (4, integración real), `test_tarjetas_fidelidad_composition_root.py`
(2, integración real) — todos pasando en el primer intento real (tras la corrección del script de humo,
no del código). 562 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas + UI corridos juntos,
sin regresión. Sintaxis limpia en todo el repo.

## Pendiente para fases futuras

- Completar páginas reales para las 14 rutas restantes (una por fase, mismo ritmo que `customers_crm`).
- Selector de búsqueda de cliente real (requiere un `SearchProvider` contra Customer Master).
- Diálogo de doble autorización para ajuste de puntos.
- Decisión explícita de corte hacia el menú real (`main_window.py`) cuando la cobertura lo justifique.
- LOY-26 (Antifraude), LOY-27 (Eliminación de legacy — el legacy sigue intacto y en vivo hoy), LOY-28
  (Validación final).
