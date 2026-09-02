"""SET-18 — "Content": Content entity. Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.enums import ContentType
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import is_uuidv7


def _content(**overrides) -> Content:
    kwargs = dict(title="Promo Verano", content_type=ContentType.IMAGE, body="base64...")
    kwargs.update(overrides)
    return Content.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_defaults(self):
        content = _content()
        assert is_uuidv7(content.id)
        assert content.duration_seconds == 10
        assert content.active is True

    def test_requires_title(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _content(title="   ")

    def test_requires_body(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _content(body="   ")

    @pytest.mark.parametrize("duration", [0, -1, 1.5, True])
    def test_rejects_invalid_duration(self, duration):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _content(duration_seconds=duration)

    @pytest.mark.parametrize(
        "content_type", [ContentType.IMAGE, ContentType.VIDEO, ContentType.TEXT, ContentType.HTML],
    )
    def test_accepts_every_content_type(self, content_type):
        content = _content(content_type=content_type)
        assert content.content_type is content_type


class TestActivateDeactivate:
    def test_activate_deactivate(self):
        content = _content()
        content.deactivate()
        assert content.active is False
        content.activate()
        assert content.active is True


class TestUpdateDetails:
    def test_updates_title_body_duration(self):
        content = _content()
        content.update_details(title="Promo Invierno", body="nuevo...", duration_seconds=20)
        assert content.title == "Promo Invierno"
        assert content.body == "nuevo..."
        assert content.duration_seconds == 20

    def test_requires_title(self):
        content = _content()
        with pytest.raises(CustomerDisplayInvalidValueError):
            content.update_details(title="   ", body="x", duration_seconds=10)

    def test_requires_body(self):
        content = _content()
        with pytest.raises(CustomerDisplayInvalidValueError):
            content.update_details(title="x", body="   ", duration_seconds=10)

    @pytest.mark.parametrize("duration", [0, -1, 1.5, True])
    def test_rejects_invalid_duration(self, duration):
        content = _content()
        with pytest.raises(CustomerDisplayInvalidValueError):
            content.update_details(title="x", body="y", duration_seconds=duration)
