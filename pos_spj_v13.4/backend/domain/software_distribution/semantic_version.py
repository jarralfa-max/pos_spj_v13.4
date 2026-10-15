"""Semantic Versioning 2.0.0 parsing and precedence.

Replaces the old updater comparator, which stripped every non-digit from each
dot segment: `13.4.0-rc1` became `(13, 4, 1)` and ranked ABOVE `13.4.0`, so a
release candidate could be offered as an "update" to the final release.

Precedence follows https://semver.org/#spec-item-11:

* MAJOR.MINOR.PATCH compare numerically;
* a version WITH a pre-release ranks below the same version without one;
* pre-release identifiers compare left to right — numeric ones numerically,
  alphanumeric ones lexically (ASCII), numeric < alphanumeric, and a shorter
  list ranks lower when all preceding identifiers are equal;
* build metadata (`+...`) is ignored for precedence and equality.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
import re

_NUMERIC = r"0|[1-9]\d*"
_PRERELEASE_ID = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
_PATTERN = re.compile(
    rf"^v?(?P<major>{_NUMERIC})\.(?P<minor>{_NUMERIC})\.(?P<patch>{_NUMERIC})"
    rf"(?:-(?P<pre>{_PRERELEASE_ID}(?:\.{_PRERELEASE_ID})*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class InvalidVersionError(ValueError):
    """The text is not a valid semantic version."""


@total_ordering
@dataclass(frozen=True, eq=False)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> "SemanticVersion":
        if not isinstance(text, str):
            raise InvalidVersionError(f"Versión inválida: {text!r}")
        match = _PATTERN.match(text.strip())
        if match is None:
            raise InvalidVersionError(f"Versión inválida: {text!r} (se espera MAYOR.MENOR.PARCHE)")
        pre = match.group("pre")
        build = match.group("build")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=tuple(pre.split(".")) if pre else (),
            build=tuple(build.split(".")) if build else (),
        )

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def windows_file_version(self) -> str:
        """Four-part numeric version for PE resources / Inno `VersionInfoVersion`.

        Windows file versions cannot express a pre-release, so it is dropped;
        the full semantic version travels in the product-version string.
        """
        return f"{self.major}.{self.minor}.{self.patch}.0"

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text

    # ── precedence ────────────────────────────────────────────────────────
    def _precedence_key(self):
        if not self.prerelease:
            # No pre-release outranks any pre-release of the same core.
            return (self.core, 1, ())
        identifiers = tuple(
            (0, int(item), "") if item.isdigit() else (1, 0, item)
            for item in self.prerelease
        )
        return (self.core, 0, identifiers)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._precedence_key() == other._precedence_key()

    def __lt__(self, other: "SemanticVersion") -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._precedence_key() < other._precedence_key()

    def __hash__(self) -> int:
        return hash(self._precedence_key())
