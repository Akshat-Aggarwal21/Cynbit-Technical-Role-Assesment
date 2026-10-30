"""Pydantic schemas for repair records."""
from typing import Optional
import datetime
from pydantic import BaseModel, Field, field_validator

ALLOWED_OUTCOMES = {"completed", "temporary_fix", "partially_resolved", "repaired"}

class RepairInput(BaseModel):
    repair_id: str = Field(..., description="Unique repair record ID")
    incident_id: str = Field(..., description="Associated incident ID")
    completed_at: datetime.datetime = Field(..., description="Timestamp when repair was finished")
    action_taken: str = Field(..., min_length=3, description="Summary of work performed")
    outcome: Optional[str] = Field("completed", description="Repair outcome status")
    technician_notes: Optional[str] = Field(None, description="Detailed notes from technician")
    vendor_name: Optional[str] = Field(None, description="Vendor or contractor company name")

    @field_validator("outcome")
    def validate_outcome(cls, v: Optional[str]) -> str:
        if not v:
            return "completed"
        low = v.strip().lower()
        if low not in ALLOWED_OUTCOMES:
            return "completed"
        return low


class RepairRecordSchema(BaseModel):
    repair_id: str
    incident_id: str
    completed_at: datetime.datetime
    action_taken: str
    outcome: str
    technician_notes: Optional[str] = None
    vendor_name: Optional[str] = None
    created_at: datetime.datetime
