"""Recurrence configuration for post-repair incident monitoring."""
from typing import Dict
from pydantic import BaseModel, Field

class RecurrenceConfig(BaseModel):
    """Configuration for issue-specific recurrence windows in days."""
    category_windows_days: Dict[str, int] = Field(
        default_factory=lambda: {
            "plumbing": 30,
            "water_intrusion": 30,
            "hvac": 45,
            "electrical": 21,
            "structural": 60,
            "appliance": 14,
            "default": 30,
        }
    )
    # Minimum similarity threshold to flag as possible recurrence
    symptom_similarity_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    # Same unit direct match automatically considered if within window
    same_unit_direct_match: bool = True

recurrence_config = RecurrenceConfig()
