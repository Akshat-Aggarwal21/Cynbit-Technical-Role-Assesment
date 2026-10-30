"""Pydantic schemas for Incident data validation and normalization contracts."""
from typing import List, Optional
import datetime
from pydantic import BaseModel, Field, field_validator

ALLOWED_CATEGORIES = {
    "plumbing", "water_intrusion", "hvac", "electrical",
    "structural", "appliance", "security", "general_maintenance", "unknown"
}

ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
ALLOWED_STATUSES = {"open", "in_progress", "repaired", "closed"}

class IncidentInput(BaseModel):
    """Raw input record from CSV upload or manual creation form."""
    incident_id: str = Field(..., description="Unique incident identifier")
    property_id: str = Field(..., description="Property identifier boundary")
    building_id: Optional[str] = Field(None, description="Building identifier")
    unit_id: Optional[str] = Field(None, description="Specific unit identifier")
    asset_id: Optional[str] = Field(None, description="Direct asset or shared system identifier")
    created_at: datetime.datetime = Field(..., description="Timestamp when incident was reported")
    raw_description: str = Field(..., min_length=3, description="Original unprocessed incident description")
    normalized_category: Optional[str] = Field("unknown", description="Issue category")
    symptoms: Optional[List[str]] = Field(default_factory=list, description="Extracted symptom tags")
    severity: Optional[str] = Field("medium", description="Reported severity level")
    status: Optional[str] = Field("open", description="Current ticket status")
    source_reference: Optional[str] = Field(None, description="CSV source or integration reference")

    @field_validator("raw_description")
    def validate_description(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Description cannot be empty or only whitespace")
        return clean

    @field_validator("severity")
    def validate_severity(cls, v: Optional[str]) -> str:
        if not v:
            return "medium"
        low = v.strip().lower()
        if low not in ALLOWED_SEVERITIES:
            return "medium"
        return low

    @field_validator("status")
    def validate_status(cls, v: Optional[str]) -> str:
        if not v:
            return "open"
        low = v.strip().lower()
        if low not in ALLOWED_STATUSES:
            return "open"
        return low


class NormalizedIncident(BaseModel):
    """Normalized incident model ready for persistence and scoring."""
    incident_id: str
    property_id: str
    building_id: Optional[str] = None
    unit_id: Optional[str] = None
    asset_id: Optional[str] = None
    raw_description: str
    normalized_category: str
    symptoms: List[str]
    severity: str
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    closed_at: Optional[datetime.datetime] = None
    source_reference: Optional[str] = None
    is_duplicate_of: Optional[str] = None
    duplicate_confidence: Optional[float] = None
    is_synthetic: bool = True


class IngestionErrorRecord(BaseModel):
    """Detailed validation error for a failed ingestion row."""
    row_index: int
    raw_data: dict
    error_message: str
    error_fields: List[str]
