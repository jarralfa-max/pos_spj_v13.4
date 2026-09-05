# ASSET-10 — Costos, mejoras y capitalización propuesta (Activos / EAM)

Ejecutado: 2026-09-02. §30-31, §36, §68 (parcial) del prompt maestro.

## La pieza central de este bounded context

Este es el flujo que el prompt maestro (§31, §109) señala explícitamente como el que había que romper: el legacy `core/services/asset_service.py::capitalizar_mantenimiento()` hacía `UPDATE activos SET valor_adquisicion = valor_adquisicion + ...` — cambiaba el valor contable directo, sin workflow ni aprobación. El flujo correcto (§31):

```text
AssetImprovement → AssetCapitalizationProposal → aprobación de Finanzas → actualización del valor financiero → evento → proyección de Activos
```

## Qué se construyó

`backend/domain/assets/entities/asset_improvement.py` — `AssetImprovement` (§36). Puramente evidencial: `cost_reference` documenta lo gastado, pero la entidad nunca toca el valor contable del activo. `link_to_proposal()` es de una sola vez (una mejora no se vincula a dos propuestas).

`backend/domain/assets/entities/asset_capitalization_proposal.py` — `AssetCapitalizationProposal` (§30). Máquina de estados:

```text
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED → POSTED
                                 → REJECTED
DRAFT | SUBMITTED → CANCELLED
```

**`approve()`/`reject()`/`mark_posted()` solo REGISTRAN que llegó una decisión de Finanzas** — no llaman al motor de asientos ni a ningún servicio de finanzas/tesorería. Activos es dueño del registro de la propuesta; Finanzas es dueño del tratamiento contable real, ya construido y preservado en `backend/application/use_cases/finance/capital_and_asset_use_cases.py` (`CapitalizeAssetUseCase`). El diseño esperado es que la capa de aplicación de Activos (fase posterior) reaccione a un evento que Finanzas publica tras decidir, no que Finanzas llame directamente a este objeto de dominio.

Nuevo enum: `AssetCapitalizationProposalStatus`. Excepciones: `AssetImprovementNotFoundError`, `AssetCapitalizationProposalNotFoundError`, `AssetCapitalizationProposalInvalidError`. Eventos añadidos: `ASSET_CAPITALIZATION_UNDER_REVIEW`, `ASSET_CAPITALIZATION_POSTED`, `ASSET_CAPITALIZATION_CANCELLED` (los otros tres — PROPOSED/ACCEPTED/REJECTED — ya existían desde ASSET-3). Ports: `AssetImprovementRepositoryPort`, `AssetCapitalizationProposalRepositoryPort`.

## Iteración necesaria

Mismo tipo de falso positivo que en ASSET-1 y ASSET-4: el docstring original de `asset_capitalization_proposal.py` mencionaba literalmente "PostingEngine" para explicar la regla, lo que disparó `test_assets_do_not_post_journal_entries.py`. Se corrigió redactando la prosa sin el token literal ("el motor de asientos" en vez del nombre de la clase). **Patrón a recordar para fases futuras**: al documentar qué NO hace una entidad respecto a Finanzas/Tesorería, evitar los nombres literales que los guardrails buscan (`PostingEngine`, `treasury_service`, `registrar_asiento`, etc.) — describir la regla en prosa, no citar el símbolo prohibido.

## Tests

`tests/unit/assets/test_asset_capitalization.py` — mejora (costo no positivo falla, vincular dos veces falla), propuesta (monto no positivo falla, ciclo completo hasta POSTED, camino de rechazo, aprobar antes de revisión falla, postear antes de aprobar falla, cancelar desde DRAFT, cancelar estado terminal falla) y el mismo check explícito de "nunca toca finanzas/tesorería" que ya se usó para `MaintenanceWorkOrder`.

## Siguiente fase

ASSET-11 — Inventario físico.
