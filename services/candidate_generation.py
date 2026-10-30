"""Deterministic Candidate Generation Engine for Cross-Unit Incident Intelligence."""
from typing import List, Dict, Set, Tuple, Optional
import datetime
from sqlalchemy.orm import Session
from database.models import Incident, UnitAssetLink, Unit, Building
from schemas.relationship import CandidatePair

class CandidateGenerationEngine:
    """
    Generates candidate pairs for relationship scoring using property boundaries,
    spatial topology, shared infrastructure, and temporal windows.
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_candidates_for_incident(
        self,
        incident: Incident,
        max_time_window_days: int = 14
    ) -> List[CandidatePair]:
        """
        Generate candidate relationships for a single anchor incident.
        Adheres strictly to the 4-stage policy contract:
        1. Hard scope filter (property boundary)
        2. Eligibility filter (minimum signal)
        3. Candidate retrieval (shared infrastructure -> topology/time window)
        4. Canonical ordering
        """
        # Stage 1 & 2: Hard scope & Eligibility check
        if not incident.property_id or not incident.created_at:
            return []
        
        # If incident has neither building, unit, nor asset, insufficient spatial signal
        if not incident.building_id and not incident.unit_id and not incident.asset_id:
            return []

        # Find assets connected to this incident's unit or direct asset
        connected_asset_ids: Set[str] = set()
        if incident.asset_id:
            connected_asset_ids.add(incident.asset_id)
        if incident.unit_id:
            links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == incident.unit_id).all()
            for link in links:
                connected_asset_ids.add(link.asset_id)

        # Time window boundaries
        time_min = incident.created_at - datetime.timedelta(days=max_time_window_days)
        time_max = incident.created_at + datetime.timedelta(days=max_time_window_days)

        # Stage 3: Query candidate incidents within the SAME PROPERTY and time window
        candidates = self.db.query(Incident).filter(
            Incident.property_id == incident.property_id,
            Incident.incident_id != incident.incident_id,
            Incident.created_at >= time_min,
            Incident.created_at <= time_max
        ).all()

        candidate_pairs: List[CandidatePair] = []

        for other in candidates:
            # Check eligibility of candidate
            if not other.building_id and not other.unit_id and not other.asset_id:
                continue

            reasons = []

            # Channel A: Shared infrastructure / asset
            other_asset_ids: Set[str] = set()
            if other.asset_id:
                other_asset_ids.add(other.asset_id)
            if other.unit_id:
                other_links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == other.unit_id).all()
                for link in other_links:
                    other_asset_ids.add(link.asset_id)

            time_diff_hours = abs((incident.created_at - other.created_at).total_seconds()) / 3600.0
            common_assets = connected_asset_ids & other_asset_ids
            if common_assets and time_diff_hours <= 168.0:
                reasons.append(f"Connected to shared infrastructure: {', '.join(sorted(list(common_assets)))} within {time_diff_hours/24:.1f} days")

            # Channel B: Same Unit within 14 days
            if incident.unit_id and other.unit_id and incident.unit_id == other.unit_id:
                time_diff_hours = abs((incident.created_at - other.created_at).total_seconds()) / 3600.0
                if time_diff_hours <= 336.0:  # 14 days
                    reasons.append(f"Reported in the same unit ({incident.unit_id}) within {time_diff_hours/24:.1f} days")

            # Channel C: Same Building & Temporal Proximity (Requires compatible category and <= 72h)
            if incident.building_id and other.building_id and incident.building_id == other.building_id:
                time_diff_hours = abs((incident.created_at - other.created_at).total_seconds()) / 3600.0
                
                # Check category compatibility
                cat_match = (incident.normalized_category == other.normalized_category)
                compatible_cats = [
                    {"plumbing", "water_intrusion"},
                    {"plumbing", "structural"},
                    {"water_intrusion", "structural"},
                ]
                is_compatible = cat_match or ({incident.normalized_category, other.normalized_category} in compatible_cats)

                if is_compatible and time_diff_hours <= 72.0:
                    reasons.append(f"Co-located in Building {incident.building_id} with compatible category ({incident.normalized_category}) within {time_diff_hours:.1f} hours")

                # Vertical stacking heuristic (e.g. Unit 101, 201, 301)
                if incident.unit_id and other.unit_id and incident.unit_id != other.unit_id and is_compatible and time_diff_hours <= 96.0:
                    u1 = self.db.query(Unit).filter(Unit.unit_id == incident.unit_id).first()
                    u2 = self.db.query(Unit).filter(Unit.unit_id == other.unit_id).first()
                    if u1 and u2 and u1.unit_number and u2.unit_number:
                        if len(u1.unit_number) >= 3 and len(u2.unit_number) >= 3:
                            if u1.unit_number[-2:] == u2.unit_number[-2:]:
                                reasons.append(f"Vertical stack alignment (Units {u1.unit_number} & {u2.unit_number})")

            # If at least one valid retrieval reason matched, construct candidate pair
            if reasons:
                # Stage 4: Enforce canonical ordering (min_id, max_id)
                id_a, id_b = (incident.incident_id, other.incident_id) if incident.incident_id < other.incident_id else (other.incident_id, incident.incident_id)
                candidate_pairs.append(
                    CandidatePair(
                        incident_a_id=id_a,
                        incident_b_id=id_b,
                        generation_reasons=reasons,
                        property_id=incident.property_id
                    )
                )

        # De-duplicate candidate pairs
        unique_pairs: Dict[Tuple[str, str], CandidatePair] = {}
        for cp in candidate_pairs:
            key = (cp.incident_a_id, cp.incident_b_id)
            if key not in unique_pairs:
                unique_pairs[key] = cp
            else:
                # Merge reasons
                combined_reasons = list(set(unique_pairs[key].generation_reasons + cp.generation_reasons))
                unique_pairs[key].generation_reasons = combined_reasons

        return list(unique_pairs.values())

    def generate_all_candidates(self, property_id: Optional[str] = None) -> List[CandidatePair]:
        """Generate candidate pairs across all active incidents in the database."""
        query = self.db.query(Incident)
        if property_id:
            query = query.filter(Incident.property_id == property_id)
        all_incidents = query.all()

        seen_pairs: Dict[Tuple[str, str], CandidatePair] = {}
        for inc in all_incidents:
            cands = self.generate_candidates_for_incident(inc)
            for c in cands:
                key = (c.incident_a_id, c.incident_b_id)
                if key not in seen_pairs:
                    seen_pairs[key] = c

        return list(seen_pairs.values())
