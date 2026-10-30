"""Pydantic schemas for reviewer decisions and audit trail."""
from typing import Optional
import datetime
from pydantic import BaseModel, Field, field_validator

ALLOWED_DECISIONS = {"accept", "reject", "uncertain"}
ALLOWED_TARGET_TYPES = {"relationship", "recurrence"}

class ReviewDecisionCreate(BaseModel):
    target_type: str = Field(..., description="Target type: 'relationship' or 'recurrence'")
    target_id: str = Field(..., description="ID of relationship or recurrence flag")
    decision: str = Field(..., description="Review action: 'accept', 'reject', 'uncertain'")
    reviewer_id: Optional[str] = Field("maintenance_coordinator", description="ID of reviewer")
    reason: Optional[str] = Field(None, description="Reviewer commentary or rationale")

    @field_validator("decision")
    def validate_decision(cls, v: str) -> str:
        low = v.strip().lower()
        if low not in ALLOWED_DECISIONS:
            raise ValueError(f"Decision must be one of: {ALLOWED_DECISIONS}")
        return low

    @field_validator("target_type")
    def validate_target_type(cls, v: str) -> str:
        low = v.strip().lower()
        if low not in ALLOWED_TARGET_TYPES:
            raise ValueError(f"Target type must be one of: {ALLOWED_TARGET_TYPES}")
        return low


class ReviewDecisionSchema(BaseModel):
    decision_id: str
    target_type: str
    target_id: str
    decision: str
    reviewer_id: str
    reason: Optional[str] = None
    rule_version: str
    created_at: datetime.datetime
