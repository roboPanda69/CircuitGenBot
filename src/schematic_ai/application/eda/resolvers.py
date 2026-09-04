"""Deterministic EDA support resolvers for CircuitIR generation."""

from __future__ import annotations

from dataclasses import dataclass

from schematic_ai.domain.circuit_ir import (
    ComponentInstance,
    ComponentResolutionStatus,
    PinConnectionState,
    PinResolutionStatus,
)
from schematic_ai.domain.knowledge import FootprintReference, SymbolReference


@dataclass(frozen=True)
class SymbolResolution:
    symbol_reference: SymbolReference | None
    requires_placeholder: bool
    reason: str | None = None


@dataclass(frozen=True)
class FootprintResolution:
    footprint_reference: FootprintReference | None
    reason: str | None = None


@dataclass(frozen=True)
class PinMappingResolution:
    pin_numbers_by_pin_id: dict[str, str]
    is_trusted: bool
    reason: str | None = None


class SymbolResolver:
    """Resolve only verified CircuitIR/knowledge symbol references."""

    def resolve(self, component: ComponentInstance) -> SymbolResolution:
        reference = component.symbol_reference
        if reference is not None and reference.verified_exists:
            return SymbolResolution(symbol_reference=reference, requires_placeholder=False)

        if component.resolution_status == ComponentResolutionStatus.RESOLVED:
            if reference is None:
                return SymbolResolution(None, True, "resolved component has no verified KiCad symbol reference")
            return SymbolResolution(None, True, "resolved component symbol reference is not verified")

        return SymbolResolution(None, True, "component identity is not fully resolved")


class FootprintResolver:
    """Resolve footprints independently from schematic symbol resolution."""

    def resolve(self, component: ComponentInstance) -> FootprintResolution:
        reference = component.footprint_reference
        if reference is not None and reference.verified_exists:
            return FootprintResolution(reference)
        if reference is None:
            return FootprintResolution(None, "component has no verified footprint reference")
        return FootprintResolution(None, "component footprint reference is not verified")


class PinMappingResolver:
    """Map pins only when CircuitIR already carries trusted resolved pin numbers."""

    def resolve(self, component: ComponentInstance, symbol_resolution: SymbolResolution) -> PinMappingResolution:
        if symbol_resolution.requires_placeholder:
            return PinMappingResolution(
                pin_numbers_by_pin_id=self.placeholder_pin_numbers(component),
                is_trusted=True,
            )

        pin_numbers: dict[str, str] = {}
        for pin in component.pins:
            if pin.connection_state == PinConnectionState.UNRESOLVED:
                continue
            if pin.resolution_status != PinResolutionStatus.RESOLVED or pin.pin_number is None:
                return PinMappingResolution(
                    pin_numbers_by_pin_id={},
                    is_trusted=False,
                    reason=f"{pin.pin_id} lacks a trusted resolved pin number",
                )
            pin_numbers[pin.pin_id] = pin.pin_number
        return PinMappingResolution(pin_numbers_by_pin_id=pin_numbers, is_trusted=True)

    def placeholder_pin_numbers(self, component: ComponentInstance) -> dict[str, str]:
        labels: dict[str, str] = {}
        used: set[str] = set()
        for index, pin in enumerate(component.pins, start=1):
            label = pin.pin_name or pin.function or f"PIN_{index}"
            label = _safe_placeholder_pin_label(label)
            if label in used:
                label = f"{label}_{index}"
            used.add(label)
            labels[pin.pin_id] = label
        return labels


def _safe_placeholder_pin_label(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "_+-" else "_" for char in value.strip().upper())
    return safe or "PIN"
