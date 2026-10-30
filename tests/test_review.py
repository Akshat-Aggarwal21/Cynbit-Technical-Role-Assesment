"""Unit tests for human review decisions and audit trail persistence."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base
from database.models import ReviewDecision, IncidentRelationship, RecurrenceFlag
from schemas.review import ReviewDecisionCreate
from services.review_service import ReviewService

@pytest.fixture
def review_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()

def test_submit_review_decision_persists_without_overwriting(review_db):
    service = ReviewService(review_db)
    target_id = "REL_INC-001_INC-002"

    # First reviewer decision: uncertain
    d1 = service.submit_decision(
        ReviewDecisionCreate(
            target_type="relationship",
            target_id=target_id,
            decision="uncertain",
            reviewer_id="reviewer_alice",
            reason="Waiting for plumber report on riser"
        )
    )
    assert d1.decision == "uncertain"
    assert d1.decision_id.startswith("DEC_")

    # Second reviewer decision on same relationship: accept
    d2 = service.submit_decision(
        ReviewDecisionCreate(
            target_type="relationship",
            target_id=target_id,
            decision="accept",
            reviewer_id="reviewer_bob",
            reason="Confirmed shared vertical stack leak on inspection"
        )
    )
    assert d2.decision == "accept"

    # Audit history must preserve BOTH entries
    history = service.get_audit_history(target_id=target_id)
    assert len(history) == 2
    decisions = [h.decision for h in history]
    assert "uncertain" in decisions
    assert "accept" in decisions

def test_csv_export_format(review_db):
    service = ReviewService(review_db)
    service.submit_decision(
        ReviewDecisionCreate(
            target_type="relationship",
            target_id="REL-TEST",
            decision="accept",
            reviewer_id="lead_tech",
            reason="Verified"
        )
    )
    csv_str = service.export_reviews_csv()
    assert "decision_id,target_type,target_id,decision,reviewer_id,reason" in csv_str
    assert "REL-TEST,accept,lead_tech,Verified" in csv_str
