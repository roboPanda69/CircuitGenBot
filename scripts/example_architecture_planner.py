from __future__ import annotations

import json
from pathlib import Path

from schematic_ai.application.architecture import ArchitecturePlanner
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[1]


class FakeArchitectureLLM:
    def generate_structured(self, *, prompt: str, json_schema: dict | None = None) -> str:
        return json.dumps(
            {
                "blocks": [
                    {
                        "draft_id": "input_stage",
                        "type": "power_input",
                        "name": "Input Power Interface",
                        "purpose": "Accept nominal input power.",
                        "ports": [
                            {"draft_id": "raw_out", "name": "raw_input_power", "kind": "power", "direction": "output", "power_domain_ref": "vin_raw"}
                        ],
                    },
                    {
                        "draft_id": "power_stage",
                        "type": "power_conversion",
                        "name": "Main Power Conversion",
                        "purpose": "Convert input power to regulated output power.",
                        "topology_class": "switching_step_down",
                        "ports": [
                            {"draft_id": "power_in", "name": "input_power", "kind": "power", "direction": "input", "power_domain_ref": "vin_raw"},
                            {"draft_id": "power_out", "name": "regulated_output", "kind": "power", "direction": "output", "power_domain_ref": "rail_5v"},
                        ],
                    },
                ],
                "connections": [
                    {
                        "draft_id": "input_to_power",
                        "source_block": "input_stage",
                        "source_port": "raw_out",
                        "target_block": "power_stage",
                        "target_port": "power_in",
                        "kind": "power",
                        "description": "Input power feeds the conversion stage.",
                    }
                ],
                "power_domains": [
                    {"draft_id": "vin_raw", "name": "Raw Input Power", "role": "input", "voltage": {"kind": "nominal", "value": 12, "unit": "V"}, "source_block": "input_stage", "consumer_blocks": ["power_stage"]},
                    {"draft_id": "rail_5v", "name": "5 V Main Rail", "role": "regulated_output", "voltage": {"kind": "nominal", "value": 5, "unit": "V"}, "source_block": "power_stage", "consumer_blocks": []},
                ],
                "interfaces": [],
                "requirement_mappings": [
                    {"requirement_id": "REQ_PWR_001", "targets": [{"type": "functional_block", "draft_id": "input_stage"}], "status": "mapped"},
                    {"requirement_id": "REQ_PWR_002", "targets": [{"type": "functional_block", "draft_id": "power_stage"}, {"type": "power_domain", "draft_id": "rail_5v"}], "status": "mapped"},
                    {"requirement_id": "REQ_PWR_003", "targets": [{"type": "functional_block", "draft_id": "power_stage"}], "status": "mapped"},
                    {"requirement_id": "REQ_PROT_001", "targets": [], "status": "unresolved"},
                    {"requirement_id": "REQ_IF_001", "targets": [], "status": "unresolved"},
                    {"requirement_id": "DREQ_IF_001", "targets": [], "status": "unresolved"},
                ],
                "architecture_decisions": [
                    {
                        "draft_id": "main_topology",
                        "type": "topology_choice",
                        "target": {"type": "functional_block", "draft_id": "power_stage"},
                        "choice": "switching_step_down",
                        "rationale": "The requested output voltage is below the nominal input supply.",
                        "driven_by_requirements": ["REQ_PWR_001", "REQ_PWR_002", "REQ_PWR_003"],
                        "status": "accepted",
                    }
                ],
                "assumptions": [],
                "open_decisions": [],
            }
        )


def main() -> None:
    data = json.loads((ROOT / "examples" / "requirement_model_v0_1.json").read_text(encoding="utf-8"))
    data["open_questions"] = []
    requirement_model = RequirementModel.model_validate(data)
    result = ArchitecturePlanner(FakeArchitectureLLM()).plan_architecture(requirement_model)
    print(result.status)
    if result.design_plan is not None:
        print(result.design_plan.model_dump_json(indent=2))
    else:
        print(json.dumps([issue.__dict__ for issue in result.requirement_issues], indent=2, default=str))


if __name__ == "__main__":
    main()
