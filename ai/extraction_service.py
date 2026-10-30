"""AI Extraction Service with schema validation and evidence quote verification."""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from ai.llm_provider import get_llm_provider

class EvidenceQuote(BaseModel):
    field: str
    evidence_quote: str

class ExtractedIncidentOutput(BaseModel):
    incident_id: str
    issue_category: str = "unknown"
    observed_symptoms: List[str] = Field(default_factory=list)
    equipment_mentions: List[str] = Field(default_factory=list)
    reported_location: Optional[str] = None
    evidence_quotes: List[EvidenceQuote] = Field(default_factory=list)
    unknown_fields: List[str] = Field(default_factory=list)
    status: str = "success"
    provider: str = "deterministic"
    warning: Optional[str] = None

class ExtractionService:
    """Service to safely extract structured features from unstructured incident text."""

    def __init__(self):
        self.provider = get_llm_provider()

    def extract(self, incident_dict: Dict[str, Any]) -> ExtractedIncidentOutput:
        """
        Runs extraction and validates that all evidence quotes exist in the raw description.
        Rejects hallucinated or unsupported spans.
        """
        raw_text = incident_dict.get("description", "") or incident_dict.get("raw_description", "")
        raw_output = self.provider.extract_structured_incident(incident_dict)

        try:
            parsed = ExtractedIncidentOutput(**raw_output)
        except Exception:
            # Fallback to minimal valid schema if provider output is ill-formed
            parsed = ExtractedIncidentOutput(
                incident_id=incident_dict.get("incident_id", "INC-UNKNOWN"),
                issue_category="unknown",
                status="schema_validation_failed"
            )

        # Evidence span validation check against raw text
        verified_quotes = []
        raw_lower = raw_text.lower()
        for eq in parsed.evidence_quotes:
            quote_clean = eq.evidence_quote.strip().lower()
            if quote_clean and quote_clean in raw_lower:
                verified_quotes.append(eq)
            else:
                # Unsupported quote detected; drop to avoid ungrounded hallucination
                parsed.unknown_fields.append(f"unsupported_evidence_for_{eq.field}")

        parsed.evidence_quotes = verified_quotes
        return parsed
