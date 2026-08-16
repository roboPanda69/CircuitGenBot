"""LLM-facing architecture draft contracts.

These drafts are proposal data only. Deterministic enrichment creates canonical
DesignPlan objects and owns stable IDs, metadata, and source linkage.
"""

from __future__ import annotations

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


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DraftFunctionalPort(DraftModel):
    draft_id: str
    name: str
    kind: FunctionalPortKind
    direction: PortDirection
    power_domain_ref: str | None = None
    interface_ref: str | None = None

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "port name")

    @field_validator("power_domain_ref", "interface_ref")
    @classmethod
    def optional_refs_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "draft reference")


class DraftFunctionalBlock(DraftModel):
    draft_id: str
    type: FunctionalBlockType
    name: str
    purpose: str
    topology_class: FunctionalTopologyClass | None = None
    ports: list[DraftFunctionalPort] = Field(default_factory=list)
    status: FunctionalBlockStatus = FunctionalBlockStatus.PLANNED

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("name", "purpose")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "block text")

    @model_validator(mode="after")
    def port_ids_must_be_unique(self) -> "DraftFunctionalBlock":
        reject_duplicates([port.draft_id for port in self.ports], f"{self.draft_id} port IDs")
        return self


class DraftBlockConnection(DraftModel):
    draft_id: str
    source_block: str
    source_port: str
    target_block: str
    target_port: str
    kind: ConnectionKind
    description: str

    @field_validator("draft_id", "source_block", "source_port", "target_block", "target_port")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "connection draft id")

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "connection description")


class DraftPowerDomain(DraftModel):
    draft_id: str
    name: str
    role: PowerDomainRole
    voltage: Constraint | None = None
    source_block: str | None = None
    consumer_blocks: list[str] = Field(default_factory=list)

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "power domain name")

    @field_validator("source_block")
    @classmethod
    def optional_source_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "source_block")

    @field_validator("consumer_blocks")
    @classmethod
    def consumers_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "consumer block") for item in value]
        return reject_duplicates(ids, "consumer blocks")


class DraftInterface(DraftModel):
    draft_id: str
    type: InterfaceType
    name: str
    participants: list[str] = Field(min_length=1)
    direction: InterfaceDirection
    power_domain_ref: str | None = None

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "interface name")

    @field_validator("participants")
    @classmethod
    def participants_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "participant") for item in value]
        return reject_duplicates(ids, "participants")

    @field_validator("power_domain_ref")
    @classmethod
    def optional_power_domain_ref_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "power_domain_ref")


class DraftMappingTarget(DraftModel):
    type: MappingTargetType
    draft_id: str

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "mapping target draft_id")


class DraftRequirementMapping(DraftModel):
    requirement_id: str
    targets: list[DraftMappingTarget] = Field(default_factory=list)
    status: RequirementMappingStatus

    @field_validator("requirement_id")
    @classmethod
    def requirement_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "requirement_id")


class DraftArchitectureDecision(DraftModel):
    draft_id: str
    type: ArchitectureDecisionType
    target: DraftMappingTarget
    choice: ArchitectureChoice
    rationale: str
    driven_by_requirements: list[str] = Field(default_factory=list)
    status: ArchitectureDecisionStatus = ArchitectureDecisionStatus.PROPOSED
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "rationale")

    @field_validator("driven_by_requirements")
    @classmethod
    def driven_requirements_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "driven_by_requirements") for item in value]
        return reject_duplicates(ids, "driven_by_requirements")


class DraftDesignAssumption(DraftModel):
    description: str
    impact: Impact
    status: Literal["active", "resolved", "dismissed"] = "active"
    affected_blocks: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "assumption description")

    @field_validator("affected_blocks")
    @classmethod
    def affected_blocks_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "affected_blocks") for item in value]
        return reject_duplicates(ids, "affected_blocks")


class DraftOpenArchitectureDecision(DraftModel):
    topic: str
    description: str
    options: list[ArchitectureChoice] = Field(default_factory=list)
    blocking: bool
    status: OpenDecisionStatus = OpenDecisionStatus.OPEN
    affected_blocks: list[str] = Field(default_factory=list)

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
        ids = [require_identifier(item, "affected_blocks") for item in value]
        return reject_duplicates(ids, "affected_blocks")


class DesignPlanDraft(DraftModel):
    blocks: list[DraftFunctionalBlock] = Field(default_factory=list)
    connections: list[DraftBlockConnection] = Field(default_factory=list)
    power_domains: list[DraftPowerDomain] = Field(default_factory=list)
    interfaces: list[DraftInterface] = Field(default_factory=list)
    requirement_mappings: list[DraftRequirementMapping] = Field(default_factory=list)
    architecture_decisions: list[DraftArchitectureDecision] = Field(default_factory=list)
    assumptions: list[DraftDesignAssumption] = Field(default_factory=list)
    open_decisions: list[DraftOpenArchitectureDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_draft_references(self) -> "DesignPlanDraft":
        block_ids = [block.draft_id for block in self.blocks]
        power_domain_ids = [domain.draft_id for domain in self.power_domains]
        interface_ids = [interface.draft_id for interface in self.interfaces]
        connection_ids = [connection.draft_id for connection in self.connections]
        decision_ids = [decision.draft_id for decision in self.architecture_decisions]

        reject_duplicates(block_ids, "draft block IDs")
        reject_duplicates(power_domain_ids, "draft power domain IDs")
        reject_duplicates(interface_ids, "draft interface IDs")
        reject_duplicates(connection_ids, "draft connection IDs")
        reject_duplicates(decision_ids, "draft decision IDs")

        ports_by_block = {
            block.draft_id: {port.draft_id for port in block.ports}
            for block in self.blocks
        }
        known_blocks = set(block_ids)
        known_power_domains = set(power_domain_ids)
        known_interfaces = set(interface_ids)
        known_connections = set(connection_ids)
        known_decisions = set(decision_ids)

        for block in self.blocks:
            for port in block.ports:
                if port.power_domain_ref is not None and port.power_domain_ref not in known_power_domains:
                    raise ValueError(f"{port.draft_id} references unknown power domain {port.power_domain_ref}")
                if port.interface_ref is not None and port.interface_ref not in known_interfaces:
                    raise ValueError(f"{port.draft_id} references unknown interface {port.interface_ref}")

        for connection in self.connections:
            self._require_block_port(connection.source_block, connection.source_port, ports_by_block)
            self._require_block_port(connection.target_block, connection.target_port, ports_by_block)

        for domain in self.power_domains:
            if domain.source_block is not None and domain.source_block not in known_blocks:
                raise ValueError(f"{domain.draft_id} references unknown source block {domain.source_block}")
            for block_id in domain.consumer_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"{domain.draft_id} references unknown consumer block {block_id}")

        for interface in self.interfaces:
            for participant in interface.participants:
                if participant not in known_blocks:
                    raise ValueError(f"{interface.draft_id} references unknown participant {participant}")
            if interface.power_domain_ref is not None and interface.power_domain_ref not in known_power_domains:
                raise ValueError(f"{interface.draft_id} references unknown power domain {interface.power_domain_ref}")

        for mapping in self.requirement_mappings:
            for target in mapping.targets:
                self._require_target(target, known_blocks, known_power_domains, known_interfaces, known_connections, known_decisions)

        for decision in self.architecture_decisions:
            self._require_target(decision.target, known_blocks, known_power_domains, known_interfaces, known_connections, known_decisions)

        for assumption in self.assumptions:
            for block_id in assumption.affected_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"assumption references unknown block {block_id}")

        for open_decision in self.open_decisions:
            for block_id in open_decision.affected_blocks:
                if block_id not in known_blocks:
                    raise ValueError(f"open decision references unknown block {block_id}")

        return self

    @staticmethod
    def _require_block_port(block_id: str, port_id: str, ports_by_block: dict[str, set[str]]) -> None:
        if block_id not in ports_by_block:
            raise ValueError(f"unknown draft block {block_id}")
        if port_id not in ports_by_block[block_id]:
            raise ValueError(f"unknown draft port {port_id} on block {block_id}")

    @staticmethod
    def _require_target(
        target: DraftMappingTarget,
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
        if target.draft_id not in known_by_type[target.type]:
            raise ValueError(f"unknown draft target {target.type}: {target.draft_id}")
