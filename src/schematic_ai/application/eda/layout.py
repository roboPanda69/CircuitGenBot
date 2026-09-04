"""Deterministic schematic layout hints for Milestone 8 backends."""

from __future__ import annotations

from dataclasses import dataclass

from schematic_ai.domain.circuit_ir import CircuitIR, ComponentInstance, Net, NetRole


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class ComponentPlacement:
    instance_id: str
    at: Point
    group_id: str | None = None


@dataclass(frozen=True)
class NetLabelPlacement:
    net_id: str
    at: Point


@dataclass(frozen=True)
class SchematicLayout:
    component_placements: dict[str, ComponentPlacement]
    net_label_placements: dict[str, NetLabelPlacement]


class SchematicLayoutStrategy:
    """Simple left-to-right layout using CircuitIR grouping as presentation hints."""

    def layout(self, circuit_ir: CircuitIR) -> SchematicLayout:
        group_by_component = {
            component_id: group.group_id
            for group in circuit_ir.groups
            for component_id in group.component_ids
        }
        placements: dict[str, ComponentPlacement] = {}
        ordered = sorted(enumerate(circuit_ir.components), key=lambda item: self._component_sort_key(item[1], item[0], group_by_component))
        for visual_index, (_, component) in enumerate(ordered):
            column = visual_index % 4
            row = visual_index // 4
            placements[component.instance_id] = ComponentPlacement(
                instance_id=component.instance_id,
                at=Point(x=35.0 + column * 45.0, y=35.0 + row * 35.0),
                group_id=group_by_component.get(component.instance_id),
            )

        net_labels: dict[str, NetLabelPlacement] = {}
        for index, net in enumerate(sorted(circuit_ir.nets, key=self._net_sort_key)):
            net_labels[net.net_id] = NetLabelPlacement(net_id=net.net_id, at=Point(x=20.0, y=120.0 + index * 7.5))

        return SchematicLayout(component_placements=placements, net_label_placements=net_labels)

    def _component_sort_key(
        self,
        component: ComponentInstance,
        original_index: int,
        group_by_component: dict[str, str],
    ) -> tuple[int, str, str, int]:
        role_rank = {
            "input": 0,
            "connector": 1,
            "protection": 2,
            "regulator": 3,
            "converter": 3,
            "capacitor": 4,
            "output": 5,
        }
        haystack = f"{component.component_class} {component.role or ''} {component.reference_designator or ''}".lower()
        rank = 6
        for token, token_rank in role_rank.items():
            if token in haystack:
                rank = min(rank, token_rank)
        return (rank, group_by_component.get(component.instance_id, ""), component.instance_id, original_index)

    def _net_sort_key(self, net: Net) -> tuple[int, str]:
        role_rank = {
            NetRole.POWER: 0,
            NetRole.GROUND: 1,
            NetRole.SIGNAL: 2,
            NetRole.CLOCK: 3,
            NetRole.ANALOG: 4,
            NetRole.DIGITAL: 5,
            NetRole.COMMUNICATION: 6,
            NetRole.UNKNOWN: 7,
        }
        return (role_rank.get(net.role, 7), net.net_id)
