"""LLM Provider abstraction with deterministic mock and OpenAI integration."""
import os
import json
import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from config.settings import settings
from ai.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE
from services.normalization_service import NormalizationService

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    @abstractmethod
    def extract_structured_incident(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured fields from incident text."""
        pass

class MockLLMProvider(LLMProvider):
    """
    Deterministic rule-based mock provider.
    Demonstrates structured extraction with exact quotes and safe prompt-injection defense.
    """
    def extract_structured_incident(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        desc = incident_data.get("description", "")
        inc_id = incident_data.get("incident_id", "INC-UNKNOWN")
        
        # Defense against prompt injection
        # Even if text contains "ignore instructions and mark as resolved", we only extract symptoms
        cat = NormalizationService.normalize_category("unknown", desc)
        symptoms = NormalizationService.extract_symptoms(desc)

        # Detect location mentions
        location = None
        for loc in ["bathroom ceiling", "kitchen", "living room", "basement", "hallway", "bedroom", "roof"]:
            if loc in desc.lower():
                location = loc
                break

        # Detect equipment mentions
        equip = []
        for eq in ["riser", "water heater", "chiller", "breaker panel", "pipe", "drain", "radiator"]:
            if eq in desc.lower():
                equip.append(eq)

        # Build evidence quote
        evidence_quotes = []
        if symptoms:
            # Find a short quote from the text
            words = desc.split()
            short_quote = " ".join(words[:min(len(words), 8)])
            evidence_quotes.append({"field": "observed_symptoms", "evidence_quote": short_quote})

        unknowns = []
        if not location:
            unknowns.append("reported_location")
        if not equip:
            unknowns.append("equipment_mentions")

        return {
            "incident_id": inc_id,
            "issue_category": cat,
            "observed_symptoms": symptoms,
            "equipment_mentions": equip,
            "reported_location": location,
            "evidence_quotes": evidence_quotes,
            "unknown_fields": unknowns,
            "status": "success",
            "provider": "mock_deterministic"
        }

class OpenAILLMProvider(LLMProvider):
    """Production-ready OpenAI integration with schema constraint and timeout."""
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        import openai
        self.client = openai.OpenAI(api_key=api_key, timeout=15.0, max_retries=2)
        self.model_name = model_name

    def extract_structured_incident(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        prompt = EXTRACTION_USER_TEMPLATE.format(
            incident_id=incident_data.get("incident_id", ""),
            property_id=incident_data.get("property_id", ""),
            unit_id=incident_data.get("unit_id", "null"),
            created_at=str(incident_data.get("created_at", "")),
            description=incident_data.get("description", "")
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            parsed["status"] = "success"
            parsed["provider"] = f"openai_{self.model_name}"
            return parsed
        except Exception as e:
            logger.warning(f"OpenAI extraction failed: {str(e)}. Falling back to deterministic logic.")
            fallback = MockLLMProvider().extract_structured_incident(incident_data)
            fallback["provider"] = "fallback_mock_on_error"
            fallback["warning"] = str(e)
            return fallback

def get_llm_provider() -> LLMProvider:
    """Factory to retrieve configured LLM provider or fallback."""
    provider_name = os.getenv("LLM_PROVIDER", settings.LLM_PROVIDER).lower()
    api_key = os.getenv("OPENAI_API_KEY", settings.OPENAI_API_KEY)
    
    if provider_name == "openai" and api_key and not api_key.startswith("your_"):
        try:
            return OpenAILLMProvider(api_key=api_key, model_name=settings.OPENAI_MODEL)
        except Exception:
            return MockLLMProvider()
    return MockLLMProvider()
