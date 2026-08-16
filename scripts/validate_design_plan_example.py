from __future__ import annotations

from pathlib import Path

from schematic_ai.domain.design_plan import DesignPlan, validate_design_plan_against_requirements
from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PLAN_PATH = ROOT / "examples" / "design_plan_v0_1.json"
REQUIREMENT_MODEL_PATH = ROOT / "examples" / "requirement_model_v0_1.json"


def main() -> None:
    design_plan = DesignPlan.model_validate_json(DESIGN_PLAN_PATH.read_text(encoding="utf-8"))
    requirement_model = RequirementModel.model_validate_json(
        REQUIREMENT_MODEL_PATH.read_text(encoding="utf-8")
    )
    validate_design_plan_against_requirements(design_plan, requirement_model)
    print(f"Validated {design_plan.design_plan_id} revision {design_plan.revision}")


if __name__ == "__main__":
    main()

