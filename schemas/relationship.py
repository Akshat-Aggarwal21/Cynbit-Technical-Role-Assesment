"""Pydantic schemas for incident relationships and transparent scoring."""
from typing import List, Dict, Any, Optional
import datetime
from pydantic import BaseModel, Field

class FactorDetail(BaseModel):
    factor_name: str
    weight: float
    raw_value: float
    weighted_value: float
    is_available: bool
    evidence_text: str

class ScoreFactors(BaseModel):
    shared_asset: FactorDetail
    topology: FactorDetail
    temporal: FactorDetail
    category: FactorDetail
    symptoms: FactorDetail

class CandidatePair(BaseModel):
    incident_a_id: str
    incident_b_id: str
    generation_reasons: List[str]
    property_id: str

class IncidentRelationshipSchema(BaseModel):
    relationship_id: str
    incident_a_id: str
    incident_b_id: str
    review_score: float = Field(..., ge=0.0, le=100.0, description="Review-ranking score (0-100)")
    score_factors: Dict[str, Any]
    evidence_summary: str
    missing_evidence: List[str] = Field(default_factory=list)
    contradictory_evidence: List[str] = Field(default_factory=list)
    recommendation_tier: str  # "suggest_for_review", "low_evidence", "insufficient_evidence"
    rule_version: str
    created_at: datetime.datetime
