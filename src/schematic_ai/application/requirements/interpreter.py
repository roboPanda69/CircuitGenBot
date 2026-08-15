"""Requirement interpreter orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from schematic_ai.application.requirements.drafts import (
    MessageEnvelope,
    RequirementChangeDraft,
    RequirementExtractionDraft,
)
from schematic_ai.application.requirements.enricher import RequirementEnricher
from schematic_ai.application.requirements.normalizer import (
    RequirementDraftNormalizationError,
    RequirementDraftNormalizer,
)
from schematic_ai.application.requirements.prompts import change_prompt, extraction_prompt, repair_prompt
from schematic_ai.config import load_settings
from schematic_ai.domain.requirements.models import OpenQuestion, RequirementModel
from schematic_ai.llm.client import LLMClient, LLMClientError


logger = logging.getLogger(__name__)
DraftT = TypeVar("DraftT", bound=BaseModel)


class RequirementInterpretationError(RuntimeError):
    def __init__(
        self,
        *,
        message_id: str,
        attempt_count: int,
        validation_summary: str,
    ) -> None:
        self.message_id = message_id
        self.attempt_count = attempt_count
        self.validation_summary = validation_summary
        super().__init__(
            f"failed to interpret {message_id} after {attempt_count} attempts: {validation_summary}"
        )


@dataclass(frozen=True)
class InterpretationResult:
    status: str
    model: RequirementModel | None = None
    open_questions: list[OpenQuestion] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status == "accepted" and self.model is not None


@dataclass
class RequirementInterpreter:
    llm_client: LLMClient
    normalizer: RequirementDraftNormalizer = field(default_factory=RequirementDraftNormalizer)
    enricher: RequirementEnricher = field(default_factory=RequirementEnricher)
    max_repair_attempts: int | None = None

    def interpret_new(
        self,
        message: MessageEnvelope,
        *,
        created_at: datetime | None = None,
    ) -> InterpretationResult:
        logger.info("interpreting new requirements message_id=%s", message.message_id)
        prompt = extraction_prompt(message)
        draft = self._generate_valid_draft(message, prompt, RequirementExtractionDraft)
        try:
            normalized = self.normalizer.normalize_extraction(draft)
            model = self.enricher.build_initial_model(
                message=message,
                draft=normalized,
                created_at=created_at,
            )
        except (RequirementDraftNormalizationError, ValidationError, ValueError) as exc:
            raise RequirementInterpretationError(
                message_id=message.message_id,
                attempt_count=1,
                validation_summary=str(exc),
            ) from exc
        status = "needs_input" if model.open_questions else "accepted"
        return InterpretationResult(status=status, model=model, open_questions=model.open_questions)

    def interpret_change(
        self,
        message: MessageEnvelope,
        current_model: RequirementModel,
        *,
        updated_at: datetime | None = None,
    ) -> InterpretationResult:
        logger.info(
            "interpreting requirement change message_id=%s revision=%s",
            message.message_id,
            current_model.revision,
        )
        prompt = change_prompt(message, current_model)
        draft = self._generate_valid_draft(message, prompt, RequirementChangeDraft)
        try:
            normalized = self.normalizer.normalize_change(draft)
            model, questions = self.enricher.apply_change(
                message=message,
                current_model=current_model,
                draft=normalized,
                updated_at=updated_at,
            )
        except (RequirementDraftNormalizationError, ValidationError, ValueError) as exc:
            raise RequirementInterpretationError(
                message_id=message.message_id,
                attempt_count=1,
                validation_summary=str(exc),
            ) from exc
        if model is None:
            return InterpretationResult(status="needs_input", open_questions=questions)
        if questions:
            return InterpretationResult(status="needs_input", model=model, open_questions=questions)
        return InterpretationResult(status="accepted", model=model, open_questions=[])

    def _generate_valid_draft(
        self,
        message: MessageEnvelope,
        prompt: str,
        model_type: type[DraftT],
    ) -> DraftT:
        schema = model_type.model_json_schema()
        attempts_allowed = 1 + self._max_repair_attempts()
        current_prompt = prompt
        last_output = ""
        last_error = ""

        for attempt in range(1, attempts_allowed + 1):
            logger.info(
                "calling llm message_id=%s draft=%s attempt=%s",
                message.message_id,
                model_type.__name__,
                attempt,
            )
            try:
                raw_output = self.llm_client.generate_structured(
                    prompt=current_prompt,
                    json_schema=schema,
                )
            except LLMClientError as exc:
                raise RequirementInterpretationError(
                    message_id=message.message_id,
                    attempt_count=attempt,
                    validation_summary=str(exc),
                ) from exc
            last_output = raw_output
            try:
                return model_type.model_validate_json(raw_output)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                logger.info(
                    "draft validation failed message_id=%s attempt=%s error=%s",
                    message.message_id,
                    attempt,
                    last_error,
                )
                current_prompt = repair_prompt(
                    original_prompt=prompt,
                    invalid_output=last_output,
                    validation_errors=last_error,
                    schema_name=model_type.__name__,
                )

        raise RequirementInterpretationError(
            message_id=message.message_id,
            attempt_count=attempts_allowed,
            validation_summary=last_error,
        )

    def _max_repair_attempts(self) -> int:
        if self.max_repair_attempts is not None:
            return self.max_repair_attempts
        return load_settings().llm_max_repair_attempts

