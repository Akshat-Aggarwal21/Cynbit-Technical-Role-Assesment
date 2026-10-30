"""Scoring configuration for incident relationship evaluation."""
from pydantic import BaseModel, Field

class ScoringWeights(BaseModel):
    """Configurable weights for the review-ranking score."""
    shared_asset: float = Field(default=0.30, ge=0.0, le=1.0)
    topology: float = Field(default=0.25, ge=0.0, le=1.0)
    temporal: float = Field(default=0.20, ge=0.0, le=1.0)
    category: float = Field(default=0.15, ge=0.0, le=1.0)
    symptoms: float = Field(default=0.10, ge=0.0, le=1.0)

class ScoringThresholds(BaseModel):
    """Review ranking score thresholds."""
    suggest_for_review: float = Field(default=50.0, ge=0.0, le=100.0)
    low_evidence: float = Field(default=30.0, ge=0.0, le=100.0)

class TemporalDecayConfig(BaseModel):
    """Half-life or decay scale (in hours) per issue category."""
    plumbing_hours: float = 72.0
    hvac_hours: float = 96.0
    electrical_hours: float = 48.0
    structural_hours: float = 120.0
    default_hours: float = 72.0

class ScoringConfig(BaseModel):
    weights: ScoringWeights = ScoringWeights()
    thresholds: ScoringThresholds = ScoringThresholds()
    decay: TemporalDecayConfig = TemporalDecayConfig()

scoring_config = ScoringConfig()
