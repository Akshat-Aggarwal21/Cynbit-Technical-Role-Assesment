"""Unit tests for transparent relationship scoring and evidence extraction."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base
from database.models import Property, Building, Unit, Asset, UnitAssetLink, Incident
from services.relationship_scoring import RelationshipScoringEngine

@pytest.fixture
def scoring_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    prop = Property(property_id="PROP-1", organization_id="ORG-1", name="Oakridge")
    bldg = Building(building_id="BLDG-1", property_id="PROP-1", name="Tower A", total_floors=3)
    u101 = Unit(unit_id="U-101", building_id="BLDG-1", unit_number="101", floor=1)
    u201 = Unit(unit_id="U-201", building_id="BLDG-1", unit_number="201", floor=2)
    riser = Asset(asset_id="RISER-01", building_id="BLDG-1", name="Riser 1", asset_type="plumbing_riser")
    
    db.add_all([prop, bldg, u101, u201, riser])
    db.add(UnitAssetLink(unit_id="U-101", asset_id="RISER-01"))
    db.add(UnitAssetLink(unit_id="U-201", asset_id="RISER-01"))
    db.commit()

    yield db
    db.close()

def test_relationship_scoring_factor_transparency(scoring_db):
    engine = RelationshipScoringEngine(scoring_db)
    now = datetime.datetime.utcnow()

    inc_a = Incident(
        incident_id="INC-101",
        property_id="PROP-1",
        building_id="BLDG-1",
        unit_id="U-101",
        asset_id="RISER-01",
        raw_description="Water dripping from bathroom ceiling seam",
        normalized_category="plumbing",
        symptoms=["water_dripping", "water_leakage"],
        created_at=now,
        updated_at=now
    )
    inc_b = Incident(
        incident_id="INC-201",
        property_id="PROP-1",
        building_id="BLDG-1",
        unit_id="U-201",
        asset_id="RISER-01",
        raw_description="Bathroom floor water leak spreading from wall seam",
        normalized_category="plumbing",
        symptoms=["water_leakage"],
        created_at=now + datetime.timedelta(hours=2),
        updated_at=now + datetime.timedelta(hours=2)
    )

    assessment = engine.compute_relationship(inc_a, inc_b)
    
    # Assert score is bounded and interpretable review score
    assert 0.0 <= assessment.review_score <= 100.0
    assert assessment.review_score >= 60.0  # Shared riser + close time + plumbing category
    assert assessment.recommendation_tier == "suggest_for_review"

    # Verify transparent factors
    factors = assessment.score_factors
    assert "shared_asset" in factors
    assert factors["shared_asset"]["raw_value"] == 1.0
    assert "RISER-01" in factors["shared_asset"]["evidence_text"]
    assert factors["category"]["raw_value"] == 1.0
    assert factors["temporal"]["raw_value"] >= 0.85

def test_contradictory_evidence_downgrades_score(scoring_db):
    engine = RelationshipScoringEngine(scoring_db)
    now = datetime.datetime.utcnow()

    # Create second building in same property
    b2 = Building(building_id="BLDG-2", property_id="PROP-1", name="Tower B", total_floors=3)
    u_diff = Unit(unit_id="U-DIFF", building_id="BLDG-2", unit_number="101", floor=1)
    scoring_db.add_all([b2, u_diff])
    scoring_db.commit()

    inc_a = Incident(
        incident_id="INC-A",
        property_id="PROP-1",
        building_id="BLDG-1",
        unit_id="U-101",
        asset_id=None,
        raw_description="Water pipe dripping",
        normalized_category="plumbing",
        symptoms=["water_dripping"],
        created_at=now,
        updated_at=now
    )
    inc_b = Incident(
        incident_id="INC-B",
        property_id="PROP-1",
        building_id="BLDG-2",
        unit_id="U-DIFF",
        asset_id=None,
        raw_description="Electrical breaker tripping",
        normalized_category="electrical",
        symptoms=["electrical_trip"],
        created_at=now,
        updated_at=now
    )

    assessment = engine.compute_relationship(inc_a, inc_b)
    assert len(assessment.contradictory_evidence) > 0
    assert assessment.recommendation_tier in ["low_evidence", "insufficient_evidence"]
    assert assessment.review_score < 40.0
