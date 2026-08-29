"""Deterministic CircuitIRDraft to CircuitIR enrichment."""

from __future__ import annotations

import re
from hashlib import sha1
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from schematic_ai.application.circuit_planner.context import CircuitPlanningContext
from schematic_ai.application.circuit_planner.drafts import (
    CircuitAssumptionTopic,
    CircuitIRDraft,
    DraftComponentInstance,
)
from schematic_ai.application.circuit_planner.result import CircuitPlanningIssue
from schematic_ai.domain.circuit_ir import (
    CircuitAssumption,
    CircuitComponentRole,
    CircuitGroup,
    CircuitIR,
    CircuitIRMetadata,
    CircuitInterfaceBinding,
    ComponentInstance,
    ComponentParameter,
    ComponentResolutionStatus,
    ImplementationMappingType,
    ImplementationStatus,
    KnowledgeReference,
    Net,
    NetConnection,
    NetRole,
    OpenImplementationDecision,
    PinConnectionState,
    PinInstance,
    PinResolutionStatus,
    QuantityCircuitValue,
    SourceDesignPlan,
)
from schematic_ai.domain.circuit_ir.models import ImplementationMapping
from schematic_ai.domain.design_plan import InterfaceType
from schematic_ai.domain.knowledge import ComponentRecord, KnowledgeState


_INSTANCE_PREFIX = {
    CircuitComponentRole.CONVERTER: "U_PWR",
    CircuitComponentRole.REGULATOR: "U_REG",
    CircuitComponentRole.CAPACITOR: "C",
    CircuitComponentRole.INDUCTOR: "L",
    CircuitComponentRole.RESISTOR: "R",
    CircuitComponentRole.CONNECTOR: "J",
    CircuitComponentRole.DIODE: "D",
    CircuitComponentRole.PROTECTION_DEVICE: "D_PROT",
    CircuitComponentRole.MOSFET: "Q",
    CircuitComponentRole.TRANSISTOR: "Q",
    CircuitComponentRole.SENSOR: "U_SENSOR",
    CircuitComponentRole.INTERFACE_IC: "U_IF",
    CircuitComponentRole.LOGIC: "U_LOGIC",
    CircuitComponentRole.OP_AMP: "U_OP",
    CircuitComponentRole.ISOLATOR: "U_ISO",
    CircuitComponentRole.RELAY: "K",
}

_REFDES_PREFIX = {
    CircuitComponentRole.CONVERTER: "U",
    CircuitComponentRole.REGULATOR: "U",
    CircuitComponentRole.CAPACITOR: "C",
    CircuitComponentRole.INDUCTOR: "L",
    CircuitComponentRole.RESISTOR: "R",
    CircuitComponentRole.CONNECTOR: "J",
    CircuitComponentRole.DIODE: "D",
    CircuitComponentRole.PROTECTION_DEVICE: "D",
    CircuitComponentRole.MOSFET: "Q",
    CircuitComponentRole.TRANSISTOR: "Q",
    CircuitComponentRole.RELAY: "K",
}


@dataclass
class CircuitIREnricher:
    def build_circuit_ir(
        self,
        *,
        draft: CircuitIRDraft,
        context: CircuitPlanningContext,
        selected_component_ids: dict[str, str],
        planning_issues: list[CircuitPlanningIssue],
        created_at: datetime | None = None,
    ) -> CircuitIR:
        timestamp = created_at or datetime.now(timezone.utc)
        metadata = CircuitIRMetadata(created_at=timestamp, updated_at=timestamp, created_by="circuit_planner")
        existing = context.existing_circuit_ir

        component_id_by_draft = self._component_ids_by_draft(draft, existing)
        net_id_by_draft = self._net_ids_by_draft(draft, existing)
        pin_id_by_draft: dict[tuple[str, str], str] = {}
        reference_designators = reference_designators_by_instance(draft, component_id_by_draft, existing)

        components: list[ComponentInstance] = []
        for component in draft.component_instances:
            instance_id = component_id_by_draft[component.draft_id]
            pin_ids = self._pin_ids(component, instance_id, existing)
            pin_id_by_draft.update({(component.draft_id, draft_pin_id): pin_id for draft_pin_id, pin_id in pin_ids.items()})
            selected_record_id = selected_component_ids.get(component.draft_id)
            component_record_id = selected_record_id
            if selected_record_id is not None:
                resolution_status = ComponentResolutionStatus.RESOLVED
            else:
                resolution_status = non_resolved_status(component.resolution_intent)
            canonical_value, canonical_parameters = resolved_value_and_parameters(
                component,
                selected_record_id,
                context,
                metadata,
            )
            pins = [
                PinInstance(
                    pin_id=pin_ids[pin.draft_pin_id],
                    component_instance_id=instance_id,
                    pin_number=None,
                    pin_name=pin.pin_name,
                    electrical_type=pin.electrical_type,
                    function=pin.function,
                    resolution_status=PinResolutionStatus.UNRESOLVED,
                    connection_state=pin.connection_intent,
                    metadata=metadata,
                )
                for pin in component.pin_drafts
            ]
            components.append(
                ComponentInstance(
                    instance_id=instance_id,
                    reference_designator=reference_designators[instance_id],
                    component_class=component.component_class,
                    role=component.role,
                    resolution_status=resolution_status,
                    component_record_id=component_record_id,
                    value=canonical_value,
                    parameters=canonical_parameters,
                    pins=pins,
                    source_block_ids=[ref for ref in component.source_design_plan_refs if ref.startswith("BLOCK_")],
                    source_requirement_ids=[ref for ref in component.source_requirement_refs if ref in requirement_ids(context)],
                    knowledge_references=knowledge_references_for_component(component_record_id, context),
                    implementation_status=component_implementation_status(resolution_status, pins),
                    metadata=metadata,
                )
            )

        nets = [
            Net(
                net_id=net_id_by_draft[net.draft_net_id],
                name=canonical_net_name(net.name_hint, net.role),
                net_class=net.role.value,
                connections=[
                    NetConnection(
                        component_instance_id=component_id_by_draft[connection.component_draft_id],
                        pin_id=pin_id_by_draft[(connection.component_draft_id, connection.draft_pin_id)],
                    )
                    for connection in net.connections
                ],
                role=net.role,
                power_domain_id=net.power_domain_ref,
                properties=[],
                metadata=metadata,
            )
            for net in draft.nets
        ]

        circuit_object_ids = set(component_id_by_draft.values()) | set(net_id_by_draft.values()) | set(pin_id_by_draft.values())
        mapping_id_by_draft = self._mapping_ids_by_draft(draft, component_id_by_draft, net_id_by_draft, pin_id_by_draft, existing)
        mappings = []
        for mapping in draft.implementation_mappings:
            resolved_refs = [resolve_draft_ref(ref, component_id_by_draft, net_id_by_draft, pin_id_by_draft) for ref in mapping.circuit_draft_refs]
            mappings.append(
                ImplementationMapping(
                    mapping_id=mapping_id_by_draft[mapping.draft_mapping_id],
                    design_plan_object_ids=mapping.design_plan_refs,
                    circuit_object_ids=resolved_refs,
                    mapping_type=mapping.mapping_type,
                    status=mapping.status,
                    rationale=mapping.rationale,
                )
            )

        if not mappings:
            mappings = generated_mappings(draft, component_id_by_draft, net_id_by_draft, existing)

        assumption_ids = self._assumption_ids_by_draft(draft, component_id_by_draft, net_id_by_draft, pin_id_by_draft, existing)
        assumptions = []
        for assumption in draft.assumptions:
            target_object_ids = [
                ref
                for ref in (
                    resolve_draft_ref(ref, component_id_by_draft, net_id_by_draft, pin_id_by_draft)
                    for ref in assumption.target_draft_refs
                )
                if ref in circuit_object_ids
            ]
            assumptions.append(
                CircuitAssumption(
                    assumption_id=assumption_ids[id(assumption)],
                    statement=assumption.statement,
                    target_object_ids=target_object_ids,
                    source=assumption.source,
                    metadata=metadata,
                )
            )

        open_decision_ids = self._open_decision_ids_by_draft(draft, component_id_by_draft, net_id_by_draft, pin_id_by_draft, existing)
        open_decisions = []
        used_decision_ids = set()
        for decision in draft.open_decisions:
            target_object_ids = [
                ref
                for ref in (
                    resolve_draft_ref(ref, component_id_by_draft, net_id_by_draft, pin_id_by_draft)
                    for ref in decision.target_draft_refs
                )
                if ref in circuit_object_ids
            ]
            decision_id = open_decision_ids[id(decision)]
            used_decision_ids.add(decision_id)
            open_decisions.append(
                OpenImplementationDecision(
                    decision_id=decision_id,
                    topic=decision.topic,
                    target_object_ids=target_object_ids,
                    description=decision.description,
                    blocking=decision.blocking,
                    options=decision.options,
                    driven_by_design_plan_ids=decision.driven_by_design_plan_refs,
                    status=decision.status,
                    metadata=metadata,
                )
            )
        for issue in planning_issues:
            if issue.blocking or issue.issue_type in {"knowledge_missing", "no_candidate", "constraint_conflict"}:
                decision_id = self._issue_decision_id(issue, circuit_object_ids, existing, used_decision_ids)
                used_decision_ids.add(decision_id)
                open_decisions.append(
                    OpenImplementationDecision(
                        decision_id=decision_id,
                        topic=issue.issue_type.value,
                        target_object_ids=[target for target in issue.target_ids if target in circuit_object_ids],
                        description=issue.description,
                        blocking=issue.blocking,
                        options=[],
                        driven_by_design_plan_ids=issue.related_design_plan_ids,
                        metadata=metadata,
                    )
                )

        interface_bindings = generated_interface_bindings(context, nets, components, metadata, existing)
        group_source_block_ids = sorted({block for component in components for block in component.source_block_ids})
        implementation_status = circuit_implementation_status(components, mappings, open_decisions)
        return CircuitIR(
            circuit_id=existing.circuit_id if existing else "CIR_0001",
            project_id=context.design_plan.project_id,
            revision=(existing.revision + 1) if existing else 1,
            source_design_plan=SourceDesignPlan(
                design_plan_id=context.design_plan.design_plan_id,
                revision=context.design_plan.revision,
            ),
            implementation_status=implementation_status,
            components=components,
            nets=nets,
            interface_bindings=interface_bindings,
            implementation_mappings=mappings,
            assumptions=assumptions,
            open_decisions=open_decisions,
            groups=[
                CircuitGroup(
                    group_id=self._group_id(group_source_block_ids, existing),
                    name="Circuit planner generated implementation",
                    component_ids=[component.instance_id for component in components],
                    net_ids=[net.net_id for net in nets],
                    source_block_ids=group_source_block_ids,
                    metadata=metadata,
                )
            ]
            if components or nets
            else [],
            knowledge_references=knowledge_references_for_selected(selected_component_ids.values(), context),
            metadata=metadata,
        )

    def _component_ids_by_draft(self, draft: CircuitIRDraft, existing) -> dict[str, str]:
        existing_by_signature: dict[tuple[str, ...], list[str]] = {}
        if existing is not None:
            for component in existing.components:
                existing_by_signature.setdefault(component_semantic_key(component), []).append(component.instance_id)
            for ids in existing_by_signature.values():
                ids.sort()
        allocators = allocators_from_existing(existing, "instance_id")
        result = {}
        used = set()
        for component in sorted(draft.component_instances, key=draft_component_sort_key):
            signature = draft_component_semantic_key(component)
            existing_id = next((item_id for item_id in existing_by_signature.get(signature, []) if item_id not in used), None)
            if existing_id and existing_id not in used:
                result[component.draft_id] = existing_id
                used.add(existing_id)
                continue
            prefix = _INSTANCE_PREFIX.get(component.component_class, "COMP")
            result[component.draft_id] = allocators.setdefault(prefix, SequentialAllocator(prefix, ())).next()
        return result

    def _net_ids_by_draft(self, draft: CircuitIRDraft, existing) -> dict[str, str]:
        existing_by_key: dict[tuple[str, ...], list[str]] = {}
        if existing is not None:
            for net in existing.nets:
                existing_by_key.setdefault(net_semantic_key(net.name, net.role, net.power_domain_id), []).append(net.net_id)
            for ids in existing_by_key.values():
                ids.sort()
        allocators = allocators_from_existing(existing, "net_id")
        result = {}
        used = set()
        for net in sorted(draft.nets, key=draft_net_sort_key):
            name = canonical_net_name(net.name_hint, net.role)
            existing_id = next(
                (item_id for item_id in existing_by_key.get(net_semantic_key(name, net.role, net.power_domain_ref), []) if item_id not in used),
                None,
            )
            if existing_id and existing_id not in used:
                result[net.draft_net_id] = existing_id
                used.add(existing_id)
                continue
            prefix = f"NET_{net_role_prefix(net.role)}"
            result[net.draft_net_id] = allocators.setdefault(prefix, SequentialAllocator(prefix, ())).next()
        return result

    def _pin_ids(self, component: DraftComponentInstance, instance_id: str, existing) -> dict[str, str]:
        existing_pins = {}
        if existing is not None:
            for existing_component in existing.components:
                if existing_component.instance_id == instance_id:
                    existing_pins = {pin.function: pin.pin_id for pin in existing_component.pins if pin.function is not None}
        result = {}
        allocator = SequentialAllocator(f"PIN_{instance_id}", existing_pins.values())
        for pin in sorted(component.pin_drafts, key=lambda item: (item.function, item.pin_name or "", item.draft_pin_id)):
            result[pin.draft_pin_id] = existing_pins.get(pin.function) or allocator.next()
        return result

    def _mapping_ids_by_draft(
        self,
        draft: CircuitIRDraft,
        component_ids: dict[str, str],
        net_ids: dict[str, str],
        pin_ids: dict[tuple[str, str], str],
        existing,
    ) -> dict[str, str]:
        existing_by_key: dict[tuple[str, ...], list[str]] = {}
        if existing is not None:
            for mapping in existing.implementation_mappings:
                key = mapping_semantic_key(mapping.design_plan_object_ids, mapping.mapping_type, mapping.circuit_object_ids)
                existing_by_key.setdefault(key, []).append(mapping.mapping_id)
            for ids in existing_by_key.values():
                ids.sort()
        allocator = SequentialAllocator("CIMAP", [mapping.mapping_id for mapping in existing.implementation_mappings] if existing else ())
        result = {}
        used = set()
        mapping_keys = []
        for mapping in draft.implementation_mappings:
            circuit_refs = [
                resolve_draft_ref(ref, component_ids, net_ids, pin_ids)
                for ref in mapping.circuit_draft_refs
            ]
            mapping_keys.append((mapping, mapping_semantic_key(mapping.design_plan_refs, mapping.mapping_type, circuit_refs)))
        for mapping, key in sorted(mapping_keys, key=lambda item: (*item[1], item[0].draft_mapping_id)):
            existing_id = next((item_id for item_id in existing_by_key.get(key, []) if item_id not in used), None)
            if existing_id:
                result[mapping.draft_mapping_id] = existing_id
                used.add(existing_id)
            else:
                result[mapping.draft_mapping_id] = allocator.next()
        return result

    def _assumption_ids_by_draft(
        self,
        draft: CircuitIRDraft,
        component_ids: dict[str, str],
        net_ids: dict[str, str],
        pin_ids: dict[tuple[str, str], str],
        existing,
    ) -> dict[int, str]:
        existing_by_key: dict[tuple[str, ...], list[str]] = {}
        if existing is not None:
            for assumption in existing.assumptions:
                existing_topic = assumption_topic_from_id(assumption.assumption_id)
                if existing_topic is None:
                    continue
                existing_by_key.setdefault(
                    assumption_semantic_key(existing_topic, assumption.source, assumption.target_object_ids),
                    [],
                ).append(assumption.assumption_id)
            for ids in existing_by_key.values():
                ids.sort()
        allocator = SequentialAllocator("CIASM", [assumption.assumption_id for assumption in existing.assumptions] if existing else ())
        result: dict[int, str] = {}
        used = set()
        keyed_assumptions = []
        for assumption in draft.assumptions:
            targets = [
                resolve_draft_ref(ref, component_ids, net_ids, pin_ids)
                for ref in assumption.target_draft_refs
            ]
            keyed_assumptions.append((assumption, assumption_semantic_key(assumption.semantic_topic, assumption.source, targets)))
        for assumption, key in sorted(keyed_assumptions, key=lambda item: item[1]):
            existing_id = next((item_id for item_id in existing_by_key.get(key, []) if item_id not in used), None)
            if existing_id:
                result[id(assumption)] = existing_id
                used.add(existing_id)
            else:
                result[id(assumption)] = assumption_id_from_semantic_key(key)
        return result

    def _open_decision_ids_by_draft(
        self,
        draft: CircuitIRDraft,
        component_ids: dict[str, str],
        net_ids: dict[str, str],
        pin_ids: dict[tuple[str, str], str],
        existing,
    ) -> dict[int, str]:
        existing_by_key: dict[tuple[str, ...], list[str]] = {}
        if existing is not None:
            for decision in existing.open_decisions:
                existing_by_key.setdefault(
                    open_decision_semantic_key(decision.topic, decision.target_object_ids, decision.driven_by_design_plan_ids),
                    [],
                ).append(decision.decision_id)
            for ids in existing_by_key.values():
                ids.sort()
        allocator = SequentialAllocator("CIOD", [decision.decision_id for decision in existing.open_decisions] if existing else ())
        result: dict[int, str] = {}
        used = set()
        keyed_decisions = []
        for decision in draft.open_decisions:
            targets = [
                resolve_draft_ref(ref, component_ids, net_ids, pin_ids)
                for ref in decision.target_draft_refs
            ]
            keyed_decisions.append(
                (
                    decision,
                    open_decision_semantic_key(decision.topic, targets, decision.driven_by_design_plan_refs),
                )
            )
        for decision, key in sorted(keyed_decisions, key=lambda item: (*item[1], item[0].description)):
            existing_id = next((item_id for item_id in existing_by_key.get(key, []) if item_id not in used), None)
            if existing_id:
                result[id(decision)] = existing_id
                used.add(existing_id)
            else:
                result[id(decision)] = allocator.next()
        return result

    def _issue_decision_id(
        self,
        issue: CircuitPlanningIssue,
        circuit_object_ids: set[str],
        existing,
        used_decision_ids: set[str],
    ) -> str:
        key = open_decision_semantic_key(
            issue.issue_type.value,
            [target for target in issue.target_ids if target in circuit_object_ids],
            issue.related_design_plan_ids,
        )
        if existing is not None:
            for decision in sorted(existing.open_decisions, key=lambda item: item.decision_id):
                if decision.decision_id in used_decision_ids:
                    continue
                if open_decision_semantic_key(decision.topic, decision.target_object_ids, decision.driven_by_design_plan_ids) == key:
                    return decision.decision_id
        allocator = SequentialAllocator("CIOD", [*used_decision_ids, *([decision.decision_id for decision in existing.open_decisions] if existing else [])])
        return allocator.next()

    def _group_id(self, source_block_ids: list[str], existing) -> str:
        key = group_semantic_key(source_block_ids)
        if existing is not None:
            for group in sorted(existing.groups, key=lambda item: item.group_id):
                if group_semantic_key(group.source_block_ids) == key:
                    return group.group_id
        allocator = SequentialAllocator("CGRP", [group.group_id for group in existing.groups] if existing else ())
        return allocator.next()


class SequentialAllocator:
    def __init__(self, root: str, existing_ids: Iterable[str] = ()):
        self.root = root
        self.counter = 0
        for item_id in existing_ids:
            match = re.match(rf"^{re.escape(root)}_(\d+)$", item_id)
            if match:
                self.counter = max(self.counter, int(match.group(1)))

    def next(self) -> str:
        self.counter += 1
        return f"{self.root}_{self.counter:03d}"


class ReferenceDesignatorAllocator:
    def __init__(self, existing):
        self.counters = {}
        self.existing_refdes_by_instance_id = {}
        if existing is None:
            return
        for component in existing.components:
            if component.reference_designator is not None:
                self.existing_refdes_by_instance_id[component.instance_id] = component.reference_designator
            refdes = component.reference_designator or ""
            match = re.match(r"^([A-Z]+)(\d+)$", refdes)
            if match:
                prefix, number = match.groups()
                self.counters[prefix] = max(self.counters.get(prefix, 0), int(number))

    def reference_designator(self, instance_id: str, component_class: CircuitComponentRole) -> str:
        existing = self.existing_refdes_by_instance_id.get(instance_id)
        if existing is not None:
            return existing
        return self.next(component_class)

    def next(self, component_class: CircuitComponentRole) -> str:
        prefix = _REFDES_PREFIX.get(component_class, "U")
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}{self.counters[prefix]}"


def reference_designators_by_instance(
    draft: CircuitIRDraft,
    component_id_by_draft: dict[str, str],
    existing,
) -> dict[str, str]:
    classes_by_instance = {
        component_id_by_draft[component.draft_id]: component.component_class
        for component in draft.component_instances
    }
    allocator = ReferenceDesignatorAllocator(existing)
    return {
        instance_id: allocator.reference_designator(instance_id, classes_by_instance[instance_id])
        for instance_id in sorted(classes_by_instance)
    }


def allocators_from_existing(existing, field_name: str) -> dict[str, SequentialAllocator]:
    result = {}
    if existing is None:
        return result
    collections = [existing.components] if field_name == "instance_id" else [existing.nets]
    for items in collections:
        for item in items:
            item_id = getattr(item, field_name)
            prefix = item_id.rsplit("_", 1)[0]
            result[prefix] = SequentialAllocator(prefix, [item_id])
    return result


def non_resolved_status(status: ComponentResolutionStatus) -> ComponentResolutionStatus:
    if status == ComponentResolutionStatus.RESOLVED:
        return ComponentResolutionStatus.PARTIALLY_RESOLVED
    return status


def resolved_value_and_parameters(
    component: DraftComponentInstance,
    selected_record_id: str | None,
    context: CircuitPlanningContext,
    metadata: CircuitIRMetadata,
):
    if selected_record_id is None:
        return None, []
    record = component_record_by_id(selected_record_id, context)
    if record is None:
        return None, []
    value = value_from_verified_attribute(component, record)
    return value, []


def component_record_by_id(component_record_id: str, context: CircuitPlanningContext) -> ComponentRecord | None:
    for record in context.knowledge_context.component_records:
        if record.component_id == component_record_id:
            return record
    return None


def value_from_verified_attribute(component: DraftComponentInstance, record: ComponentRecord):
    for attribute in sorted(record.attributes, key=lambda item: item.attribute_id):
        if attribute.status != KnowledgeState.VERIFIED or attribute.value is None or not attribute.evidence_ids:
            continue
        if attribute.name not in recognized_value_attribute_names(component):
            continue
        quantity_value = getattr(attribute.value, "value", None)
        if quantity_value is None:
            continue
        if getattr(attribute.value, "kind", None) not in {"exact", "nominal"}:
            continue
        return QuantityCircuitValue(quantity=quantity_value)
    return None


def recognized_value_attribute_names(component: DraftComponentInstance) -> set[str]:
    by_class = {
        CircuitComponentRole.CAPACITOR: {
            "capacitance",
            "recommended_capacitance",
            "recommended_input_capacitance",
            "recommended_output_capacitance",
        },
        CircuitComponentRole.INDUCTOR: {"inductance", "recommended_inductance"},
        CircuitComponentRole.RESISTOR: {"resistance", "recommended_resistance"},
    }
    return by_class.get(component.component_class, set())


def draft_component_sort_key(component: DraftComponentInstance) -> tuple[str, ...]:
    return (*draft_component_semantic_key(component), component.draft_id)


def draft_component_semantic_key(component: DraftComponentInstance) -> tuple[str, ...]:
    return (
        component.component_class.value,
        component.role,
        ",".join(sorted(ref for ref in component.source_design_plan_refs if ref.startswith("BLOCK_"))),
        ",".join(sorted(component.source_requirement_refs)),
        ",".join(sorted(pin.function for pin in component.pin_drafts)),
    )


def component_semantic_key(component: ComponentInstance) -> tuple[str, ...]:
    return (
        component.component_class.value,
        component.role or "",
        ",".join(sorted(component.source_block_ids)),
        ",".join(sorted(component.source_requirement_ids)),
        ",".join(sorted(pin.function or "" for pin in component.pins)),
    )


def draft_net_sort_key(net) -> tuple[str, ...]:
    return (*net_semantic_key(canonical_net_name(net.name_hint, net.role), net.role, net.power_domain_ref), net.draft_net_id)


def net_semantic_key(name: str | None, role: NetRole, power_domain_id: str | None) -> tuple[str, ...]:
    return (role.value, name or "", power_domain_id or "")


def mapping_semantic_key(
    design_plan_object_ids: list[str],
    mapping_type: ImplementationMappingType,
    circuit_object_ids: list[str] | None = None,
) -> tuple[str, ...]:
    return (
        mapping_type.value,
        ",".join(sorted(design_plan_object_ids)),
        ",".join(sorted(circuit_object_ids or [])),
    )


def assumption_semantic_key(
    topic: CircuitAssumptionTopic | str,
    source: str,
    target_object_ids: list[str],
) -> tuple[str, ...]:
    topic_value = getattr(topic, "value", str(topic))
    return ("assumption", topic_value, source, ",".join(sorted(target_object_ids)))


def assumption_id_from_semantic_key(key: tuple[str, ...]) -> str:
    topic = key[1].upper()
    digest = sha1("|".join(key).encode("utf-8")).hexdigest()[:10].upper()
    return f"CIASM_{topic}_{digest}"


def assumption_topic_from_id(assumption_id: str) -> CircuitAssumptionTopic | None:
    prefix = "CIASM_"
    if not assumption_id.startswith(prefix):
        return None
    remainder = assumption_id[len(prefix) :]
    for topic in sorted(CircuitAssumptionTopic, key=lambda item: len(item.value), reverse=True):
        token = f"{topic.value.upper()}_"
        if remainder.startswith(token):
            return topic
    return None


def open_decision_semantic_key(topic: str, target_object_ids: list[str], driven_by_design_plan_ids: list[str]) -> tuple[str, ...]:
    return ("open_decision", topic, ",".join(sorted(target_object_ids)), ",".join(sorted(driven_by_design_plan_ids)))


def group_semantic_key(source_block_ids: list[str]) -> tuple[str, ...]:
    return ("generated_group", ",".join(sorted(source_block_ids)))


def component_implementation_status(
    resolution_status: ComponentResolutionStatus,
    pins: list[PinInstance],
) -> ImplementationStatus:
    if resolution_status != ComponentResolutionStatus.RESOLVED:
        return ImplementationStatus.UNRESOLVED if resolution_status == ComponentResolutionStatus.UNRESOLVED else ImplementationStatus.PARTIAL
    if any(pin.resolution_status != PinResolutionStatus.RESOLVED or pin.connection_state == PinConnectionState.UNRESOLVED for pin in pins):
        return ImplementationStatus.PARTIAL
    return ImplementationStatus.RESOLVED


def circuit_implementation_status(
    components: list[ComponentInstance],
    mappings: list[ImplementationMapping],
    open_decisions: list[OpenImplementationDecision],
) -> ImplementationStatus:
    if not components:
        return ImplementationStatus.UNRESOLVED
    if any(component.implementation_status != ImplementationStatus.RESOLVED for component in components):
        return ImplementationStatus.PARTIAL
    if any(mapping.status != ImplementationStatus.RESOLVED for mapping in mappings):
        return ImplementationStatus.PARTIAL
    if any(decision.blocking and decision.status == "open" for decision in open_decisions):
        return ImplementationStatus.PARTIAL
    return ImplementationStatus.RESOLVED


def resolve_draft_ref(
    ref: str,
    component_ids: dict[str, str],
    net_ids: dict[str, str],
    pin_ids: dict[tuple[str, str], str],
) -> str:
    if ref in component_ids:
        return component_ids[ref]
    if ref in net_ids:
        return net_ids[ref]
    for (_, draft_pin_id), pin_id in pin_ids.items():
        if ref == draft_pin_id:
            return pin_id
    return ref


def generated_mappings(
    draft: CircuitIRDraft,
    component_ids: dict[str, str],
    net_ids: dict[str, str],
    existing,
) -> list[ImplementationMapping]:
    by_design_ref: dict[str, list[str]] = {}
    for component in draft.component_instances:
        for design_ref in component.source_design_plan_refs:
            if design_ref.startswith("BLOCK_"):
                by_design_ref.setdefault(design_ref, []).append(component_ids[component.draft_id])
    for net in draft.nets:
        if net.power_domain_ref:
            by_design_ref.setdefault(net.power_domain_ref, []).append(net_ids[net.draft_net_id])
    existing_by_key = {}
    if existing is not None:
        for mapping in existing.implementation_mappings:
            key = mapping_semantic_key(mapping.design_plan_object_ids, mapping.mapping_type, mapping.circuit_object_ids)
            existing_by_key.setdefault(key, mapping.mapping_id)
    allocator = SequentialAllocator("CIMAP", [mapping.mapping_id for mapping in existing.implementation_mappings] if existing else ())
    mappings = []
    for design_ref, circuit_refs in sorted(by_design_ref.items()):
        if not circuit_refs:
            continue
        circuit_object_ids = sorted(set(circuit_refs))
        key = mapping_semantic_key([design_ref], ImplementationMappingType.IMPLEMENTS, circuit_object_ids)
        mappings.append(
            ImplementationMapping(
                mapping_id=existing_by_key.get(key) or allocator.next(),
                design_plan_object_ids=[design_ref],
                circuit_object_ids=circuit_object_ids,
                mapping_type=ImplementationMappingType.IMPLEMENTS,
                status=ImplementationStatus.PARTIAL,
                rationale="Generated from draft source DesignPlan references.",
            )
        )
    return mappings


def generated_interface_bindings(
    context: CircuitPlanningContext,
    nets: list[Net],
    components: list[ComponentInstance],
    metadata: CircuitIRMetadata,
    existing,
) -> list[CircuitInterfaceBinding]:
    existing_by_interface = {}
    if existing is not None:
        existing_by_interface = {
            binding.design_plan_interface_id: binding.binding_id
            for binding in sorted(existing.interface_bindings, key=lambda item: item.binding_id)
        }
    allocator = SequentialAllocator("IFB", [binding.binding_id for binding in existing.interface_bindings] if existing else ())
    bindings: list[CircuitInterfaceBinding] = []
    for interface in sorted(context.design_plan.interfaces, key=lambda item: item.interface_id):
        if interface.type != InterfaceType.I2C:
            continue
        signal_nets = sorted(net.net_id for net in nets if (net.name or "").upper() in {"SDA", "SCL"})
        if not signal_nets:
            continue
        component_ids = sorted(
            component.instance_id
            for component in components
            if set(component.source_block_ids) & set(interface.participants)
        )
        bindings.append(
            CircuitInterfaceBinding(
                binding_id=existing_by_interface.get(interface.interface_id) or allocator.next(),
                design_plan_interface_id=interface.interface_id,
                net_ids=signal_nets,
                component_ids=component_ids,
                description="Generated binding for planned I2C electrical nets.",
                metadata=metadata,
            )
        )
    return bindings


def knowledge_references_for_component(component_record_id: str | None, context: CircuitPlanningContext) -> list[KnowledgeReference]:
    if component_record_id is None:
        return []
    for component in context.knowledge_context.component_records:
        if component.component_id == component_record_id:
            evidence_ids = sorted({
                evidence_id
                for attribute in component.attributes
                for evidence_id in attribute.evidence_ids
            } | {
                evidence_id
                for claim in [*component.qualification_claims, *component.compliance_claims]
                for evidence_id in claim.evidence_ids
            })
            return [
                KnowledgeReference(
                    component_record_id=component_record_id,
                    source_ids=component.source_ids,
                    evidence_ids=evidence_ids,
                    purpose="candidate selection provenance",
                )
            ]
    return []


def knowledge_references_for_selected(component_record_ids, context: CircuitPlanningContext) -> list[KnowledgeReference]:
    refs = []
    seen = set()
    for component_record_id in component_record_ids:
        if component_record_id in seen:
            continue
        seen.add(component_record_id)
        refs.extend(knowledge_references_for_component(component_record_id, context))
    return refs


def requirement_ids(context: CircuitPlanningContext) -> set[str]:
    return {requirement.id for requirement in [*context.requirement_model.requirements, *context.requirement_model.derived_requirements]}


def canonical_net_name(name_hint: str | None, role: NetRole) -> str | None:
    if name_hint is None:
        return None
    candidate = name_hint.strip().upper()
    if candidate in {"VIN", "VOUT", "GND", "AGND", "DGND", "SDA", "SCL", "SW", "5V", "12V"}:
        return candidate
    return enum_value(role).upper()


def net_role_prefix(role: NetRole) -> str:
    return {
        NetRole.POWER: "PWR",
        NetRole.GROUND: "GND",
        NetRole.SIGNAL: "SIG",
        NetRole.CLOCK: "CLK",
        NetRole.ANALOG: "ANA",
        NetRole.DIGITAL: "DIG",
        NetRole.COMMUNICATION: "COMM",
        NetRole.UNKNOWN: "UNK",
    }[role]


def enum_value(value) -> str:
    return getattr(value, "value", str(value))
