"""CircuitIR v0.1 canonical electrical circuit representation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.circuit_ir.enums import (
    CircuitAssumptionStatus,
    CircuitComponentRole,
    ComponentResolutionStatus,
    ImplementationMappingType,
    ImplementationStatus,
    NetRole,
    OpenImplementationDecisionStatus,
    PinConnectionState,
    PinElectricalType,
    PinResolutionStatus,
)
from schematic_ai.domain.knowledge.models import FootprintReference, SymbolReference
from schematic_ai.domain.requirements.constraints import Quantity
from schematic_ai.domain.requirements.validation import (
    reject_duplicates,
    require_identifier,
    require_nonblank,
)


SCHEMA_VERSION = "0.1"


class CircuitIRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CircuitIRMetadata(CircuitIRModel):
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
    def updated_at_must_not_precede_created_at(self) -> "CircuitIRMetadata":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class SourceDesignPlan(CircuitIRModel):
    design_plan_id: str
    revision: int = Field(ge=1)

    @field_validator("design_plan_id")
    @classmethod
    def design_plan_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "design_plan_id")


class QuantityCircuitValue(CircuitIRModel):
    kind: Literal["quantity"] = "quantity"
    quantity: Quantity


class TextCircuitValue(CircuitIRModel):
    kind: Literal["text"] = "text"
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "circuit value")


class BooleanCircuitValue(CircuitIRModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class EnumCircuitValue(CircuitIRModel):
    kind: Literal["enum"] = "enum"
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "circuit value")


CircuitValue = Annotated[
    QuantityCircuitValue | TextCircuitValue | BooleanCircuitValue | EnumCircuitValue,
    Field(discriminator="kind"),
]


class ComponentParameter(CircuitIRModel):
    name: str
    value: CircuitValue
    source: str | None = None
    metadata: CircuitIRMetadata

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "parameter name")

    @field_validator("source")
    @classmethod
    def optional_source_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "parameter source")


class KnowledgeReference(CircuitIRModel):
    component_record_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    purpose: str | None = None

    @field_validator("component_record_id")
    @classmethod
    def optional_component_record_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_record_id")

    @field_validator("source_ids", "evidence_ids")
    @classmethod
    def reference_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "knowledge reference") for item in value]
        return reject_duplicates(ids, "knowledge references")

    @field_validator("purpose")
    @classmethod
    def optional_purpose_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "knowledge reference purpose")


class PinInstance(CircuitIRModel):
    pin_id: str
    component_instance_id: str
    pin_number: str | None = None
    pin_name: str | None = None
    electrical_type: PinElectricalType = PinElectricalType.UNSPECIFIED
    function: str | None = None
    resolution_status: PinResolutionStatus = PinResolutionStatus.UNRESOLVED
    connection_state: PinConnectionState = PinConnectionState.UNRESOLVED
    metadata: CircuitIRMetadata

    @field_validator("pin_id", "component_instance_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "pin id")

    @field_validator("pin_number", "pin_name", "function")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "pin text")

    @model_validator(mode="after")
    def resolved_pin_requires_pin_identifier(self) -> "PinInstance":
        if self.resolution_status == PinResolutionStatus.RESOLVED and self.pin_number is None and self.pin_name is None:
            raise ValueError("resolved pins require pin_number or pin_name")
        if self.connection_state == PinConnectionState.NO_CONNECT and self.electrical_type not in {
            PinElectricalType.NO_CONNECT,
            PinElectricalType.UNSPECIFIED,
            PinElectricalType.PASSIVE,
        }:
            raise ValueError("no_connect pins must use no_connect, unspecified, or passive electrical type")
        return self


class ComponentInstance(CircuitIRModel):
    instance_id: str
    reference_designator: str | None = None
    component_class: CircuitComponentRole
    role: str | None = None
    resolution_status: ComponentResolutionStatus
    component_record_id: str | None = None
    value: CircuitValue | None = None
    parameters: list[ComponentParameter] = Field(default_factory=list)
    pins: list[PinInstance] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    source_requirement_ids: list[str] = Field(default_factory=list)
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    symbol_reference: SymbolReference | None = None
    footprint_reference: FootprintReference | None = None
    implementation_status: ImplementationStatus = ImplementationStatus.UNRESOLVED
    metadata: CircuitIRMetadata

    @field_validator("instance_id")
    @classmethod
    def instance_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "instance_id")

    @field_validator("reference_designator", "role")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "component text")

    @field_validator("component_record_id")
    @classmethod
    def optional_component_record_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_record_id")

    @field_validator("source_block_ids", "source_requirement_ids")
    @classmethod
    def source_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "source id") for item in value]
        return reject_duplicates(ids, "source IDs")

    @model_validator(mode="after")
    def resolution_and_pin_ownership_must_be_valid(self) -> "ComponentInstance":
        if self.resolution_status == ComponentResolutionStatus.RESOLVED and self.component_record_id is None:
            raise ValueError("resolved components require component_record_id")
        if self.implementation_status == ImplementationStatus.RESOLVED:
            if self.resolution_status != ComponentResolutionStatus.RESOLVED:
                raise ValueError("resolved component implementation requires resolved component identity")
        reject_duplicates([pin.pin_id for pin in self.pins], "component pin IDs")
        for pin in self.pins:
            if pin.component_instance_id != self.instance_id:
                raise ValueError(f"{pin.pin_id} belongs to {pin.component_instance_id}, not {self.instance_id}")
            if self.implementation_status == ImplementationStatus.RESOLVED:
                if pin.resolution_status != PinResolutionStatus.RESOLVED:
                    raise ValueError("resolved component implementation requires resolved pins")
                if pin.connection_state == PinConnectionState.UNRESOLVED:
                    raise ValueError("resolved component implementation cannot contain unresolved pin connections")
        return self


class NetConnection(CircuitIRModel):
    component_instance_id: str
    pin_id: str

    @field_validator("component_instance_id", "pin_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "net connection")


class NetProperty(CircuitIRModel):
    name: str
    value: CircuitValue

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "net property name")


class Net(CircuitIRModel):
    net_id: str
    name: str | None = None
    net_class: str | None = None
    connections: list[NetConnection] = Field(default_factory=list)
    role: NetRole = NetRole.UNKNOWN
    power_domain_id: str | None = None
    properties: list[NetProperty] = Field(default_factory=list)
    metadata: CircuitIRMetadata

    @field_validator("net_id")
    @classmethod
    def net_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "net_id")

    @field_validator("name", "net_class")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "net text")

    @field_validator("power_domain_id")
    @classmethod
    def optional_power_domain_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "power_domain_id")

    @model_validator(mode="after")
    def net_connections_must_be_unique(self) -> "Net":
        reject_duplicates(
            [f"{connection.component_instance_id}:{connection.pin_id}" for connection in self.connections],
            "net connections",
        )
        return self


class ImplementationMapping(CircuitIRModel):
    mapping_id: str
    design_plan_object_ids: list[str] = Field(default_factory=list)
    circuit_object_ids: list[str] = Field(default_factory=list)
    mapping_type: ImplementationMappingType
    status: ImplementationStatus = ImplementationStatus.PARTIAL
    rationale: str | None = None

    @field_validator("mapping_id")
    @classmethod
    def mapping_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "mapping_id")

    @field_validator("design_plan_object_ids", "circuit_object_ids")
    @classmethod
    def mapping_refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "mapping reference") for item in value]
        return reject_duplicates(ids, "mapping references")

    @field_validator("rationale")
    @classmethod
    def optional_rationale_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "mapping rationale")

    @model_validator(mode="after")
    def endpoints_must_be_meaningful(self) -> "ImplementationMapping":
        if not self.design_plan_object_ids:
            raise ValueError("implementation mappings require at least one DesignPlan object")
        if not self.circuit_object_ids:
            raise ValueError("implementation mappings require at least one CircuitIR object")
        return self


class CircuitAssumption(CircuitIRModel):
    assumption_id: str
    statement: str
    target_object_ids: list[str] = Field(default_factory=list)
    source: str
    status: CircuitAssumptionStatus = CircuitAssumptionStatus.ACTIVE
    metadata: CircuitIRMetadata

    @field_validator("assumption_id")
    @classmethod
    def assumption_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "assumption_id")

    @field_validator("statement", "source")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "circuit assumption text")

    @field_validator("target_object_ids")
    @classmethod
    def target_ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "target object id") for item in value]
        return reject_duplicates(ids, "assumption target IDs")


class OpenImplementationDecision(CircuitIRModel):
    decision_id: str
    topic: str
    target_object_ids: list[str] = Field(default_factory=list)
    description: str
    blocking: bool
    options: list[str] = Field(default_factory=list)
    driven_by_design_plan_ids: list[str] = Field(default_factory=list)
    status: OpenImplementationDecisionStatus = OpenImplementationDecisionStatus.OPEN
    metadata: CircuitIRMetadata

    @field_validator("decision_id")
    @classmethod
    def decision_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "decision_id")

    @field_validator("topic", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "open implementation decision text")

    @field_validator("target_object_ids", "driven_by_design_plan_ids")
    @classmethod
    def ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "open decision reference") for item in value]
        return reject_duplicates(ids, "open decision references")

    @field_validator("options")
    @classmethod
    def options_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_nonblank(item, "open decision option") for item in value], "open decision options")


class CircuitGroup(CircuitIRModel):
    group_id: str
    name: str
    component_ids: list[str] = Field(default_factory=list)
    net_ids: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    metadata: CircuitIRMetadata

    @field_validator("group_id")
    @classmethod
    def group_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "group_id")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "group name")

    @field_validator("component_ids", "net_ids", "source_block_ids")
    @classmethod
    def ids_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "group reference") for item in value]
        return reject_duplicates(ids, "group references")


class CircuitInterfaceBinding(CircuitIRModel):
    binding_id: str
    design_plan_interface_id: str
    net_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    description: str | None = None
    metadata: CircuitIRMetadata

    @field_validator("binding_id", "design_plan_interface_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "interface binding id")

    @field_validator("net_ids", "component_ids")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "interface binding reference") for item in value]
        return reject_duplicates(ids, "interface binding references")

    @field_validator("description")
    @classmethod
    def optional_description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "interface binding description")


class CircuitIR(CircuitIRModel):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    circuit_id: str
    project_id: str
    revision: int = Field(ge=1)
    source_design_plan: SourceDesignPlan
    implementation_status: ImplementationStatus = ImplementationStatus.UNRESOLVED
    components: list[ComponentInstance] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    interface_bindings: list[CircuitInterfaceBinding] = Field(default_factory=list)
    implementation_mappings: list[ImplementationMapping] = Field(default_factory=list)
    assumptions: list[CircuitAssumption] = Field(default_factory=list)
    open_decisions: list[OpenImplementationDecision] = Field(default_factory=list)
    groups: list[CircuitGroup] = Field(default_factory=list)
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    metadata: CircuitIRMetadata

    @field_validator("circuit_id", "project_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "circuit id")

    @model_validator(mode="after")
    def structural_references_must_be_valid(self) -> "CircuitIR":
        component_ids = [component.instance_id for component in self.components]
        net_ids = [net.net_id for net in self.nets]
        mapping_ids = [mapping.mapping_id for mapping in self.implementation_mappings]
        assumption_ids = [assumption.assumption_id for assumption in self.assumptions]
        decision_ids = [decision.decision_id for decision in self.open_decisions]
        group_ids = [group.group_id for group in self.groups]
        binding_ids = [binding.binding_id for binding in self.interface_bindings]

        reject_duplicates(component_ids, "component instance IDs")
        reject_duplicates(net_ids, "net IDs")
        reject_duplicates(mapping_ids, "implementation mapping IDs")
        reject_duplicates(assumption_ids, "circuit assumption IDs")
        reject_duplicates(decision_ids, "open implementation decision IDs")
        reject_duplicates(group_ids, "circuit group IDs")
        reject_duplicates(binding_ids, "interface binding IDs")

        pins_by_component: dict[str, set[str]] = {}
        all_pin_ids: list[str] = []
        for component in self.components:
            pin_ids = [pin.pin_id for pin in component.pins]
            pins_by_component[component.instance_id] = set(pin_ids)
            all_pin_ids.extend(pin_ids)
        reject_duplicates(all_pin_ids, "pin IDs")

        known_components = set(component_ids)
        known_nets = set(net_ids)
        known_pins = set(all_pin_ids)
        known_circuit_objects = known_components | known_nets | known_pins | set(mapping_ids) | set(assumption_ids) | set(decision_ids) | set(group_ids) | set(binding_ids)

        pin_to_net: dict[str, str] = {}
        for net in self.nets:
            for connection in net.connections:
                if connection.component_instance_id not in known_components:
                    raise ValueError(f"{net.net_id} references unknown component {connection.component_instance_id}")
                if connection.pin_id not in known_pins:
                    raise ValueError(f"{net.net_id} references unknown pin {connection.pin_id}")
                if connection.pin_id not in pins_by_component[connection.component_instance_id]:
                    raise ValueError(f"{net.net_id} references pin {connection.pin_id} not owned by {connection.component_instance_id}")
                if connection.pin_id in pin_to_net:
                    raise ValueError(f"{connection.pin_id} is connected to multiple nets: {pin_to_net[connection.pin_id]}, {net.net_id}")
                pin_to_net[connection.pin_id] = net.net_id

        for component in self.components:
            for pin in component.pins:
                appears_on_net = pin.pin_id in pin_to_net
                if pin.connection_state == PinConnectionState.CONNECTED and not appears_on_net:
                    raise ValueError(f"{pin.pin_id} is marked connected but is not on a net")
                if pin.connection_state == PinConnectionState.NO_CONNECT and appears_on_net:
                    raise ValueError(f"{pin.pin_id} is no_connect but appears on {pin_to_net[pin.pin_id]}")
                if pin.connection_state == PinConnectionState.UNRESOLVED and appears_on_net:
                    raise ValueError(f"{pin.pin_id} is unresolved but appears on {pin_to_net[pin.pin_id]}")

        for mapping in self.implementation_mappings:
            for object_id in mapping.circuit_object_ids:
                if object_id not in known_circuit_objects:
                    raise ValueError(f"{mapping.mapping_id} references unknown circuit object {object_id}")

        for assumption in self.assumptions:
            for object_id in assumption.target_object_ids:
                if object_id not in known_circuit_objects:
                    raise ValueError(f"{assumption.assumption_id} references unknown circuit object {object_id}")

        for decision in self.open_decisions:
            for object_id in decision.target_object_ids:
                if object_id not in known_circuit_objects:
                    raise ValueError(f"{decision.decision_id} references unknown circuit object {object_id}")

        for group in self.groups:
            for component_id in group.component_ids:
                if component_id not in known_components:
                    raise ValueError(f"{group.group_id} references unknown component {component_id}")
            for net_id in group.net_ids:
                if net_id not in known_nets:
                    raise ValueError(f"{group.group_id} references unknown net {net_id}")

        for binding in self.interface_bindings:
            for component_id in binding.component_ids:
                if component_id not in known_components:
                    raise ValueError(f"{binding.binding_id} references unknown component {component_id}")
            for net_id in binding.net_ids:
                if net_id not in known_nets:
                    raise ValueError(f"{binding.binding_id} references unknown net {net_id}")

        if self.implementation_status == ImplementationStatus.RESOLVED:
            self._validate_resolved_status_consistency()

        return self

    def _validate_resolved_status_consistency(self) -> None:
        for component in self.components:
            if component.resolution_status != ComponentResolutionStatus.RESOLVED:
                raise ValueError(
                    f"resolved CircuitIR cannot contain {component.resolution_status} component {component.instance_id}"
                )
            if component.implementation_status != ImplementationStatus.RESOLVED:
                raise ValueError(
                    f"resolved CircuitIR cannot contain {component.implementation_status} component implementation {component.instance_id}"
                )
            for pin in component.pins:
                if pin.resolution_status != PinResolutionStatus.RESOLVED:
                    raise ValueError(f"resolved CircuitIR cannot contain {pin.resolution_status} pin {pin.pin_id}")
                if pin.connection_state == PinConnectionState.UNRESOLVED:
                    raise ValueError(f"resolved CircuitIR cannot contain unresolved pin connection {pin.pin_id}")

        for mapping in self.implementation_mappings:
            if mapping.status != ImplementationStatus.RESOLVED:
                raise ValueError(f"resolved CircuitIR cannot contain {mapping.status} implementation mapping {mapping.mapping_id}")

        for decision in self.open_decisions:
            if decision.blocking and decision.status == OpenImplementationDecisionStatus.OPEN:
                raise ValueError(f"resolved CircuitIR cannot contain blocking open implementation decision {decision.decision_id}")


def next_circuit_revision(circuit: CircuitIR, *, updated_at: datetime | None = None) -> CircuitIR:
    data = circuit.model_dump(mode="json")
    data["revision"] = circuit.revision + 1
    data["metadata"]["updated_at"] = (updated_at or datetime.now(timezone.utc)).isoformat()
    return CircuitIR.model_validate(data)
