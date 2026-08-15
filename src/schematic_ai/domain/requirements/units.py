"""Deterministic unit spelling normalization for ingestion boundaries.

This module does not perform physical unit conversion. It only maps known
aliases such as "volts" to the canonical spelling "V".
"""

from __future__ import annotations

from schematic_ai.domain.requirements.validation import require_nonblank


class UnitNormalizationError(ValueError):
    """Raised when a raw unit cannot be normalized to a trusted spelling."""


_UNIT_ALIASES = {
    "v": "V",
    "volt": "V",
    "volts": "V",
    "a": "A",
    "amp": "A",
    "amps": "A",
    "ampere": "A",
    "amperes": "A",
    "ma": "mA",
    "milliamp": "mA",
    "milliamps": "mA",
    "milliampere": "mA",
    "milliamperes": "mA",
    "w": "W",
    "watt": "W",
    "watts": "W",
    "ohm": "ohm",
    "ohms": "ohm",
    "khz": "kHz",
    "mhz": "MHz",
    "celsius": "degC",
    "degc": "degC",
    "°c": "degC",
}


def normalize_unit(raw_unit: str) -> str:
    """Return a canonical unit spelling for a known alias.

    Unknown nonblank units raise ``UnitNormalizationError``. The canonical
    ``RequirementModel`` still stores unit strings, but ingestion layers must
    explicitly normalize raw user/LLM spellings before canonicalization.
    """

    try:
        normalized_input = require_nonblank(raw_unit, "unit").lower()
    except ValueError as exc:
        raise UnitNormalizationError(str(exc)) from exc

    try:
        return _UNIT_ALIASES[normalized_input]
    except KeyError as exc:
        raise UnitNormalizationError(f"unknown unit alias: {raw_unit}") from exc

