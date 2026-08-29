from __future__ import annotations

import json
from pathlib import Path

from schematic_ai.domain.circuit_ir import CircuitIR, ComponentInstance, Net


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


SCHEMAS = {
    "circuit_ir_v0_1.schema.json": CircuitIR,
    "component_instance_v0_1.schema.json": ComponentInstance,
    "net_v0_1.schema.json": Net,
}


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = SCHEMA_DIR / filename
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
