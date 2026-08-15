import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from schematic_ai.domain.requirements.models import Origin, Requirement, Target
from schematic_ai.domain.requirements.models import Relationship
from schematic_ai.domain.requirements.updates import (
    RequirementPatch,
    RequirementPatchError,
    RequirementUpdateService,
)
from tests.requirements.test_requirement_model import base_model, base_requirement


def added_requirement():
    return Requirement(
        id="REQ_PROT_001",
        category="protection",
        type="reverse_polarity_protection",
        description="The circuit shall include reverse-polarity protection.",
        target=Target(type="power_input", id="VIN"),
        constraint={"kind": "boolean", "value": True},
        priority="required",
        enforcement="hard",
        origin=Origin(type="user", source_id="MSG_001"),
        status="confirmed",
        confidence=1.0,
    )


class RequirementUpdateServiceTests(unittest.TestCase):
    def test_apply_patch_does_not_mutate_original_and_increments_revision(self):
        original = base_model()
        service = RequirementUpdateService()

        updated = service.apply_patch(
            original,
            RequirementPatch(add_requirements=(added_requirement(),)),
            updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )

        self.assertEqual(len(original.requirements), 1)
        self.assertEqual(original.revision, 1)
        self.assertEqual(len(updated.requirements), 2)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.requirement_set_id, original.requirement_set_id)
        self.assertEqual(updated.project_id, original.project_id)
        self.assertEqual(updated.schema_version, original.schema_version)
        self.assertGreater(updated.metadata.updated_at, original.metadata.updated_at)

    def test_invalid_resulting_model_is_rejected(self):
        original = base_model()
        service = RequirementUpdateService()

        with self.assertRaises(ValidationError):
            service.apply_patch(
                original,
                RequirementPatch(add_requirements=(base_requirement("REQ_PWR_001"),)),
                updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            )

    def test_removed_referenced_requirement_is_rejected_by_full_validation(self):
        original = base_model(
            requirements=[
                base_requirement("REQ_PWR_001"),
                base_requirement("REQ_PWR_002").model_copy(
                    update={
                        "dependencies": [
                            Relationship(type="requires", requirement_id="REQ_PWR_001")
                        ]
                    }
                ),
            ]
        )
        service = RequirementUpdateService()

        with self.assertRaises(ValidationError):
            service.apply_patch(
                original,
                RequirementPatch(remove_requirement_ids=("REQ_PWR_001",)),
                updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            )

    def test_serialization_round_trip_after_update(self):
        service = RequirementUpdateService()
        updated = service.apply_patch(
            base_model(),
            RequirementPatch(add_requirements=(added_requirement(),)),
            updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )

        restored = type(updated).model_validate_json(updated.model_dump_json())
        self.assertEqual(restored.model_dump(mode="json"), updated.model_dump(mode="json"))

    def test_replace_unknown_requirement_is_rejected(self):
        service = RequirementUpdateService()

        with self.assertRaises(RequirementPatchError):
            service.apply_patch(
                base_model(),
                RequirementPatch(replace_requirements=(added_requirement(),)),
                updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            )

    def test_patch_updated_at_must_be_timezone_aware(self):
        service = RequirementUpdateService()

        with self.assertRaises(RequirementPatchError):
            service.apply_patch(
                base_model(),
                RequirementPatch(add_requirements=(added_requirement(),)),
                updated_at=datetime(2026, 8, 16),
            )


if __name__ == "__main__":
    unittest.main()
