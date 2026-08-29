"""LLM-facing CircuitIR draft contracts.

Draft objects are proposal data only. Deterministic enrichment creates
canonical CircuitIR objects and owns stable IDs, revision, and source linkage.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schematic_ai.domain.circuit_ir import (
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
from schematic_ai.domain.circuit_ir.models import CircuitValue
from schematic_ai.domain.requirements.validation import reject_duplicates, require_identifier, require_nonblank


class CircuitDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CircuitAssumptionTopic(StrEnum):
    POWER = "power"
    GROUNDING = "grounding"
    INTERFACE = "interface"
    SIGNAL = "signal"
    TIMING = "timing"
    COMPONENT_SELECTION = "component_selection"
    VALUE_SELECTION = "value_selection"
    CONNECTIVITY = "connectivity"
    THERMAL_CONTEXT = "thermal_context"
    ENVIRONMENT = "environment"
    IMPLEMENTATION = "implementation"
    OTHER = "other"


class DraftComponentParameter(CircuitDraftModel):
    name: str
    value: CircuitValue
    source: str | None = None

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


class DraftPin(CircuitDraftModel):
    draft_pin_id: str
    component_draft_id: str
    function: str
    pin_name: str | None = None
    pin_number: str | None = None
    electrical_type: PinElectricalType = PinElectricalType.UNSPECIFIED
    resolution_status: PinResolutionStatus = PinResolutionStatus.UNRESOLVED
    connection_intent: PinConnectionState = PinConnectionState.UNRESOLVED

    @field_validator("draft_pin_id", "component_draft_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft pin id")

    @field_validator("function")
    @classmethod
    def function_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "pin function")

    @field_validator("pin_name", "pin_number")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "pin text")


class DraftComponentInstance(CircuitDraftModel):
    draft_id: str
    role: str
    component_class: CircuitComponentRole
    resolution_intent: ComponentResolutionStatus = ComponentResolutionStatus.UNRESOLVED
    proposed_component_record_id: str | None = None
    reference_designator_hint: str | None = None
    value: CircuitValue | None = None
    parameters: list[DraftComponentParameter] = Field(default_factory=list)
    source_design_plan_refs: list[str] = Field(default_factory=list)
    source_requirement_refs: list[str] = Field(default_factory=list)
    pin_drafts: list[DraftPin] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("draft_id")
    @classmethod
    def draft_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_id")

    @field_validator("role")
    @classmethod
    def role_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "component role")

    @field_validator("proposed_component_record_id")
    @classmethod
    def optional_component_id_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "component_record_id")

    @field_validator("reference_designator_hint")
    @classmethod
    def optional_refdes_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "reference designator hint")

    @field_validator("source_design_plan_refs", "source_requirement_refs")
    @classmethod
    def source_refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "source reference") for item in value]
        return reject_duplicates(ids, "source references")

    @model_validator(mode="after")
    def pin_drafts_must_belong_to_component(self) -> "DraftComponentInstance":
        reject_duplicates([pin.draft_pin_id for pin in self.pin_drafts], f"{self.draft_id} draft pin IDs")
        for pin in self.pin_drafts:
            if pin.component_draft_id != self.draft_id:
                raise ValueError(f"{pin.draft_pin_id} belongs to {pin.component_draft_id}, not {self.draft_id}")
        return self


class DraftNetConnection(CircuitDraftModel):
    component_draft_id: str
    draft_pin_id: str

    @field_validator("component_draft_id", "draft_pin_id")
    @classmethod
    def ids_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft net connection")


class DraftNet(CircuitDraftModel):
    draft_net_id: str
    name_hint: str | None = None
    role: NetRole = NetRole.UNKNOWN
    connections: list[DraftNetConnection] = Field(default_factory=list)
    power_domain_ref: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("draft_net_id")
    @classmethod
    def draft_net_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_net_id")

    @field_validator("name_hint")
    @classmethod
    def optional_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "net name")

    @field_validator("power_domain_ref")
    @classmethod
    def optional_power_domain_ref_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_identifier(value, "power_domain_ref")

    @model_validator(mode="after")
    def connections_must_be_unique(self) -> "DraftNet":
        reject_duplicates(
            [f"{connection.component_draft_id}:{connection.draft_pin_id}" for connection in self.connections],
            f"{self.draft_net_id} connections",
        )
        return self


class DraftImplementationMapping(CircuitDraftModel):
    draft_mapping_id: str
    design_plan_refs: list[str] = Field(default_factory=list)
    circuit_draft_refs: list[str] = Field(default_factory=list)
    mapping_type: ImplementationMappingType
    status: ImplementationStatus = ImplementationStatus.PARTIAL
    rationale: str | None = None

    @field_validator("draft_mapping_id")
    @classmethod
    def draft_mapping_id_must_be_valid(cls, value: str) -> str:
        return require_identifier(value, "draft_mapping_id")

    @field_validator("design_plan_refs", "circuit_draft_refs")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "mapping reference") for item in value]
        return reject_duplicates(ids, "mapping references")

    @field_validator("rationale")
    @classmethod
    def optional_rationale_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_nonblank(value, "mapping rationale")


class DraftCircuitAssumption(CircuitDraftModel):
    semantic_topic: CircuitAssumptionTopic = CircuitAssumptionTopic.OTHER
    statement: str
    target_draft_refs: list[str] = Field(default_factory=list)
    source: str

    @field_validator("statement", "source")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "assumption text")

    @field_validator("target_draft_refs")
    @classmethod
    def target_refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "assumption target") for item in value]
        return reject_duplicates(ids, "assumption targets")


class DraftOpenImplementationDecision(CircuitDraftModel):
    topic: str
    description: str
    target_draft_refs: list[str] = Field(default_factory=list)
    blocking: bool
    options: list[str] = Field(default_factory=list)
    driven_by_design_plan_refs: list[str] = Field(default_factory=list)
    status: OpenImplementationDecisionStatus = OpenImplementationDecisionStatus.OPEN

    @field_validator("topic", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        return require_nonblank(value, "open decision text")

    @field_validator("target_draft_refs", "driven_by_design_plan_refs")
    @classmethod
    def refs_must_be_valid(cls, value: list[str]) -> list[str]:
        ids = [require_identifier(item, "open decision reference") for item in value]
        return reject_duplicates(ids, "open decision references")

    @field_validator("options")
    @classmethod
    def options_must_not_be_blank(cls, value: list[str]) -> list[str]:
        return reject_duplicates([require_nonblank(item, "option") for item in value], "open decision options")


class CircuitIRDraft(CircuitDraftModel):
    component_instances: list[DraftComponentInstance] = Field(default_factory=list)
    nets: list[DraftNet] = Field(default_factory=list)
    implementation_mappings: list[DraftImplementationMapping] = Field(default_factory=list)
    assumptions: list[DraftCircuitAssumption] = Field(default_factory=list)
    open_decisions: list[DraftOpenImplementationDecision] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_draft_references(self) -> "CircuitIRDraft":
        component_ids = [component.draft_id for component in self.component_instances]
        net_ids = [net.draft_net_id for net in self.nets]
        mapping_ids = [mapping.draft_mapping_id for mapping in self.implementation_mappings]
        reject_duplicates(component_ids, "draft component IDs")
        reject_duplicates(net_ids, "draft net IDs")
        reject_duplicates(mapping_ids, "draft mapping IDs")

        pins_by_component: dict[str, set[str]] = {}
        all_pin_ids: list[str] = []
        for component in self.component_instances:
            pin_ids = [pin.draft_pin_id for pin in component.pin_drafts]
            pins_by_component[component.draft_id] = set(pin_ids)
            all_pin_ids.extend(pin_ids)
        reject_duplicates(all_pin_ids, "draft pin IDs")

        known_components = set(component_ids)
        known_nets = set(net_ids)
        known_pins = set(all_pin_ids)
        known_circuit_refs = known_components | known_nets | known_pins

        pin_to_net: dict[str, str] = {}
        for net in self.nets:
            for connection in net.connections:
                if connection.component_draft_id not in known_components:
                    raise ValueError(f"{net.draft_net_id} references unknown component {connection.component_draft_id}")
                if connection.draft_pin_id not in known_pins:
                    raise ValueError(f"{net.draft_net_id} references unknown pin {connection.draft_pin_id}")
                if connection.draft_pin_id not in pins_by_component[connection.component_draft_id]:
                    raise ValueError(
                        f"{net.draft_net_id} references pin {connection.draft_pin_id} not owned by {connection.component_draft_id}"
                    )
                if connection.draft_pin_id in pin_to_net:
                    raise ValueError(
                        f"{connection.draft_pin_id} is connected to multiple draft nets: "
                        f"{pin_to_net[connection.draft_pin_id]}, {net.draft_net_id}"
                    )
                pin_to_net[connection.draft_pin_id] = net.draft_net_id

        for component in self.component_instances:
            for pin in component.pin_drafts:
                appears_on_net = pin.draft_pin_id in pin_to_net
                if pin.connection_intent == PinConnectionState.CONNECTED and not appears_on_net:
                    raise ValueError(f"{pin.draft_pin_id} is marked connected but is not on a draft net")
                if pin.connection_intent in {PinConnectionState.NO_CONNECT, PinConnectionState.UNRESOLVED} and appears_on_net:
                    raise ValueError(f"{pin.draft_pin_id} is {pin.connection_intent} but appears on {pin_to_net[pin.draft_pin_id]}")

        for mapping in self.implementation_mappings:
            for ref in mapping.circuit_draft_refs:
                if ref not in known_circuit_refs:
                    raise ValueError(f"{mapping.draft_mapping_id} references unknown circuit draft object {ref}")

        for assumption in self.assumptions:
            for ref in assumption.target_draft_refs:
                if ref not in known_circuit_refs:
                    raise ValueError(f"assumption references unknown circuit draft object {ref}")
        assumption_keys = [
            f"{assumption.semantic_topic}:{assumption.source}:{','.join(sorted(assumption.target_draft_refs))}"
            for assumption in self.assumptions
        ]
        reject_duplicates(assumption_keys, "draft assumption semantic keys")

        for decision in self.open_decisions:
            for ref in decision.target_draft_refs:
                if ref not in known_circuit_refs:
                    raise ValueError(f"{decision.topic} references unknown circuit draft object {ref}")

        return self
