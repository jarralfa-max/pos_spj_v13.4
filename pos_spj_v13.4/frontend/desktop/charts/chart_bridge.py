"""Bridge ChartDataDTO objects into the canonical HTML chart template."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.application.dto.charts import ChartDataDTO


class ChartBridge:
    """Render QueryService chart DTOs as safe HTML payloads for JavaScript renderers."""

    _BASE_DIR = Path(__file__).resolve().parent
    _TEMPLATE = _BASE_DIR / "templates" / "chart_base.html"
    _RENDERER = _BASE_DIR / "renderers" / "echarts_renderer.js"

    @classmethod
    def render(cls, chart: ChartDataDTO) -> str:
        template = cls._TEMPLATE.read_text(encoding="utf-8")
        renderer = cls._RENDERER.read_text(encoding="utf-8")
        payload = json.dumps(cls._to_jsonable(chart), ensure_ascii=False, sort_keys=True)
        return template.replace("{{CHART_PAYLOAD}}", payload).replace("{{ECHARTS_RENDERER}}", renderer)

    @classmethod
    def _to_jsonable(cls, value: Any) -> Any:
        if is_dataclass(value):
            return {field.name: cls._to_jsonable(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, tuple):
            return [cls._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): cls._to_jsonable(item) for key, item in value.items()}
        if hasattr(value, "items"):
            return {str(key): cls._to_jsonable(item) for key, item in value.items()}
        return value
