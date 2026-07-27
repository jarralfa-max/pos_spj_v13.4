from unittest.mock import MagicMock

from core.services.production_application_service import ProductionApplicationService


def test_batch_flow_methods_are_available_for_real_meat_processing():
    recipe = MagicMock()
    uc = MagicMock()
    engine = MagicMock()
    svc = ProductionApplicationService(recipe_engine=recipe, production_uc=uc, production_engine=engine)

    svc.abrir_lote(1, 10.0, 1, "u", receta_id=5)
    svc.agregar_subproducto("B1", 2, 6.2, expected_pct=0.0, is_waste=False)
    svc.preview_lote("B1")
    svc.cerrar_lote("B1", 1, "u")

    uc.abrir_lote.assert_called_once()
    engine.add_output.assert_called_once()
    engine.preview_batch.assert_called_once_with("B1")
    uc.cerrar_lote.assert_called_once_with(batch_id="B1", sucursal_id=1, usuario="u")

