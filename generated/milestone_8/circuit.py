"""Generated Python circuit representation.

CircuitIR remains the canonical electrical state. This file is a
derived one-way artifact and external edits do not update CircuitIR.
"""

import json

CIRCUITIR_PYTHON_REPRESENTATION = json.loads(
    r'''
{
  "canonical_source": "CircuitIR",
  "components": [
    {
      "instance_id": "J_IN_001",
      "pins": [
        {
          "component_instance_id": "J_IN_001",
          "connection_state": "connected",
          "electrical_type": "power_output",
          "function": "raw input power",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_J_IN_VIN",
          "pin_name": "VIN",
          "pin_number": "1",
          "resolution_status": "partially_resolved"
        },
        {
          "component_instance_id": "J_IN_001",
          "connection_state": "connected",
          "electrical_type": "power_output",
          "function": "input return",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_J_IN_GND",
          "pin_name": "GND",
          "pin_number": "2",
          "resolution_status": "partially_resolved"
        }
      ],
      "placeholder": true,
      "ref": "J1",
      "symbol": null,
      "value": null
    },
    {
      "instance_id": "D_PROT_001",
      "pins": [
        {
          "component_instance_id": "D_PROT_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "raw input",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_D_PROT_IN",
          "pin_name": "IN",
          "pin_number": null,
          "resolution_status": "unresolved"
        },
        {
          "component_instance_id": "D_PROT_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "protected output",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_D_PROT_OUT",
          "pin_name": "OUT",
          "pin_number": null,
          "resolution_status": "unresolved"
        }
      ],
      "placeholder": true,
      "ref": "D1",
      "symbol": null,
      "value": null
    },
    {
      "instance_id": "U_REG_001",
      "pins": [
        {
          "component_instance_id": "U_REG_001",
          "connection_state": "connected",
          "electrical_type": "power_input",
          "function": "converter input",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_U_REG_VIN",
          "pin_name": "VIN",
          "pin_number": "1",
          "resolution_status": "resolved"
        },
        {
          "component_instance_id": "U_REG_001",
          "connection_state": "unresolved",
          "electrical_type": "power_output",
          "function": "switch node",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_U_REG_SW",
          "pin_name": "SW",
          "pin_number": "2",
          "resolution_status": "partially_resolved"
        },
        {
          "component_instance_id": "U_REG_001",
          "connection_state": "connected",
          "electrical_type": "power_output",
          "function": "regulated output",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_U_REG_VOUT",
          "pin_name": "VOUT",
          "pin_number": "3",
          "resolution_status": "resolved"
        },
        {
          "component_instance_id": "U_REG_001",
          "connection_state": "connected",
          "electrical_type": "power_input",
          "function": "power return",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_U_REG_GND",
          "pin_name": "GND",
          "pin_number": "4",
          "resolution_status": "resolved"
        },
        {
          "component_instance_id": "U_REG_001",
          "connection_state": "no_connect",
          "electrical_type": "unspecified",
          "function": "enable pin pending policy",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_U_REG_EN",
          "pin_name": "EN",
          "pin_number": "5",
          "resolution_status": "partially_resolved"
        }
      ],
      "placeholder": true,
      "ref": "U1",
      "symbol": null,
      "value": null
    },
    {
      "instance_id": "C_IN_001",
      "pins": [
        {
          "component_instance_id": "C_IN_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "positive terminal",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_C_IN_POS",
          "pin_name": "POS",
          "pin_number": "1",
          "resolution_status": "resolved"
        },
        {
          "component_instance_id": "C_IN_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "return terminal",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_C_IN_NEG",
          "pin_name": "NEG",
          "pin_number": "2",
          "resolution_status": "resolved"
        }
      ],
      "placeholder": false,
      "ref": "C1",
      "symbol": "Device:C",
      "value": {
        "kind": "quantity",
        "quantity": {
          "unit": "uF",
          "value": 22.0
        }
      }
    },
    {
      "instance_id": "C_OUT_001",
      "pins": [
        {
          "component_instance_id": "C_OUT_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "positive terminal",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_C_OUT_POS",
          "pin_name": "POS",
          "pin_number": "1",
          "resolution_status": "partially_resolved"
        },
        {
          "component_instance_id": "C_OUT_001",
          "connection_state": "connected",
          "electrical_type": "passive",
          "function": "return terminal",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_C_OUT_NEG",
          "pin_name": "NEG",
          "pin_number": "2",
          "resolution_status": "partially_resolved"
        }
      ],
      "placeholder": true,
      "ref": "C2",
      "symbol": null,
      "value": {
        "kind": "quantity",
        "quantity": {
          "unit": "uF",
          "value": 47.0
        }
      }
    },
    {
      "instance_id": "J_OUT_001",
      "pins": [
        {
          "component_instance_id": "J_OUT_001",
          "connection_state": "connected",
          "electrical_type": "power_input",
          "function": "regulated 5 V output",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_J_OUT_5V",
          "pin_name": "5V",
          "pin_number": "1",
          "resolution_status": "partially_resolved"
        },
        {
          "component_instance_id": "J_OUT_001",
          "connection_state": "connected",
          "electrical_type": "power_input",
          "function": "regulated rail return",
          "metadata": {
            "created_at": "2026-08-29T00:00:00+05:30",
            "created_by": "circuit_ir_fixture",
            "updated_at": "2026-08-29T00:00:00+05:30"
          },
          "pin_id": "PIN_J_OUT_GND",
          "pin_name": "GND",
          "pin_number": "2",
          "resolution_status": "partially_resolved"
        }
      ],
      "placeholder": true,
      "ref": "J2",
      "symbol": null,
      "value": null
    }
  ],
  "nets": [
    {
      "connections": [
        {
          "component_instance_id": "J_IN_001",
          "pin_id": "PIN_J_IN_VIN"
        },
        {
          "component_instance_id": "D_PROT_001",
          "pin_id": "PIN_D_PROT_IN"
        }
      ],
      "name": "VIN_RAW",
      "net_id": "NET_VIN_RAW"
    },
    {
      "connections": [
        {
          "component_instance_id": "D_PROT_001",
          "pin_id": "PIN_D_PROT_OUT"
        },
        {
          "component_instance_id": "U_REG_001",
          "pin_id": "PIN_U_REG_VIN"
        },
        {
          "component_instance_id": "C_IN_001",
          "pin_id": "PIN_C_IN_POS"
        }
      ],
      "name": "VIN_PROTECTED",
      "net_id": "NET_VIN_PROTECTED"
    },
    {
      "connections": [
        {
          "component_instance_id": "U_REG_001",
          "pin_id": "PIN_U_REG_VOUT"
        },
        {
          "component_instance_id": "C_OUT_001",
          "pin_id": "PIN_C_OUT_POS"
        },
        {
          "component_instance_id": "J_OUT_001",
          "pin_id": "PIN_J_OUT_5V"
        }
      ],
      "name": "5V",
      "net_id": "NET_5V"
    },
    {
      "connections": [
        {
          "component_instance_id": "J_IN_001",
          "pin_id": "PIN_J_IN_GND"
        },
        {
          "component_instance_id": "U_REG_001",
          "pin_id": "PIN_U_REG_GND"
        },
        {
          "component_instance_id": "C_IN_001",
          "pin_id": "PIN_C_IN_NEG"
        },
        {
          "component_instance_id": "C_OUT_001",
          "pin_id": "PIN_C_OUT_NEG"
        },
        {
          "component_instance_id": "J_OUT_001",
          "pin_id": "PIN_J_OUT_GND"
        }
      ],
      "name": "GND",
      "net_id": "NET_GND"
    },
    {
      "connections": [],
      "name": "AGND",
      "net_id": "NET_AGND"
    }
  ],
  "round_trip": false,
  "source_circuit_id": "CIR_0001",
  "source_circuit_revision": 1
}
'''
)
