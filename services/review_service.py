"""Human Review and Audit Trail Service."""
import uuid
import datetime
from typing import List, Optional, Dict, Any
import pandas as pd
from sqlalchemy.orm import Session
from database.models import ReviewDecision, IncidentRelationship, RecurrenceFlag, Incident
from schemas.review import ReviewDecisionCreate

class ReviewService:
    """Manages reviewer adjudication, audit history, and CSV data exports."""

    def __init__(self, db: Session):
        self.db = db

    def submit_decision(self, form: ReviewDecisionCreate, rule_version: str = "v1.2.0") -> ReviewDecision:
        """
        Record a human review decision (accept, reject, uncertain) with audit persistence.
        Does NOT overwrite historical decisions; stores an append-only log entry.
        """
        decision_id = f"DEC_{uuid.uuid4().hex[:10].upper()}"
        
        entry = ReviewDecision(
            decision_id=decision_id,
            target_type=form.target_type,
            target_id=form.target_id,
            decision=form.decision,
            reviewer_id=form.reviewer_id or "coordinator",
            reason=form.reason,
            rule_version=rule_version,
            created_at=datetime.datetime.utcnow()
        )
        self.db.add(entry)

        # Update the active status on the target entity if applicable
        if form.target_type == "recurrence":
            flag = self.db.query(RecurrenceFlag).filter_by(flag_id=form.target_id).first()
            if flag:
                flag.status = f"reviewed_{form.decision}"
        elif form.target_type == "relationship":
            rel = self.db.query(IncidentRelationship).filter_by(relationship_id=form.target_id).first()
            if rel and form.decision == "reject":
                rel.recommendation_tier = "rejected_by_human"
            elif rel and form.decision == "accept":
                rel.recommendation_tier = "accepted_by_human"

        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_audit_history(self, target_id: Optional[str] = None) -> List[ReviewDecision]:
        """Fetch review decision audit trail."""
        query = self.db.query(ReviewDecision)
        if target_id:
            query = query.filter(ReviewDecision.target_id == target_id)
        return query.order_by(ReviewDecision.created_at.desc()).all()

    def export_incidents_csv(self) -> str:
        """Export all incidents as CSV string."""
        incidents = self.db.query(Incident).all()
        data = []
        for inc in incidents:
            data.append({
                "incident_id": inc.incident_id,
                "property_id": inc.property_id,
                "building_id": inc.building_id,
                "unit_id": inc.unit_id,
                "asset_id": inc.asset_id,
                "created_at": inc.created_at.isoformat() if inc.created_at else "",
                "normalized_category": inc.normalized_category,
                "symptoms": "; ".join(inc.symptoms or []),
                "severity": inc.severity,
                "status": inc.status,
                "raw_description": inc.raw_description,
                "is_duplicate_of": inc.is_duplicate_of,
                "is_synthetic": inc.is_synthetic
            })
        return pd.DataFrame(data).to_csv(index=False)

    def export_relationships_csv(self) -> str:
        """Export all candidate relationships and scores as CSV string."""
        rels = self.db.query(IncidentRelationship).all()
        data = []
        for r in rels:
            data.append({
                "relationship_id": r.relationship_id,
                "incident_a_id": r.incident_a_id,
                "incident_b_id": r.incident_b_id,
                "review_score": r.review_score,
                "recommendation_tier": r.recommendation_tier,
                "evidence_summary": r.evidence_summary.replace("\n", " "),
                "missing_evidence": "; ".join(r.missing_evidence or []),
                "contradictory_evidence": "; ".join(r.contradictory_evidence or []),
                "rule_version": r.rule_version,
                "created_at": r.created_at.isoformat() if r.created_at else ""
            })
        return pd.DataFrame(data).to_csv(index=False)

    def export_recurrence_csv(self) -> str:
        """Export all recurrence flags as CSV string."""
        flags = self.db.query(RecurrenceFlag).all()
        data = []
        for f in flags:
            data.append({
                "flag_id": f.flag_id,
                "new_incident_id": f.new_incident_id,
                "prior_incident_id": f.prior_incident_id,
                "repair_id": f.repair_id,
                "days_since_repair": f.days_since_repair,
                "recurrence_window_days": f.recurrence_window_days,
                "similarity_score": f.similarity_score,
                "evidence_summary": f.evidence_summary,
                "status": f.status,
                "created_at": f.created_at.isoformat() if f.created_at else ""
            })
        return pd.DataFrame(data).to_csv(index=False)

    def export_reviews_csv(self) -> str:
        """Export human reviewer audit decisions as CSV string."""
        decisions = self.db.query(ReviewDecision).all()
        data = []
        for d in decisions:
            data.append({
                "decision_id": d.decision_id,
                "target_type": d.target_type,
                "target_id": d.target_id,
                "decision": d.decision,
                "reviewer_id": d.reviewer_id,
                "reason": d.reason,
                "rule_version": d.rule_version,
                "created_at": d.created_at.isoformat() if d.created_at else ""
            })
        return pd.DataFrame(data).to_csv(index=False)
