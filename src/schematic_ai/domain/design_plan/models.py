"""DesignPlan v0.1 typed domain contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.design_plan.enums import (
    ArchitectureChoice,
    ArchitectureDecisionStatus,
    ArchitectureDecisionType,
    ConnectionKind,
    FunctionalBlockStatus,
    FunctionalBlockType,
    FunctionalPortKind,
    FunctionalTopologyClass,
    InterfaceDirection,
    InterfaceType,
    MappingTargetType,
    OpenDecisionStatus,
    PortDirection,
    PowerDomainRole,
    RequirementMappingStatus,
)
from schematic_ai.domain.requirements.constraints import Constraint
from schematic_ai.domain.requirements.enums import Impact
from schematic_ai.domain.requirements.validation import (
    reject_duplicates,
    require_identifier,
    require_nonblank,
)


SCHEMA_VERSION = "0.1"

_TOPOLOGY_CHOICES = {
    ArchitectureChoice.SWITCHING_STEP_DOWN,
    ArchitectureChoice.SWITCHING_STEP_UP,
    ArchitectureChoice.SWITCHING_INVERTING,
    ArchitectureChoice.LINEAR_REGULATION,
    ArchitectureChoice.ISOLATED_POWER_CONVERSION,
    ArchitectureChoice.NON_ISOLATED_POWER_CONVERSION,
    ArchitectureChoice.DIRECT_INTERFACE,
    ArchitectureChoice.INTERFACE_BRIDGE,
    ArchitectureChoice.ANALOG_FILTER,
    ArchitectureChoice.AMPLIFIER,
    ArchitectureChoice.SIGNAL_CONDITIONING,
    ArchitectureChoice.LEVEL_TRANSLATION,
    ArchitectureChoice.GALVANIC_ISOLATION,
    ArchitectureChoice.SENSOR_FRONTEND,
    ArchitectureChoice.ACTUATOR_DRIVER,
    ArchitectureChoice.CUSTOM_ARCHITECTURE,
}

_ARCHITECTURE_CHOICE_COMPATIBILITY = {
    ArchitectureDecisionType.TOPOLOGY_CHOICE: _TOPOLOGY_CHOICES,
    ArchitectureDecisionType.INTERFACE_STRATEGY: {
        ArchitectureChoice.DIRECT_INTERFACE,
        ArchitectureChoice.INTERFACE_BRIDGE,
        ArchitectureChoice.LEVEL_TRANSLATION,
        ArchitectureChoice.PROTOCOL_TRANSLATION,
        ArchitectureChoice.CUSTOM_ARCHITECTURE,
    },
    ArchitectureDecisionType.POWER_STRATEGY: {
        ArchitectureChoice.SINGLE_RAIL,
        ArchitectureChoice.MULTIPLE_RAILS,
        ArchitectureChoice.CENTRALIZED_REGULATION,
        ArchitectureChoice.DISTRIBUTED_REGULATION,
        ArchitectureChoice.ISOLATED_DOMAINS,
        ArchitectureChoice.SHARED_GROUND_DOMAINS,
        ArchitectureChoice.CUSTOM_ARCHITECTURE,
    },
    ArchitectureDecisionType.ISOLATION_STRATEGY: {
        ArchitectureChoice.GALVANICALLY_ISOLATED,
        ArchitectureChoice.NON_ISOLATED,
        ArchitectureChoice.PARTIAL_ISOLATION,
        ArchitectureChoice.GALVANIC_ISOLATION,
        ArchitectureChoice.CUSTOM_ARCHITECTURE,
    },
    ArchitectureDecisionType.SIGNAL_PATH_STRATEGY: {
        ArchitectureChoice.DIRECT_SIGNAL_PATH,
        ArchitectureChoice.FILTERED_SIGNAL_PATH,
        ArchitectureChoice.AMPLIFIED_SIGNAL_PATH,
        ArchitectureChoice.CONDITIONED_SIGNAL_PATH,
        ArchitectureChoice.DIFFERENTIAL_SIGNAL_PATH,
        ArchitectureChoice.SINGLE_ENDED_SIGNAL_PATH,
        ArchitectureChoice.ANALOG_FILTER,
        ArchitectureChoice.AMPLIFIER,
        ArchitectureChoice.SIGNAL_CONDITIONING,
        ArchitectureChoice.CUSTOM_ARCHITECTURE,
    },
    ArchitectureDecisionType.PARTITIONING: {
        ArchitectureChoice.SINGLE_BOARD_PARTITION,
        ArchitectureChoice.MODULAR_PARTITION,
        ArchitectureChoice.SEPARATE_POWER_AND_CONTROL,
        ArchitectureChoice.INTEGRATED_ARCHITECTURE,
        ArchitectureChoice.CUSTOM_ARCHITECTURE,
    },
    ArchitectureDecisionType.OTHER: {ArchitectureChoice.CUSTOM_ARCHITECTURE},
}


class DesignPlanDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SourceRequirementSet(DesignPlanDomainModel):
    requirement_set_id: str
    revision: int = Field(ge=1)

    @field_validator("requirement_set_id")
    @classmethod
    def requirement_set_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "requirement_set_id")


class FunctionalPort(DesignPlanDomainModel):
    port_id: str
    name: str
    kind: FunctionalPortKind
    direction: PortDirection
    power_domain: str | None = None
    interface_id: str | None = None

    @field_validator("port_id")
    @classmethod
    def port_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "port_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "port name")

    @field_validator("power_domain", "interface_id")
    @classmethod
    def optional_ids_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "port reference")


class FunctionalBlock(DesignPlanDomainModel):
    block_id: str
    type: FunctionalBlockType
    name: str
    purpose: str
    topology_class: FunctionalTopologyClass | None = None
    inputs: list[FunctionalPort] = Field(default_factory=list)
    outputs: list[FunctionalPort] = Field(default_factory=list)
    status: FunctionalBlockStatus = FunctionalBlockStatus.PLANNED

    @field_validator("block_id")
    @classmethod
    def block_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "block_id")

    @field_validator("name", "purpose")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "block text")

    @model_validator(mode="after")
    def block_port_ids_must_be_unique(self) -> "FunctionalBlock":
        reject_duplicates([port.port_id for port in [*self.inputs, *self.outputs]], "block port IDs")
        return self


class ConnectionEndpoint(DesignPlanDomainModel):
    block_id: str
    port_id: str

    @field_validator("block_id", "port_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "connection endpoint")


class BlockConnection(DesignPlanDomainModel):
    connection_id: str
    source: ConnectionEndpoint
    target: ConnectionEndpoint
    kind: ConnectionKind
    description: str

    @field_validator("connection_id")
    @classmethod
    def connection_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "connection_id")

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "description")

    @model_validator(mode="after")
    def endpoints_must_not_be_identical(self) -> "BlockConnection":
        if self.source == self.target:
            raise ValueError("connection source and target endpoints must differ")
        return self


class PowerDomain(DesignPlanDomainModel):
    power_domain_id: str
    name: str
    role: PowerDomainRole
    voltage: Constraint | None = None
    source_block: str | None = None
    consumer_blocks: list[str] = Field(default_factory=list)

    @field_validator("power_domain_id")
    @classmethod
    def power_domain_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "power_domain_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "power domain name")

    @field_validator("source_block")
    @classmethod
    def optional_source_block_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "source_block")

    @field_validator("consumer_blocks")
    @classmethod
    def consumer_blocks_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(block_id, "consumer_blocks") for block_id in value]
        return reject_duplicates(ids, "consumer_blocks")


class Interface(DesignPlanDomainModel):
    interface_id: str
    type: InterfaceType
    name: str
    participants: list[str] = Field(min_length=1)
    direction: InterfaceDirection
    power_domain: str | None = None

    @field_validator("interface_id")
    @classmethod
    def interface_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "interface_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "interface name")

    @field_validator("participants")
    @classmethod
    def participants_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(block_id, "participants") for block_id in value]
        return reject_duplicates(ids, "participants")

    @field_validator("power_domain")
    @classmethod
    def optional_power_domain_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "power_domain")


class MappingTarget(DesignPlanDomainModel):
    type: MappingTargetType
    id: str

    @field_validator("id")
    @classmethod
    def id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "mapping target id")


class RequirementMapping(DesignPlanDomainModel):
    mapping_id: str
    requirement_id: str
    implemented_by: list[MappingTarget] = Field(default_factory=list)
    status: RequirementMappingStatus

    @field_validator("mapping_id", "requirement_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "requirement mapping id")

    @model_validator(mode="after")
    def mapped_status_requires_target(self) -> "RequirementMapping":
        if self.status in {
            RequirementMappingStatus.MAPPED,
            RequirementMappingStatus.PARTIALLY_MAPPED,
        } and not self.implemented_by:
            raise ValueError("mapped requirements must reference at least one design-plan target")
        return self


class ArchitectureDecision(DesignPlanDomainModel):
    decision_id: str
    type: ArchitectureDecisionType
    target: MappingTarget
    choice: ArchitectureChoice
    rationale: str
    driven_by_requirements: list[str] = Field(default_factory=list)
    status: ArchitectureDecisionStatus = ArchitectureDecisionStatus.PROPOSED

    @field_validator("decision_id")
    @classmethod
    def decision_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "decision_id")

    @field_validator("rationale")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "architecture decision text")

    @field_validator("driven_by_requirements")
    @classmethod
    def driven_requirements_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(requirement_id, "driven_by_requirements") for requirement_id in value]
        return reject_duplicates(ids, "driven_by_requirements")

    @model_validator(mode="after")
    def choice_must_match_decision_type(self) -> "ArchitectureDecision":
        allowed = _ARCHITECTURE_CHOICE_COMPATIBILITY[self.type]
        if self.choice not in allowed:
            raise ValueError(f"{self.choice} is not compatible with decision type {self.type}")
        return self


class DesignAssumption(DesignPlanDomainModel):
    assumption_id: str
    description: str
    impact: Impact
    status: Literal["active", "resolved", "dismissed"] = "active"
    affected_blocks: list[str] = Field(default_factory=list)

    @field_validator("assumption_id")
    @classmethod
    def assumption_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "assumption_id")

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "assumption description")

    @field_validator("affected_blocks")
    @classmethod
    def affected_blocks_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(block_id, "affected_blocks") for block_id in value]
        return reject_duplicates(ids, "affected_blocks")


class OpenArchitectureDecision(DesignPlanDomainModel):
    open_decision_id: str
    topic: str
    description: str
    options: list[ArchitectureChoice] = Field(default_factory=list)
    blocking: bool
    status: OpenDecisionStatus = OpenDecisionStatus.OPEN
    affected_blocks: list[str] = Field(default_factory=list)

    @field_validator("open_decision_id")
    @classmethod
    def open_decision_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "open_decision_id")

    @field_validator("topic", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "open decision text")

    @field_validator("options")
    @classmethod
    def options_must_be_unique(cls, value: list[ArchitectureChoice]) -> list[ArchitectureChoice]:
        return reject_duplicates(value, "open decision options")

    @field_validator("affected_blocks")
    @classmethod
    def affected_blocks_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(block_id, "affected_blocks") for block_id in value]
        return reject_duplicates(ids, "affected_blocks")


class DesignPlanMetadata(DesignPlanDomainModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("created_by")
    @classmethod
    def created_by_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "created_by")

    @model_validator(mode="after")
    def updated_at_must_not_precede_created_at(self) -> "DesignPlanMetadata":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class DesignPlan(DesignPlanDomainModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    design_plan_id: str
    project_id: str
    revision: int = Field(ge=1)
    source_requirement_set: SourceRequirementSet
    functional_blocks: list[FunctionalBlock] = Field(default_factory=list)
    block_connections: list[BlockConnection] = Field(default_factory=list)
    power_domains: list[PowerDomain] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    requirement_mappings: list[RequirementMapping] = Field(default_factory=list)
    architecture_decisions: list[ArchitectureDecision] = Field(default_factory=list)
    assumptions: list[DesignAssumption] = Field(default_factory=list)
    open_decisions: list[OpenArchitectureDecision] = Field(default_factory=list)
    metadata: DesignPlanMetadata

    @field_validator("design_plan_id", "project_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "design plan id")

    @model_validator(mode="after")
    def validate_internal_references(self) -> "DesignPlan":
        block_ids = [block.block_id for block in self.functional_blocks]
        power_domain_ids = [domain.power_domain_id for domain in self.power_domains]
        interface_ids = [interface.interface_id for interface in self.interfaces]
        connection_ids = [connection.connection_id for connection in self.block_connections]
        decision_ids = [decision.decision_id for decision in self.architecture_decisions]

        self._validate_unique("functional block IDs", block_ids)
        self._validate_unique("block connection IDs", connection_ids)
        self._validate_unique("power domain IDs", power_domain_ids)
        self._validate_unique("interface IDs", interface_ids)
        self._validate_unique("requirement mapping IDs", [mapping.mapping_id for mapping in self.requirement_mappings])
        self._validate_unique("architecture decision IDs", decision_ids)
        self._validate_unique("design assumption IDs", [assumption.assumption_id for assumption in self.assumptions])
        self._validate_unique("open decision IDs", [decision.open_decision_id for decision in self.open_decisions])

        ports_by_block: dict[str, dict[str, FunctionalPort]] = {}
        all_port_ids: list[str] = []
        for block in self.functional_blocks:
            block_ports = {port.port_id: port for port in [*block.inputs, *block.outputs]}
            ports_by_block[block.block_id] = block_ports
            all_port_ids.extend(block_ports)
        self._validate_unique("functional port IDs", all_port_ids)

        known_blocks = set(block_ids)
        known_power_domains = set(power_domain_ids)
        known_interfaces = set(interface_ids)
        known_connections = set(connection_ids)
        known_decisions = set(decision_ids)

        for block in self.functional_blocks:
            for port in [*block.inputs, *block.outputs]:
                if port.power_domain is not None and port.power_domain not in known_power_domains:
                    raise ValueError(f"{port.port_id} references unknown power domain {port.power_domain}")
                if port.interface_id is not None and port.interface_id not in known_interfaces:
                    raise ValueError(f"{port.port_id} references unknown interface {port.interface_id}")

        for connection in self.block_connections:
            source_port = self._resolve_endpoint(connection.source, ports_by_block, "source")
            target_port = self._resolve_endpoint(connection.target, ports_by_block, "target")
            if source_port.direction == PortDirection.INPUT and target_port.direction == PortDirection.INPUT:
                raise ValueError(f"{connection.connection_id} cannot connect input to input")
            if source_port.direction == PortDirection.INPUT:
                raise ValueError(f"{connection.connection_id} source port cannot be input-only")
            if target_port.direction == PortDirection.OUTPUT:
                raise ValueError(f"{connection.connection_id} target port cannot be output-only")

        for domain in self.power_domains:
            if domain.source_block is not None and domain.source_block not in known_blocks:
                raise ValueError(f"{domain.power_domain_id} references unknown source block {domain.source_block}")
            for block_id in domain.consumer_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"{domain.power_domain_id} references unknown consumer block {block_id}")

        for interface in self.interfaces:
            for block_id in interface.participants:
                if block_id not in known_blocks:
                    raise ValueError(f"{interface.interface_id} references unknown participant {block_id}")
            if interface.power_domain is not None and interface.power_domain not in known_power_domains:
                raise ValueError(f"{interface.interface_id} references unknown power domain {interface.power_domain}")

        for mapping in self.requirement_mappings:
            for target in mapping.implemented_by:
                self._validate_mapping_target(target, known_blocks, known_power_domains, known_interfaces, known_connections, known_decisions)

        for decision in self.architecture_decisions:
            self._validate_mapping_target(decision.target, known_blocks, known_power_domains, known_interfaces, known_connections, known_decisions)

        for assumption in self.assumptions:
            for block_id in assumption.affected_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"{assumption.assumption_id} references unknown block {block_id}")

        for open_decision in self.open_decisions:
            for block_id in open_decision.affected_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"{open_decision.open_decision_id} references unknown block {block_id}")

        return self

    @staticmethod
    def _validate_unique(namespace: str, ids: list[str]) -> None:
        reject_duplicates(ids, namespace)

    @staticmethod
    def _resolve_endpoint(
        endpoint: ConnectionEndpoint,
        ports_by_block: dict[str, dict[str, FunctionalPort]],
        role: str,
    ) -> FunctionalPort:
        try:
            ports = ports_by_block[endpoint.block_id]
        except KeyError as exc:
            raise ValueError(f"connection {role} references unknown block {endpoint.block_id}") from exc
        try:
            return ports[endpoint.port_id]
        except KeyError as exc:
            raise ValueError(f"connection {role} references unknown port {endpoint.port_id}") from exc

    @staticmethod
    def _validate_mapping_target(
        target: MappingTarget,
        block_ids: set[str],
        power_domain_ids: set[str],
        interface_ids: set[str],
        connection_ids: set[str],
        decision_ids: set[str],
    ) -> None:
        known_by_type = {
            MappingTargetType.FUNCTIONAL_BLOCK: block_ids,
            MappingTargetType.POWER_DOMAIN: power_domain_ids,
            MappingTargetType.INTERFACE: interface_ids,
            MappingTargetType.BLOCK_CONNECTION: connection_ids,
            MappingTargetType.ARCHITECTURE_DECISION: decision_ids,
        }
        if target.id not in known_by_type[target.type]:
            raise ValueError(f"mapping target references unknown {target.type}: {target.id}")
