"""Forecast: dependencias ausentes producen mensaje claro, no crash críptico."""
from __future__ import annotations

import pytest

import core.services.forecast_service as fs_module
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def test_missing_statsmodels_raises_clear_message(monkeypatch):
    conn = make_db()
    monkeypatch.setattr(fs_module, "pd", object())          # pandas presente
    monkeypatch.setattr(fs_module, "ExponentialSmoothing", None)
    svc = fs_module.ForecastService(conn)
    with pytest.raises(RuntimeError, match="statsmodels"):
        svc.generar_plan_compras(new_uuid(), new_uuid(), 30, 7, 5.0)


def test_missing_pandas_raises_clear_message(monkeypatch):
    conn = make_db()
    monkeypatch.setattr(fs_module, "pd", None)
    svc = fs_module.ForecastService(conn)
    with pytest.raises(RuntimeError, match="pandas"):
        svc.generar_plan_compras(new_uuid(), new_uuid(), 30, 7, 5.0)


def test_blank_uuid_ids_rejected(monkeypatch):
    conn = make_db()
    monkeypatch.setattr(fs_module, "pd", object())
    monkeypatch.setattr(fs_module, "ExponentialSmoothing", object())
    svc = fs_module.ForecastService(conn)
    with pytest.raises(ValueError, match="UUID"):
        svc.generar_plan_compras("", new_uuid(), 30, 7, 5.0)
