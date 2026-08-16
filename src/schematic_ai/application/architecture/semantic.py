"""Direct RequirementModel-to-DesignPlan semantic checks for Milestone 4."""

from __future__ import annotations

from math import inf, isclose

from schematic_ai.application.architecture.errors import ArchitectureSemanticValidationError
from schematic_ai.domain.design_plan.enums import InterfaceType, MappingTargetType
from schematic_ai.domain.design_plan.models import DesignPlan, Interface, PowerDomain, RequirementMapping
from schematic_ai.domain.requirements.enums import RequirementCategory
from schematic_ai.domain.requirements.models import Requirement, RequirementModel
from schematic_ai.domain.requirements.units import UnitNormalizationError, normalize_unit


_SUPPORTED_PROTOCOLS = {
    InterfaceType.I2C.value,
    InterfaceType.SPI.value,
    InterfaceType.UART.value,
    InterfaceType.CAN.value,
    InterfaceType.USB.value,
}


def validate_architecture_semantics(
    requirement_model: RequirementModel,
    design_plan: DesignPlan,
) -> None:
    """Validate direct facts represented explicitly in both models."""

    requirements = {
        requirement.id: requirement
        for requirement in [*requirement_model.requirements, *requirement_model.derived_requirements]
    }
    power_domains = {domain.power_domain_id: domain for domain in design_plan.power_domains}
    interfaces = {interface.interface_id: interface for interface in design_plan.interfaces}

    for mapping in design_plan.requirement_mappings:
        requirement = requirements.get(mapping.requirement_id)
        if requirement is None:
            continue
        _validate_voltage_mapping(requirement, mapping, power_domains)
        _validate_interface_mapping(requirement, mapping, interfaces)


def _validate_voltage_mapping(
    requirement: Requirement,
    mapping: RequirementMapping,
    power_domains: dict[str, PowerDomain],
) -> None:
    if requirement.category != RequirementCategory.POWER or "voltage" not in requirement.type:
        return

    requirement_interval = voltage_interval(requirement.constraint)
    if requirement_interval is None:
        return

    for target in mapping.implemented_by:
        if target.type != MappingTargetType.POWER_DOMAIN:
            continue
        domain = power_domains.get(target.id)
        if domain is None or domain.voltage is None:
            continue
        domain_interval = voltage_interval(domain.voltage)
        if domain_interval is None:
            continue
        if not interval_satisfies(requirement_interval, domain_interval):
            raise ArchitectureSemanticValidationError(
                f"{mapping.requirement_id} voltage mismatch: requirement {describe_constraint(requirement.constraint)} "
                f"but mapped power domain {domain.power_domain_id} is {describe_constraint(domain.voltage)}"
            )


def _validate_interface_mapping(
    requirement: Requirement,
    mapping: RequirementMapping,
    interfaces: dict[str, Interface],
) -> None:
    if requirement.category != RequirementCategory.INTERFACE:
        return

    required_protocols = required_interface_protocols(requirement)
    if not required_protocols:
        return

    for target in mapping.implemented_by:
        if target.type != MappingTargetType.INTERFACE:
            continue
        interface = interfaces.get(target.id)
        if interface is None:
            continue
        actual = interface.type.value
        if actual in _SUPPORTED_PROTOCOLS and actual not in required_protocols:
            raise ArchitectureSemanticValidationError(
                f"{mapping.requirement_id} protocol mismatch: requirement allows "
                f"{', '.join(sorted(required_protocols))} but mapped interface {interface.interface_id} is {actual}"
            )


def required_interface_protocols(requirement: Requirement) -> set[str]:
    constraint = requirement.constraint
    if getattr(constraint, "kind", None) != "enum":
        return set()
    protocols = {str(option).strip().lower() for option in constraint.allowed}
    return protocols & _SUPPORTED_PROTOCOLS


def voltage_interval(constraint) -> tuple[float, float, str] | None:
    if getattr(constraint, "kind", None) in {"exact", "nominal"}:
        return (constraint.value, constraint.value, normalized_unit(constraint.unit))
    if getattr(constraint, "kind", None) == "range":
        return (constraint.minimum, constraint.maximum, normalized_unit(constraint.unit))
    if getattr(constraint, "kind", None) == "minimum":
        return (constraint.value, inf, normalized_unit(constraint.unit))
    if getattr(constraint, "kind", None) == "maximum":
        return (-inf, constraint.value, normalized_unit(constraint.unit))
    return None


def normalized_unit(unit: str) -> str:
    try:
        return normalize_unit(unit)
    except UnitNormalizationError:
        return unit


def interval_satisfies(
    requirement_interval: tuple[float, float, str],
    domain_interval: tuple[float, float, str],
) -> bool:
    req_min, req_max, req_unit = requirement_interval
    domain_min, domain_max, domain_unit = domain_interval
    if req_unit != domain_unit:
        return False
    return greater_or_equal(domain_min, req_min) and less_or_equal(domain_max, req_max)


def greater_or_equal(left: float, right: float) -> bool:
    return left > right or isclose(left, right)


def less_or_equal(left: float, right: float) -> bool:
    return left < right or isclose(left, right)


def describe_constraint(constraint) -> str:
    if getattr(constraint, "kind", None) in {"exact", "nominal", "minimum", "maximum"}:
        return f"{constraint.kind} {format_number(constraint.value)} {constraint.unit}"
    if getattr(constraint, "kind", None) == "range":
        return f"range {format_number(constraint.minimum)}-{format_number(constraint.maximum)} {constraint.unit}"
    return constraint.kind


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)
