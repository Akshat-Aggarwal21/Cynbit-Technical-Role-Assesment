"""Repair Recurrence Verification Service."""
from typing import List, Optional, Set
import datetime
from sqlalchemy.orm import Session
from database.models import Incident, RepairRecord, RecurrenceFlag, UnitAssetLink
from config.recurrence_config import recurrence_config
from services.explanation_service import ExplanationService
from services.normalization_service import utc_now

class RecurrenceDetectionService:
    """Detects and flags potential recurrence of maintenance issues following completed repairs."""

    def __init__(self, db: Session):
        self.db = db
        self.config = recurrence_config

    def check_incident_for_recurrence(
        self,
        new_incident: Incident
    ) -> List[RecurrenceFlag]:
        """
        Check if a given new incident represents a possible recurrence of an earlier repaired issue.
        """
        if not new_incident.created_at:
            return []

        # Find connected assets for the new incident
        connected_assets: Set[str] = set()
        if new_incident.asset_id:
            connected_assets.add(new_incident.asset_id)
        if new_incident.unit_id:
            links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == new_incident.unit_id).all()
            for l in links:
                connected_assets.add(l.asset_id)

        # Get window for this incident's category
        window_days = self.config.category_windows_days.get(
            new_incident.normalized_category,
            self.config.category_windows_days["default"]
        )

        min_repair_date = new_incident.created_at - datetime.timedelta(days=window_days)

        # Query completed repairs completed before the new incident, within window
        repairs: List[RepairRecord] = self.db.query(RepairRecord).join(Incident).filter(
            Incident.property_id == new_incident.property_id,
            RepairRecord.completed_at <= new_incident.created_at,
            RepairRecord.completed_at >= min_repair_date
        ).all()

        flags: List[RecurrenceFlag] = []

        for rep in repairs:
            prior_inc = rep.incident
            if not prior_inc or prior_inc.incident_id == new_incident.incident_id:
                continue

            # Check spatial relationship (same unit or connected shared asset)
            same_unit = (
                new_incident.unit_id is not None
                and prior_inc.unit_id is not None
                and new_incident.unit_id == prior_inc.unit_id
            )

            # Check shared asset
            prior_assets: Set[str] = set()
            if prior_inc.asset_id:
                prior_assets.add(prior_inc.asset_id)
            if prior_inc.unit_id:
                prior_links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == prior_inc.unit_id).all()
                for pl in prior_links:
                    prior_assets.add(pl.asset_id)

            shared_asset = bool(connected_assets & prior_assets)

            if not (same_unit or shared_asset):
                continue

            # Calculate elapsed time in days (timezone safe)
            t_new = new_incident.created_at
            t_rep = rep.completed_at
            if t_new.tzinfo is not None:
                t_new = t_new.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            if t_rep.tzinfo is not None:
                t_rep = t_rep.astimezone(datetime.timezone.utc).replace(tzinfo=None)

            days_elapsed = (t_new - t_rep).total_seconds() / 86400.0
            if days_elapsed < 0 or days_elapsed > window_days:
                continue

            # Check symptom or category similarity
            cat_match = (new_incident.normalized_category == prior_inc.normalized_category)
            s1 = set(new_incident.symptoms or [])
            s2 = set(prior_inc.symptoms or [])
            symptom_overlap = s1 & s2
            
            similarity = 0.4 if cat_match else 0.0
            if symptom_overlap:
                similarity += 0.6 * (len(symptom_overlap) / max(1, len(s1 | s2)))

            # If same unit, category match + some symptom signal is sufficient
            # If across units on shared asset, require explicit symptom overlap
            is_valid_candidate = False
            if same_unit and (cat_match or similarity >= self.config.symptom_similarity_threshold):
                is_valid_candidate = True
            elif shared_asset and symptom_overlap and cat_match and similarity >= 0.50:
                is_valid_candidate = True

            if is_valid_candidate:
                flag_id = f"REC_{new_incident.incident_id}_{rep.repair_id}"
                explanation = ExplanationService.explain_recurrence(
                    new_incident_id=new_incident.incident_id,
                    prior_incident_id=prior_inc.incident_id,
                    repair_id=rep.repair_id,
                    days_since_repair=days_elapsed,
                    repair_action=rep.action_taken,
                    symptom_overlap=sorted(list(symptom_overlap))
                )

                flag = RecurrenceFlag(
                    flag_id=flag_id,
                    new_incident_id=new_incident.incident_id,
                    prior_incident_id=prior_inc.incident_id,
                    repair_id=rep.repair_id,
                    days_since_repair=round(days_elapsed, 1),
                    recurrence_window_days=window_days,
                    similarity_score=round(similarity, 2),
                    evidence_summary=explanation,
                    status="flagged",
                    created_at=utc_now()
                )
                flags.append(flag)

        return flags

    def scan_all_for_recurrence(self) -> List[RecurrenceFlag]:
        """Scan all incidents to identify and persist recurrence flags."""
        all_incidents = self.db.query(Incident).order_by(Incident.created_at.asc()).all()

        for inc in all_incidents:
            flags = self.check_incident_for_recurrence(inc)
            for f in flags:
                existing = self.db.query(RecurrenceFlag).filter_by(flag_id=f.flag_id).first()
                if not existing:
                    self.db.add(f)
        
        self.db.commit()
        return self.db.query(RecurrenceFlag).all()
