"""Duplicate detection service for identifying exact and near-duplicate incidents."""
from typing import Tuple, Optional, List
import datetime
from sqlalchemy.orm import Session
from database.models import Incident
from services.normalization_service import NormalizationService

class DuplicateDetectionService:
    """Detects exact or near-duplicate maintenance incidents without silent deletion."""

    def __init__(self, db: Session):
        self.db = db

    def check_duplicate(
        self,
        property_id: str,
        unit_id: Optional[str],
        created_at: datetime.datetime,
        raw_description: str,
        exclude_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str], float, str]:
        """
        Evaluate if an incoming incident is a duplicate of an existing record.
        Returns: (is_duplicate, original_incident_id, confidence, reason)
        """
        clean_desc = NormalizationService.clean_text(raw_description).lower()

        # Query candidates in the same property within a 48-hour window
        window_start = created_at - datetime.timedelta(hours=48)
        window_end = created_at + datetime.timedelta(hours=48)

        query = self.db.query(Incident).filter(
            Incident.property_id == property_id,
            Incident.created_at >= window_start,
            Incident.created_at <= window_end
        )
        if exclude_id:
            query = query.filter(Incident.incident_id != exclude_id)

        candidates: List[Incident] = query.all()

        for cand in candidates:
            cand_desc = NormalizationService.clean_text(cand.raw_description).lower()
            
            # Exact description match
            if clean_desc == cand_desc and (unit_id == cand.unit_id or (unit_id is None and cand.unit_id is None)):
                time_diff = abs((created_at - cand.created_at).total_seconds())
                if time_diff < 3600:  # Within 1 hour
                    return (True, cand.incident_id, 1.0, "Identical description, same unit, reported within 1 hour")
                else:
                    return (True, cand.incident_id, 0.90, "Identical description and same unit within 48 hours")

            # Word-level Jaccard overlap for near-duplicates
            words_a = set(clean_desc.split())
            words_b = set(cand_desc.split())
            if words_a and words_b:
                jaccard = len(words_a & words_b) / len(words_a | words_b)
                if jaccard >= 0.85 and unit_id == cand.unit_id and unit_id is not None:
                    return (True, cand.incident_id, round(jaccard, 2), f"High lexical overlap ({jaccard:.0%}) for same unit")

        return (False, None, 0.0, "No duplicate detected")
