from __future__ import annotations

import json
from datetime import datetime, timezone

from schematic_ai.application.requirements import MessageEnvelope, RequirementInterpreter
from schematic_ai.llm import OllamaClient


def main() -> None:
    interpreter = RequirementInterpreter(llm_client=OllamaClient())
    result = interpreter.interpret_new(
        MessageEnvelope(
            message_id="MSG_MANUAL_001",
            project_id="PRJ_MANUAL_001",
            text="Make a 12V to 5V 2A power supply.",
        ),
        created_at=datetime.now(timezone.utc),
    )
    if result.model is not None:
        print(result.model.model_dump_json(indent=2))
    else:
        print(json.dumps([question.model_dump(mode="json") for question in result.open_questions], indent=2))


if __name__ == "__main__":
    main()
