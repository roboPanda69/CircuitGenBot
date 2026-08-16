"""Deterministic DesignPlanDraft to DesignPlan enrichment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from schematic_ai.application.architecture.drafts import (
    DesignPlanDraft,
    DraftMappingTarget,
)
from schematic_ai.application.architecture.errors import ArchitectureEnrichmentError
from schematic_ai.domain.design_plan import validate_design_plan_against_requirements
from schematic_ai.domain.design_plan.enums import (
    FunctionalBlockType,
    FunctionalPortKind,
    InterfaceType,
    MappingTargetType,
    PortDirection,
    PowerDomainRole,
)
from schematic_ai.domain.design_plan.models import (
    ArchitectureDecision,
    BlockConnection,
    ConnectionEndpoint,
    DesignAssumption,
    DesignPlan,
    DesignPlanMetadata,
    FunctionalBlock,
    FunctionalPort,
    Interface,
    MappingTarget,
    OpenArchitectureDecision,
    PowerDomain,
    RequirementMapping,
    SourceRequirementSet,
)
from schematic_ai.domain.requirements.models import RequirementModel


_BLOCK_PREFIX = {
    FunctionalBlockType.POWER_INPUT: "INPUT",
    FunctionalBlockType.POWER_PROTECTION: "PROT",
    FunctionalBlockType.POWER_CONVERSION: "PWR",
    FunctionalBlockType.POWER_DISTRIBUTION: "PDIST",
    FunctionalBlockType.SENSOR: "SENSOR",
    FunctionalBlockType.ACTUATOR: "ACT",
    FunctionalBlockType.SIGNAL_CONDITIONING: "SIG",
    FunctionalBlockType.ANALOG_PROCESSING: "ANALOG",
    FunctionalBlockType.DIGITAL_LOGIC: "DIG",
    FunctionalBlockType.COMMUNICATION: "COMM",
    FunctionalBlockType.INTERFACE_BRIDGE: "IFBR",
    FunctionalBlockType.CONNECTOR: "CONNBLK",
    FunctionalBlockType.USER_INTERFACE: "UI",
    FunctionalBlockType.STORAGE: "STORE",
    FunctionalBlockType.TIMING: "TIME",
    FunctionalBlockType.ISOLATION: "ISO",
    FunctionalBlockType.OTHER: "GEN",
}


@dataclass
class DesignPlanEnricher:
    def build_design_plan(
        self,
        *,
        draft: DesignPlanDraft,
        requirement_model: RequirementModel,
        existing_design_plan: DesignPlan | None = None,
        created_at: datetime | None = None,
    ) -> DesignPlan:
        timestamp = created_at or datetime.now(timezone.utc)
        block_allocator = SequentialAllocator.from_existing("BLOCK", self._existing_block_ids(existing_design_plan))
        port_allocator = SequentialAllocator.from_existing("PORT", self._existing_port_ids(existing_design_plan))
        power_domain_allocator = SequentialAllocator.from_existing("PWRDOM", self._ids(existing_design_plan, "power_domain_id", "power_domains"))
        interface_allocator = SequentialAllocator.from_existing("IF", self._ids(existing_design_plan, "interface_id", "interfaces"))
        connection_allocator = SequentialAllocator.from_existing("CONN", self._ids(existing_design_plan, "connection_id", "block_connections"))
        mapping_allocator = SequentialAllocator.from_existing("MAP", self._ids(existing_design_plan, "mapping_id", "requirement_mappings"))
        decision_allocator = SequentialAllocator.from_existing("DEC", self._ids(existing_design_plan, "decision_id", "architecture_decisions"))
        assumption_allocator = SequentialAllocator.from_existing("DASM", self._ids(existing_design_plan, "assumption_id", "assumptions"))
        open_decision_allocator = SequentialAllocator.from_existing("ODEC", self._ids(existing_design_plan, "open_decision_id", "open_decisions"))

        existing_block_by_semantics = self._existing_blocks_by_semantics(existing_design_plan)
        existing_power_by_semantics = self._existing_power_domains_by_semantics(existing_design_plan)
        block_requirement_types = self._requirement_types_by_block(draft, requirement_model)
        block_id_by_draft: dict[str, str] = {}
        port_id_by_draft: dict[tuple[str, str], str] = {}

        for block in draft.blocks:
            semantic_key = (
                enum_value(block.type),
                canonical_block_name(block.type, block.topology_class, block_requirement_types.get(block.draft_id, set())),
            )
            existing = existing_block_by_semantics.get(semantic_key)
            block_id_by_draft[block.draft_id] = existing or block_allocator.next(_BLOCK_PREFIX[block.type])

        power_domain_id_by_draft: dict[str, str] = {}
        used_power_domain_ids: set[str] = set()
        for domain in draft.power_domains:
            existing_id = existing_power_by_semantics.get(power_domain_signature(domain.role, domain.voltage))
            if existing_id is not None and existing_id not in used_power_domain_ids:
                power_domain_id = existing_id
            else:
                power_domain_id = power_domain_allocator.next()
            power_domain_id_by_draft[domain.draft_id] = power_domain_id
            used_power_domain_ids.add(power_domain_id)

        interface_id_by_draft = {}
        used_interface_ids: set[str] = set()
        for interface in draft.interfaces:
            interface_id = self._interface_id(interface.type, existing_design_plan, interface_allocator, used_interface_ids)
            interface_id_by_draft[interface.draft_id] = interface_id
            used_interface_ids.add(interface_id)

        functional_blocks: list[FunctionalBlock] = []
        canonical_block_name_by_draft: dict[str, str] = {}
        for block in draft.blocks:
            inputs: list[FunctionalPort] = []
            outputs: list[FunctionalPort] = []
            block_port_counters: dict[tuple[FunctionalPortKind, PortDirection], int] = {}
            for port in block.ports:
                port_name = canonical_port_name(port.kind, port.direction, block_port_counters)
                port_id = self._port_id(
                    existing_design_plan,
                    port_name,
                    block_id_by_draft[block.draft_id],
                    port_allocator,
                    _BLOCK_PREFIX[block.type],
                )
                port_id_by_draft[(block.draft_id, port.draft_id)] = port_id
                canonical_port = FunctionalPort(
                    port_id=port_id,
                    name=port_name,
                    kind=port.kind,
                    direction=port.direction,
                    power_domain=power_domain_id_by_draft.get(port.power_domain_ref) if port.power_domain_ref else None,
                    interface_id=interface_id_by_draft.get(port.interface_ref) if port.interface_ref else None,
                )
                if port.direction == PortDirection.INPUT:
                    inputs.append(canonical_port)
                else:
                    outputs.append(canonical_port)
            block_name = canonical_block_name(
                block.type,
                block.topology_class,
                block_requirement_types.get(block.draft_id, set()),
            )
            canonical_block_name_by_draft[block.draft_id] = block_name
            functional_blocks.append(
                FunctionalBlock(
                    block_id=block_id_by_draft[block.draft_id],
                    type=block.type,
                    name=block_name,
                    purpose=canonical_block_purpose(
                        block.type,
                        block.topology_class,
                        block_requirement_types.get(block.draft_id, set()),
                    ),
                    topology_class=block.topology_class,
                    inputs=inputs,
                    outputs=outputs,
                    status=block.status,
                )
            )

        connection_id_by_draft: dict[str, str] = {}
        block_connections: list[BlockConnection] = []
        for connection in draft.connections:
            connection_id = connection_allocator.next()
            connection_id_by_draft[connection.draft_id] = connection_id
            block_connections.append(
                BlockConnection(
                    connection_id=connection_id,
                    source=ConnectionEndpoint(
                        block_id=block_id_by_draft[connection.source_block],
                        port_id=port_id_by_draft[(connection.source_block, connection.source_port)],
                    ),
                    target=ConnectionEndpoint(
                        block_id=block_id_by_draft[connection.target_block],
                        port_id=port_id_by_draft[(connection.target_block, connection.target_port)],
                    ),
                    kind=connection.kind,
                    description=canonical_connection_description(
                        canonical_block_name_by_draft[connection.source_block],
                        canonical_block_name_by_draft[connection.target_block],
                        connection.kind,
                    ),
                )
            )

        power_domains = [
            PowerDomain(
                power_domain_id=power_domain_id_by_draft[domain.draft_id],
                name=canonical_power_domain_name(domain.role, domain.voltage),
                role=domain.role,
                voltage=domain.voltage,
                source_block=block_id_by_draft.get(domain.source_block) if domain.source_block else None,
                consumer_blocks=[block_id_by_draft[item] for item in domain.consumer_blocks],
            )
            for domain in draft.power_domains
        ]

        interfaces = [
            Interface(
                interface_id=interface_id_by_draft[interface.draft_id],
                type=interface.type,
                name=canonical_interface_name(interface.type),
                participants=[block_id_by_draft[item] for item in interface.participants],
                direction=interface.direction,
                power_domain=power_domain_id_by_draft.get(interface.power_domain_ref) if interface.power_domain_ref else None,
            )
            for interface in draft.interfaces
        ]

        architecture_decision_id_by_draft: dict[str, str] = {}
        architecture_decisions: list[ArchitectureDecision] = []
        for decision in draft.architecture_decisions:
            decision_id = decision_allocator.next()
            architecture_decision_id_by_draft[decision.draft_id] = decision_id
            architecture_decisions.append(
                ArchitectureDecision(
                    decision_id=decision_id,
                    type=decision.type,
                    target=self._resolve_target(
                        decision.target,
                        block_id_by_draft,
                        power_domain_id_by_draft,
                        interface_id_by_draft,
                        connection_id_by_draft,
                        architecture_decision_id_by_draft,
                    ),
                    choice=decision.choice,
                    rationale=canonical_decision_rationale(decision.type, decision.choice, decision.driven_by_requirements),
                    driven_by_requirements=decision.driven_by_requirements,
                    status=decision.status,
                )
            )

        requirement_mappings = [
            RequirementMapping(
                mapping_id=mapping_allocator.next(),
                requirement_id=mapping.requirement_id,
                implemented_by=[
                    self._resolve_target(
                        target,
                        block_id_by_draft,
                        power_domain_id_by_draft,
                        interface_id_by_draft,
                        connection_id_by_draft,
                        architecture_decision_id_by_draft,
                    )
                    for target in mapping.targets
                ],
                status=mapping.status,
            )
            for mapping in draft.requirement_mappings
        ]

        assumptions = [
            DesignAssumption(
                assumption_id=assumption_allocator.next(),
                description=canonical_assumption_description(len(assumption.affected_blocks)),
                impact=assumption.impact,
                status=assumption.status,
                affected_blocks=[block_id_by_draft[item] for item in assumption.affected_blocks],
            )
            for assumption in draft.assumptions
        ]

        open_decisions: list[OpenArchitectureDecision] = []
        for index, open_decision in enumerate(draft.open_decisions, start=1):
            open_decisions.append(
                OpenArchitectureDecision(
                    open_decision_id=open_decision_allocator.next(),
                    topic=f"architecture_decision_{index:03d}",
                    description=canonical_open_decision_description(open_decision.options),
                    options=open_decision.options,
                    blocking=open_decision.blocking,
                    status=open_decision.status,
                    affected_blocks=[block_id_by_draft[item] for item in open_decision.affected_blocks],
                )
            )

        try:
            plan = DesignPlan(
                design_plan_id=existing_design_plan.design_plan_id if existing_design_plan else "DPLAN_0001",
                project_id=requirement_model.project_id,
                revision=(existing_design_plan.revision + 1) if existing_design_plan else 1,
                source_requirement_set=SourceRequirementSet(
                    requirement_set_id=requirement_model.requirement_set_id,
                    revision=requirement_model.revision,
                ),
                functional_blocks=functional_blocks,
                block_connections=block_connections,
                power_domains=power_domains,
                interfaces=interfaces,
                requirement_mappings=requirement_mappings,
                architecture_decisions=architecture_decisions,
                assumptions=assumptions,
                open_decisions=open_decisions,
                metadata=DesignPlanMetadata(
                    created_at=existing_design_plan.metadata.created_at if existing_design_plan else timestamp,
                    updated_at=timestamp,
                    created_by="architecture_planner",
                ),
            )
            validate_design_plan_against_requirements(plan, requirement_model)
        except Exception as exc:
            raise ArchitectureEnrichmentError(str(exc)) from exc
        return plan

    @staticmethod
    def _resolve_target(
        target: DraftMappingTarget,
        block_ids: dict[str, str],
        power_domain_ids: dict[str, str],
        interface_ids: dict[str, str],
        connection_ids: dict[str, str],
        decision_ids: dict[str, str],
    ) -> MappingTarget:
        by_type = {
            MappingTargetType.FUNCTIONAL_BLOCK: block_ids,
            MappingTargetType.POWER_DOMAIN: power_domain_ids,
            MappingTargetType.INTERFACE: interface_ids,
            MappingTargetType.BLOCK_CONNECTION: connection_ids,
            MappingTargetType.ARCHITECTURE_DECISION: decision_ids,
        }
        try:
            return MappingTarget(type=target.type, id=by_type[target.type][target.draft_id])
        except KeyError as exc:
            raise ArchitectureEnrichmentError(f"unknown draft target {target.type}: {target.draft_id}") from exc

    @staticmethod
    def _existing_blocks_by_semantics(existing: DesignPlan | None) -> dict[tuple[str, str], str]:
        if existing is None:
            return {}
        return {(enum_value(block.type), block.name): block.block_id for block in existing.functional_blocks}

    @staticmethod
    def _existing_power_domains_by_semantics(existing: DesignPlan | None) -> dict[tuple[str, str], str]:
        if existing is None:
            return {}
        result: dict[tuple[str, str], str] = {}
        for domain in existing.power_domains:
            result.setdefault(power_domain_signature(domain.role, domain.voltage), domain.power_domain_id)
        return result

    @staticmethod
    def _existing_block_ids(existing: DesignPlan | None) -> Iterable[str]:
        if existing is None:
            return ()
        return [block.block_id for block in existing.functional_blocks]

    @staticmethod
    def _existing_port_ids(existing: DesignPlan | None) -> Iterable[str]:
        if existing is None:
            return ()
        return [
            port.port_id
            for block in existing.functional_blocks
            for port in [*block.inputs, *block.outputs]
        ]

    @staticmethod
    def _ids(existing: DesignPlan | None, field_name: str, collection_name: str) -> Iterable[str]:
        if existing is None:
            return ()
        return [getattr(item, field_name) for item in getattr(existing, collection_name)]

    @staticmethod
    @staticmethod
    def _interface_id(interface_type, existing: DesignPlan | None, allocator: "SequentialAllocator", used_ids: set[str]) -> str:
        if existing:
            for interface in existing.interfaces:
                if interface.type == interface_type and interface.interface_id not in used_ids:
                    return interface.interface_id
        return allocator.next(enum_value(interface_type).upper())

    @staticmethod
    def _port_id(
        existing: DesignPlan | None,
        port_name: str,
        canonical_block_id: str,
        allocator: "SequentialAllocator",
        prefix: str,
    ) -> str:
        if existing:
            for block in existing.functional_blocks:
                if block.block_id == canonical_block_id:
                    for port in [*block.inputs, *block.outputs]:
                        if port.name == port_name:
                            return port.port_id
        return allocator.next(prefix)

    @staticmethod
    def _requirement_types_by_block(
        draft: DesignPlanDraft,
        requirement_model: RequirementModel,
    ) -> dict[str, set[str]]:
        requirement_types = {
            requirement.id: requirement.type
            for requirement in [*requirement_model.requirements, *requirement_model.derived_requirements]
        }
        result: dict[str, set[str]] = {}
        for mapping in draft.requirement_mappings:
            requirement_type = requirement_types.get(mapping.requirement_id)
            if requirement_type is None:
                continue
            for target in mapping.targets:
                if target.type == MappingTargetType.FUNCTIONAL_BLOCK:
                    result.setdefault(target.draft_id, set()).add(requirement_type)
        return result


class SequentialAllocator:
    def __init__(self, root: str, existing_ids: Iterable[str] = ()):
        self.root = root
        self._generic_counter = 0
        self._prefix_counters: dict[str, int] = {}
        for item_id in existing_ids:
            match = re.match(rf"^{re.escape(root)}(?:_([A-Z]+))?_(\d+)$", item_id)
            if not match:
                continue
            prefix, number = match.groups()
            if prefix is None:
                self._generic_counter = max(self._generic_counter, int(number))
            else:
                self._prefix_counters[prefix] = max(self._prefix_counters.get(prefix, 0), int(number))

    @classmethod
    def from_existing(cls, root: str, existing_ids: Iterable[str]) -> "SequentialAllocator":
        return cls(root, existing_ids)

    def next(self, prefix: str | None = None) -> str:
        if prefix is None:
            self._generic_counter += 1
            return f"{self.root}_{self._generic_counter:03d}"
        self._prefix_counters[prefix] = self._prefix_counters.get(prefix, 0) + 1
        return f"{self.root}_{prefix}_{self._prefix_counters[prefix]:03d}"


def enum_value(value) -> str:
    return getattr(value, "value", str(value))


def canonical_block_name(
    block_type: FunctionalBlockType,
    topology_class,
    requirement_types: set[str],
) -> str:
    topology = enum_value(topology_class) if topology_class is not None else None
    if block_type == FunctionalBlockType.POWER_INPUT:
        return "Input Power Interface"
    if block_type == FunctionalBlockType.POWER_PROTECTION:
        if "reverse_polarity_protection" in requirement_types:
            return "Reverse-Polarity Power Protection"
        return "Power Protection"
    if block_type == FunctionalBlockType.POWER_CONVERSION:
        if topology == "switching_step_down":
            return "Step-Down Power Conversion"
        if topology == "switching_step_up":
            return "Step-Up Power Conversion"
        if topology == "linear_regulation":
            return "Linear Power Regulation"
        if topology == "isolated_power_conversion":
            return "Isolated Power Conversion"
        return "Power Conversion"
    if block_type == FunctionalBlockType.POWER_DISTRIBUTION:
        return "Power Distribution"
    if block_type == FunctionalBlockType.SENSOR:
        return "Sensor Functional Block"
    if block_type == FunctionalBlockType.COMMUNICATION:
        return "Communication Interface"
    if block_type == FunctionalBlockType.INTERFACE_BRIDGE:
        return "Interface Bridge"
    if block_type == FunctionalBlockType.ISOLATION:
        return "Isolation Boundary"
    return f"{enum_value(block_type).replace('_', ' ').title()} Functional Block"


def canonical_block_purpose(
    block_type: FunctionalBlockType,
    topology_class,
    requirement_types: set[str],
) -> str:
    topology = enum_value(topology_class) if topology_class is not None else None
    if block_type == FunctionalBlockType.POWER_INPUT:
        return "Represent the external power entry point for the functional architecture."
    if block_type == FunctionalBlockType.POWER_PROTECTION:
        return "Represent architecture-level protection before downstream functional blocks."
    if block_type == FunctionalBlockType.POWER_CONVERSION:
        if topology == "switching_step_down":
            return "Convert the source power domain to the required lower regulated output domain."
        if topology == "switching_step_up":
            return "Convert the source power domain to the required higher regulated output domain."
        if topology == "linear_regulation":
            return "Regulate the source power domain to the required output domain."
        return "Convert the source power domain to the required regulated output domain."
    if block_type == FunctionalBlockType.SENSOR:
        return "Represent the sensing function required by the architecture."
    if block_type == FunctionalBlockType.COMMUNICATION:
        return "Represent the logical communication interface for the architecture."
    if block_type == FunctionalBlockType.ISOLATION:
        return "Represent a functional isolation boundary for downstream implementation."
    return "Represent a functional architecture block for mapped requirements."


def canonical_port_name(
    kind: FunctionalPortKind,
    direction: PortDirection,
    counters: dict[tuple[FunctionalPortKind, PortDirection], int],
) -> str:
    key = (kind, direction)
    counters[key] = counters.get(key, 0) + 1
    return f"{enum_value(kind)}_{enum_value(direction)}_{counters[key]}"


def canonical_connection_description(source_name: str, target_name: str, kind) -> str:
    return f"Connect {source_name} to {target_name} for {enum_value(kind).replace('_', ' ')} transfer."


def canonical_power_domain_name(role: PowerDomainRole, voltage) -> str:
    role_text = {
        PowerDomainRole.INPUT: "Input",
        PowerDomainRole.PROTECTED_INPUT: "Protected Input",
        PowerDomainRole.REGULATED_OUTPUT: "Regulated Output",
        PowerDomainRole.UNREGULATED: "Unregulated",
        PowerDomainRole.LOGIC_SUPPLY: "Logic Supply",
        PowerDomainRole.ANALOG_SUPPLY: "Analog Supply",
        PowerDomainRole.REFERENCE: "Reference",
        PowerDomainRole.ISOLATED_SUPPLY: "Isolated Supply",
        PowerDomainRole.OTHER: "General",
    }[role]
    voltage_text = voltage_label(voltage)
    if voltage_text:
        return f"{voltage_text} {role_text} Power Domain"
    return f"{role_text} Power Domain"


def canonical_interface_name(interface_type: InterfaceType) -> str:
    return f"{enum_value(interface_type).upper()} Interface"


def canonical_decision_rationale(decision_type, choice, driven_by_requirements: list[str]) -> str:
    choice_text = enum_value(choice).replace("_", " ")
    decision_text = enum_value(decision_type).replace("_", " ")
    if driven_by_requirements:
        return f"Selected a {choice_text} architecture for mapped {decision_text} requirements."
    return f"Selected a {choice_text} architecture for the {decision_text}."


def canonical_assumption_description(affected_count: int) -> str:
    if affected_count == 1:
        return "Architecture assumption retained for one affected functional block."
    return f"Architecture assumption retained for {affected_count} affected functional blocks."


def canonical_open_decision_description(options: list) -> str:
    if not options:
        return "An architecture decision remains open before implementation planning can continue."
    choices = ", ".join(enum_value(option).replace("_", " ") for option in options)
    return f"An architecture decision remains open among controlled options: {choices}."


def voltage_label(voltage) -> str:
    if voltage is None:
        return ""
    if getattr(voltage, "kind", None) in {"exact", "nominal"}:
        return f"{format_number(voltage.value)} {voltage.unit}"
    return ""


def power_domain_signature(role: PowerDomainRole, voltage) -> tuple[str, str]:
    return (enum_value(role), constraint_signature(voltage))


def constraint_signature(constraint) -> str:
    if constraint is None:
        return "none"
    data = constraint.model_dump(mode="json")
    return "|".join(f"{key}={data[key]}" for key in sorted(data))


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)
