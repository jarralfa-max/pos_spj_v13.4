# LOY-1 — Seguridad (Fidelidad/Loyalty + Loyalty Cards)

Fecha: 2026-08-28
Alcance: master prompt §59-61 (Permisos, Segregación, Auditoría) + §4 (frontera del bounded context).
Precede a cualquier entidad de dominio real (LOY-2+) — mismo orden que CASH-1/CRM-2/SALES-2.

## Qué se construyó

Dos fundaciones de seguridad paralelas, una por bounded context, porque el master prompt (§30, §60) trata
"Tarjetas de fidelidad" como subdominio especializado con su propia navegación y sus propios roles de
segregación de funciones (Diseñador de tarjetas, Aprobador de plantillas, Operador de impresión — distintos de
Operador de fidelidad/Administrador de campañas):

### Fidelidad (`GROWTH_ENGINE`)
- `backend/domain/loyalty/exceptions.py` — `LoyaltyDomainError` + errores de seguridad.
- `backend/domain/loyalty/value_objects/{authorization_grant,loyalty_audit_entry}.py`.
- `backend/application/loyalty/permissions.py` — `LoyaltyPermissions`, ~50 códigos granulares (programas,
  membresías, puntos, niveles, recompensas, retos, referidos, cumpleaños, retención, campañas, cupones, vales,
  sorteos, antifraude, configuración).
- `backend/application/loyalty/{authorization,session_authorization,audit}.py`.

### Loyalty Cards (`TARJETAS_FIDELIDAD`)
- `backend/domain/loyalty_cards/exceptions.py` + `value_objects/{authorization_grant,card_audit_entry}.py`.
- `backend/application/loyalty_cards/permissions.py` — `LoyaltyCardsPermissions`, ~25 códigos (tarjetas,
  plantillas, diseñador, formatos, pliegos, lotes, reimpresión, QR, auditoría, configuración).
- `backend/application/loyalty_cards/{authorization,session_authorization,audit}.py`.

Ambos mirroran exactamente `backend/application/sales/{permissions,authorization,session_authorization,audit}.py`
(SALES-2): `PermissionChecker` Protocol, `AllowAll.../DenyAll...ForTests`, `require()`/`has_permission()` fail
closed sin checker, `authorize_exception()` con autorizador obligatoriamente distinto del solicitante
(`SegregationOfDutiesError`), y persistencia de auditoría reutilizando el sink existente
`core.services.auto_audit.audit_write` (sin tabla paralela).

## Decisión de catálogo (aplica [[feedback_permissions_compras_standard]])

Se extendieron las dos claves YA existentes en `CANONICAL_MODULE_PERMISSIONS` (`GROWTH_ENGINE` y
`TARJETAS_FIDELIDAD`, ligadas a los botones reales del menú lateral "⭐ Fidelización"/"💳 Tarjetas Fidelidad")
en vez de crear claves paralelas `FIDELIDAD`/`LOYALTY`. El código plano original `"ver"` se conserva en ambas
por compatibilidad. Test `test_no_fidelidad_parallel_module_key_was_created` bloquea que alguien reintroduzca
una clave paralela en el futuro.

## Wiring real (no solo declarado)

`core/app_container.py` ahora construye `self.loyalty_authorization_policy` y
`self.loyalty_cards_authorization_policy`, cada uno con su propio `*SessionPermissionChecker(self.session)` —
el mismo patrón de sesión viva usado por `customer_authorization_policy`/`sales_authorization_policy`. Verificado
con una construcción real de `AppContainer` contra una base bootstrapeada desde cero (no solo un test aislado).

**Explícitamente NO hecho, señalado no oculto**: ni `modulos/fidelidad_config.py` ni
`modulos/loyalty_card_designer.py` llaman todavía a estas políticas — se confirmó (grep) que ninguno de los dos
tenía un check de rol hardcodeado tipo `{"admin","gerente"}` que reemplazar (a diferencia de
`modulos/ventas.py` en SALES-2), así que no hay una corrección "real y contenida" equivalente que aplicar en
esta fase. Hoy ambos módulos legacy siguen gateados únicamente por el permiso plano de visibilidad
(`GROWTH_ENGINE.ver`/`TARJETAS_FIDELIDAD.ver`) vía el menú lateral — sin distinción granular interna. Las
fases LOY-2+ (que construirán los casos de uso reales) serán quienes efectivamente llamen
`require()`/`authorize_exception()`. Ningún rol tiene sembrados los códigos granulares nuevos
(`_seed_system_roles` no fue tocado) — mismo criterio ya establecido en SALES-2/COMPRAS: nunca auto-otorgar
una acción granular nueva, un admin debe concederla explícitamente vía Configuración → Seguridad → Permisos.

## Tests

40 tests nuevos, todos pasando:
- `tests/unit/test_loyalty_security.py` (18) y `tests/unit/test_loyalty_cards_security.py` (13) — política,
  autorización en caliente, segregación de funciones, value objects de auditoría.
- `tests/architecture/test_loyalty_permissions_are_granular.py` (5) y
  `tests/architecture/test_loyalty_cards_permissions_are_granular.py` (4) — granularidad, prefijo de catálogo,
  sin duplicados, registro 1:1 en `permission_catalog.py`, sin clave paralela.

Regresión dirigida (permission-catalog/menu/BI): 17/18 pasan; la única falla
(`test_permission_catalog_matches_menu_modules.py::test_permission_catalog_has_all_menu_modules`) es
preexistente y no relacionada — usa una ruta relativa hardcodeada (`Path("pos_spj_v13.4/interfaz/menu_lateral.py")`)
que solo resuelve si pytest se invoca un nivel arriba de la raíz real del repo; confirmado reproduciendo el
mismo fallo con `git stash` (revierte todo este trabajo) aplicado — la ruta apunta a una tercera copia anidada
fantasma que no existe en disco, documentada ya en memoria (`env_nested_git_repo_pos_spj`), no algo introducido
aquí.

## Pendiente para fases futuras

- LOY-2 (dominio base: programas/cuentas/membresías/ledger) es el primer consumidor real de
  `LoyaltyAuthorizationPolicy.require()`.
- LOY-16+ (tarjetas) será el primer consumidor real de `LoyaltyCardsAuthorizationPolicy`.
- Ningún rol tiene otorgados los nuevos permisos granulares todavía — verificar con el usuario/administrador
  antes de asumir que cualquier rol existente podrá operar los nuevos flujos sin configuración adicional.
