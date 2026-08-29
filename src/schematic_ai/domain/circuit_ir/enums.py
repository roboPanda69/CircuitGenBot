"""Controlled vocabularies for CircuitIR v0.1."""

from __future__ import annotations

from enum import StrEnum


class ComponentResolutionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"


class ImplementationStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PARTIAL = "partial"
    RESOLVED = "resolved"


class CircuitComponentRole(StrEnum):
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    DIODE = "diode"
    MOSFET = "mosfet"
    TRANSISTOR = "transistor"
    REGULATOR = "regulator"
    CONVERTER = "converter"
    SENSOR = "sensor"
    MICROCONTROLLER = "microcontroller"
    LOGIC = "logic"
    CONNECTOR = "connector"
    RELAY = "relay"
    OP_AMP = "op_amp"
    ISOLATOR = "isolator"
    PROTECTION_DEVICE = "protection_device"
    INTERFACE_IC = "interface_ic"
    OTHER = "other"


class PinElectricalType(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    PASSIVE = "passive"
    POWER_INPUT = "power_input"
    POWER_OUTPUT = "power_output"
    OPEN_DRAIN = "open_drain"
    OPEN_COLLECTOR = "open_collector"
    NO_CONNECT = "no_connect"
    UNSPECIFIED = "unspecified"


class PinResolutionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"


class PinConnectionState(StrEnum):
    CONNECTED = "connected"
    UNRESOLVED = "unresolved"
    NO_CONNECT = "no_connect"


class NetRole(StrEnum):
    POWER = "power"
    GROUND = "ground"
    SIGNAL = "signal"
    CLOCK = "clock"
    ANALOG = "analog"
    DIGITAL = "digital"
    COMMUNICATION = "communication"
    UNKNOWN = "unknown"


class ImplementationMappingType(StrEnum):
    IMPLEMENTS = "implements"
    SUPPORTS = "supports"
    PROTECTS = "protects"
    INTERFACES = "interfaces"
    BIASES = "biases"
    FILTERS = "filters"
    OTHER = "other"


class CircuitAssumptionStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class OpenImplementationDecisionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
