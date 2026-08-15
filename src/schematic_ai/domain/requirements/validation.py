"""Shared validators for requirement domain models."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable


ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def require_identifier(value: str, field_name: str = "id") -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} cannot be blank")
    if not ID_PATTERN.match(value):
        raise ValueError(
            f"{field_name} must start with a letter and contain only letters, digits, '_' or '-'"
        )
    return value


def require_nonblank(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} cannot be blank")
    return value


def require_finite_number(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def reject_duplicates(values: Iterable[str], field_name: str) -> list[str]:
    normalized = list(values)
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    if duplicates:
        raise ValueError(f"{field_name} contains duplicate values: {', '.join(duplicates)}")
    return normalized
