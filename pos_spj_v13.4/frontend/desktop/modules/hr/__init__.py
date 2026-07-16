"""Canonical desktop HR module."""

from __future__ import annotations

__all__ = ["HRView"]


def __getattr__(name: str):
    if name == "HRView":
        from .hr_view import HRView

        return HRView
    raise AttributeError(name)
