"""Controlled vocabularies for Engineering Knowledge v0.1."""

from __future__ import annotations

from enum import StrEnum


class ComponentCategory(StrEnum):
    REGULATOR = "regulator"
    POWER_CONVERTER = "power_converter"
    MOSFET = "mosfet"
    DIODE = "diode"
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    SENSOR = "sensor"
    MICROCONTROLLER = "microcontroller"
    INTERFACE_IC = "interface_ic"
    ISOLATOR = "isolator"
    OP_AMP = "op_amp"
    CONNECTOR = "connector"
    RELAY = "relay"
    PROTECTION_DEVICE = "protection_device"
    LOGIC_IC = "logic_ic"
    MEMORY = "memory"
    TIMING_DEVICE = "timing_device"
    OTHER = "other"


class DocumentationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    USER_SUPPLIED_ONLY = "user_supplied_only"
    MISSING = "missing"
    UNVERIFIED = "unverified"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    NOT_RECOMMENDED_FOR_NEW_DESIGNS = "not_recommended_for_new_designs"
    OBSOLETE = "obsolete"
    UNKNOWN = "unknown"


class KnowledgeState(StrEnum):
    VERIFIED = "verified"
    VERIFIED_NO = "verified_no"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


class KnowledgeSourceType(StrEnum):
    MANUFACTURER_DATASHEET = "manufacturer_datasheet"
    MANUFACTURER_REFERENCE_MANUAL = "manufacturer_reference_manual"
    MANUFACTURER_SAFETY_MANUAL = "manufacturer_safety_manual"
    MANUFACTURER_APPLICATION_NOTE = "manufacturer_application_note"
    MANUFACTURER_REFERENCE_DESIGN = "manufacturer_reference_design"
    MANUFACTURER_PRODUCT_PAGE = "manufacturer_product_page"
    STANDARD = "standard"
    QUALIFICATION_DOCUMENT = "qualification_document"
    KICAD_LIBRARY = "kicad_library"
    MANUAL_ENTRY = "manual_entry"
    INTERNAL_DOCUMENT = "internal_document"
    STRUCTURED_IMPORT = "structured_import"
    OTHER = "other"


class SourceTrustClass(StrEnum):
    AUTHORITATIVE = "authoritative"
    TRUSTED_SECONDARY = "trusted_secondary"
    CURATED_INTERNAL = "curated_internal"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


class ExtractionMethod(StrEnum):
    MANUAL = "manual"
    STRUCTURED_IMPORT = "structured_import"
    KICAD_INDEX = "kicad_index"
    PARSER = "parser"
    FUTURE_LLM_DRAFT = "future_llm_draft"
    OTHER = "other"


class EvidenceValidationMethod(StrEnum):
    MANUAL_REVIEW = "manual_review"
    SCHEMA_VALIDATION = "schema_validation"
    LOCAL_FILE_INDEX = "local_file_index"
    CONSISTENCY_CHECK = "consistency_check"
    NOT_VALIDATED = "not_validated"
    OTHER = "other"


class ComplianceStandard(StrEnum):
    ISO_26262 = "ISO_26262"
    ISO_SAE_21434 = "ISO_SAE_21434"
    AEC_Q100 = "AEC_Q100"
    AEC_Q101 = "AEC_Q101"
    AEC_Q102 = "AEC_Q102"
    AEC_Q103 = "AEC_Q103"
    AEC_Q104 = "AEC_Q104"
    AEC_Q200 = "AEC_Q200"
    IEC = "IEC"
    UL = "UL"
    OTHER = "other"


class ComplianceClaimType(StrEnum):
    QUALIFIED_TO = "qualified_to"
    DEVELOPED_ACCORDING_TO = "developed_according_to"
    COMPLIANT_PRODUCT = "compliant_product"
    COMPLIANT_DEVELOPMENT_PROCESS = "compliant_development_process"
    SAFETY_DOCUMENTATION_AVAILABLE = "safety_documentation_available"
    SUPPORTS_TARGET_INTEGRITY_LEVEL = "supports_target_integrity_level"
    MANUFACTURER_CLAIM = "manufacturer_claim"
    THIRD_PARTY_CERTIFIED = "third_party_certified"
    OTHER = "other"


class ComplianceDomain(StrEnum):
    CONSUMER = "consumer"
    INDUSTRIAL = "industrial"
    AUTOMOTIVE = "automotive"
    MEDICAL = "medical"
    AEROSPACE = "aerospace"
    RAILWAY = "railway"
    OTHER = "other"


class EngineeringRuleCategory(StrEnum):
    POWER = "power"
    PROTECTION = "protection"
    INTERFACE = "interface"
    ANALOG = "analog"
    DIGITAL = "digital"
    THERMAL = "thermal"
    QUALIFICATION = "qualification"
    SAFETY = "safety"
    LAYOUT = "layout"
    OTHER = "other"


class EngineeringRuleSeverity(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    ADVISORY = "advisory"
    INFO = "info"


class EngineeringRuleStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DRAFT = "draft"
    RETIRED = "retired"


class KnowledgeImportMode(StrEnum):
    CREATE_OR_ENRICH = "create_or_enrich"
    CREATE_ONLY = "create_only"
    ENRICH_EXISTING = "enrich_existing"
    VALIDATE_ONLY = "validate_only"


class KnowledgeImportStatus(StrEnum):
    CREATED = "created"
    UPDATED_EXISTING = "updated_existing"
    DUPLICATE = "duplicate"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class SourceReferenceType(StrEnum):
    LOCAL_JSON = "local_json"
    LOCAL_YAML = "local_yaml"
    LOCAL_PDF = "local_pdf"
    STRUCTURED_DATA = "structured_data"
    INTERNAL_DOCUMENT = "internal_document"
    KICAD_LIBRARY = "kicad_library"
    MANUAL = "manual"
    OTHER = "other"
