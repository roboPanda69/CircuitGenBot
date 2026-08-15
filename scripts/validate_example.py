from __future__ import annotations

from pathlib import Path

from schematic_ai.domain.requirements.models import RequirementModel


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = ROOT / "examples" / "requirement_model_v0_1.json"


def main() -> None:
    model = RequirementModel.model_validate_json(EXAMPLE_PATH.read_text(encoding="utf-8"))
    print(f"Validated {model.requirement_set_id} revision {model.revision}")


if __name__ == "__main__":
    main()

