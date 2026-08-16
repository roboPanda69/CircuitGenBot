"""Controlled vocabularies for DesignPlan v0.1."""

from __future__ import annotations

from enum import StrEnum


class FunctionalBlockType(StrEnum):
    POWER_INPUT = "power_input"
    POWER_PROTECTION = "power_protection"
    POWER_CONVERSION = "power_conversion"
    POWER_DISTRIBUTION = "power_distribution"
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    SIGNAL_CONDITIONING = "signal_conditioning"
    ANALOG_PROCESSING = "analog_processing"
    DIGITAL_LOGIC = "digital_logic"
    COMMUNICATION = "communication"
    INTERFACE_BRIDGE = "interface_bridge"
    CONNECTOR = "connector"
    USER_INTERFACE = "user_interface"
    STORAGE = "storage"
    TIMING = "timing"
    ISOLATION = "isolation"
    OTHER = "other"


class FunctionalBlockStatus(StrEnum):
    PLANNED = "planned"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class FunctionalTopologyClass(StrEnum):
    SWITCHING_STEP_DOWN = "switching_step_down"
    SWITCHING_STEP_UP = "switching_step_up"
    SWITCHING_INVERTING = "switching_inverting"
    LINEAR_REGULATION = "linear_regulation"
    ISOLATED_POWER_CONVERSION = "isolated_power_conversion"
    NON_ISOLATED_POWER_CONVERSION = "non_isolated_power_conversion"
    DIRECT_INTERFACE = "direct_interface"
    INTERFACE_BRIDGE = "interface_bridge"
    ANALOG_FILTER = "analog_filter"
    AMPLIFIER = "amplifier"
    SIGNAL_CONDITIONING = "signal_conditioning"
    LEVEL_TRANSLATION = "level_translation"
    GALVANIC_ISOLATION = "galvanic_isolation"
    SENSOR_FRONTEND = "sensor_frontend"
    ACTUATOR_DRIVER = "actuator_driver"
    CUSTOM_ARCHITECTURE = "custom_architecture"


class FunctionalPortKind(StrEnum):
    POWER = "power"
    ANALOG_SIGNAL = "analog_signal"
    DIGITAL_SIGNAL = "digital_signal"
    COMMUNICATION = "communication"
    CONTROL = "control"
    FEEDBACK = "feedback"
    CLOCK = "clock"
    OTHER = "other"


class PortDirection(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class ConnectionKind(StrEnum):
    POWER = "power"
    ANALOG_SIGNAL = "analog_signal"
    DIGITAL_SIGNAL = "digital_signal"
    COMMUNICATION = "communication"
    CONTROL = "control"
    FEEDBACK = "feedback"
    CLOCK = "clock"
    OTHER = "other"


class PowerDomainRole(StrEnum):
    INPUT = "input"
    PROTECTED_INPUT = "protected_input"
    REGULATED_OUTPUT = "regulated_output"
    UNREGULATED = "unregulated"
    LOGIC_SUPPLY = "logic_supply"
    ANALOG_SUPPLY = "analog_supply"
    REFERENCE = "reference"
    ISOLATED_SUPPLY = "isolated_supply"
    OTHER = "other"


class InterfaceType(StrEnum):
    I2C = "i2c"
    SPI = "spi"
    UART = "uart"
    CAN = "can"
    USB = "usb"
    GPIO = "gpio"
    PWM = "pwm"
    ANALOG = "analog"
    POWER = "power"
    CLOCK = "clock"
    CUSTOM = "custom"


class InterfaceDirection(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class RequirementMappingStatus(StrEnum):
    MAPPED = "mapped"
    PARTIALLY_MAPPED = "partially_mapped"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class MappingTargetType(StrEnum):
    FUNCTIONAL_BLOCK = "functional_block"
    POWER_DOMAIN = "power_domain"
    INTERFACE = "interface"
    BLOCK_CONNECTION = "block_connection"
    ARCHITECTURE_DECISION = "architecture_decision"


class ArchitectureDecisionType(StrEnum):
    TOPOLOGY_CHOICE = "topology_choice"
    PARTITIONING = "partitioning"
    INTERFACE_STRATEGY = "interface_strategy"
    POWER_STRATEGY = "power_strategy"
    ISOLATION_STRATEGY = "isolation_strategy"
    SIGNAL_PATH_STRATEGY = "signal_path_strategy"
    OTHER = "other"


class ArchitectureChoice(StrEnum):
    SWITCHING_STEP_DOWN = "switching_step_down"
    SWITCHING_STEP_UP = "switching_step_up"
    SWITCHING_INVERTING = "switching_inverting"
    LINEAR_REGULATION = "linear_regulation"
    ISOLATED_POWER_CONVERSION = "isolated_power_conversion"
    NON_ISOLATED_POWER_CONVERSION = "non_isolated_power_conversion"
    DIRECT_INTERFACE = "direct_interface"
    INTERFACE_BRIDGE = "interface_bridge"
    ANALOG_FILTER = "analog_filter"
    AMPLIFIER = "amplifier"
    SIGNAL_CONDITIONING = "signal_conditioning"
    LEVEL_TRANSLATION = "level_translation"
    GALVANIC_ISOLATION = "galvanic_isolation"
    SENSOR_FRONTEND = "sensor_frontend"
    ACTUATOR_DRIVER = "actuator_driver"
    PROTOCOL_TRANSLATION = "protocol_translation"
    SINGLE_RAIL = "single_rail"
    MULTIPLE_RAILS = "multiple_rails"
    CENTRALIZED_REGULATION = "centralized_regulation"
    DISTRIBUTED_REGULATION = "distributed_regulation"
    ISOLATED_DOMAINS = "isolated_domains"
    SHARED_GROUND_DOMAINS = "shared_ground_domains"
    GALVANICALLY_ISOLATED = "galvanically_isolated"
    NON_ISOLATED = "non_isolated"
    PARTIAL_ISOLATION = "partial_isolation"
    DIRECT_SIGNAL_PATH = "direct_signal_path"
    FILTERED_SIGNAL_PATH = "filtered_signal_path"
    AMPLIFIED_SIGNAL_PATH = "amplified_signal_path"
    CONDITIONED_SIGNAL_PATH = "conditioned_signal_path"
    DIFFERENTIAL_SIGNAL_PATH = "differential_signal_path"
    SINGLE_ENDED_SIGNAL_PATH = "single_ended_signal_path"
    SINGLE_BOARD_PARTITION = "single_board_partition"
    MODULAR_PARTITION = "modular_partition"
    SEPARATE_POWER_AND_CONTROL = "separate_power_and_control"
    INTEGRATED_ARCHITECTURE = "integrated_architecture"
    CUSTOM_ARCHITECTURE = "custom_architecture"


class ArchitectureDecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class OpenDecisionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
