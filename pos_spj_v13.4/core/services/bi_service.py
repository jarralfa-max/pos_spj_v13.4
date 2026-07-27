# core/services/bi_service.py
"""BIService — orquesta consultas de Business Intelligence."""
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class BIService:

    def __init__(self, repo, feature_flag_service=None):
        self.repo = repo
        self.feature_flag_service = feature_flag_service

    def ranking_cajeros(
        self,
        sucursal_id: int,
        rango: str = "mes",
        limite: int = 20,
    ) -> list:
        """Delegación al repo con resolución de rango temporal."""
        hoy = date.today().isoformat()
        if rango == "hoy":
            fi = ff = hoy
        elif rango == "semana":
            fi = (date.today() - timedelta(days=7)).isoformat()
            ff = hoy
        else:
            # mes (default para rangos no reconocidos)
            fi = date.today().replace(day=1).isoformat()
            ff = hoy
        return self.repo.get_ranking_cajeros(sucursal_id, fi, ff, limite=limite)
