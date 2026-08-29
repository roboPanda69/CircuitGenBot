from __future__ import annotations

import json
from pathlib import Path

from schematic_ai.domain.knowledge import (
    ComponentRecord,
    ComplianceProfile,
    EngineeringRule,
    KnowledgeContext,
    KnowledgeImportRequest,
    KnowledgeImportResult,
    ManualKnowledgeEntry,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


SCHEMAS = {
    "component_record_v0_1.schema.json": ComponentRecord,
    "engineering_rule_v0_1.schema.json": EngineeringRule,
    "knowledge_context_v0_1.schema.json": KnowledgeContext,
    "compliance_profile_v0_1.schema.json": ComplianceProfile,
    "knowledge_import_request_v0_1.schema.json": KnowledgeImportRequest,
    "knowledge_import_result_v0_1.schema.json": KnowledgeImportResult,
    "manual_knowledge_entry_v0_1.schema.json": ManualKnowledgeEntry,
}


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = SCHEMA_DIR / filename
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
