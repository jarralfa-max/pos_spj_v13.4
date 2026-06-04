"""Waste module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class RegisterWasteCommand(BaseCommand):
    pass
