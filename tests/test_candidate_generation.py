"""Unit tests for deterministic candidate generation policy."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base
from database.models import Property, Building, Unit, Asset, UnitAssetLink, Incident
from services.candidate_generation import CandidateGenerationEngine

@pytest.fixture
def candidate_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Properties
    p1 = Property(property_id="PROP-A", organization_id="ORG-1", name="Property Alpha")
    p2 = Property(property_id="PROP-B", organization_id="ORG-1", name="Property Beta")
    db.add_all([p1, p2])

    # Buildings
    b1 = Building(building_id="BLDG-A1", property_id="PROP-A", name="Building A1", total_floors=3)
    b2 = Building(building_id="BLDG-B1", property_id="PROP-B", name="Building B1", total_floors=3)
    db.add_all([b1, b2])

    # Units
    u101 = Unit(unit_id="U-101", building_id="BLDG-A1", unit_number="101", floor=1)
    u201 = Unit(unit_id="U-201", building_id="BLDG-A1", unit_number="201", floor=2)
    u_b = Unit(unit_id="U-B1", building_id="BLDG-B1", unit_number="101", floor=1)
    db.add_all([u101, u201, u_b])

    # Asset
    riser = Asset(asset_id="RISER-01", building_id="BLDG-A1", name="Plumbing Stack 01", asset_type="plumbing_riser")
    db.add(riser)

    # Links
    db.add(UnitAssetLink(unit_id="U-101", asset_id="RISER-01"))
    db.add(UnitAssetLink(unit_id="U-201", asset_id="RISER-01"))
    db.commit()

    yield db
    db.close()

def test_hard_scope_filter_blocks_cross_property_matching(candidate_db):
    engine = CandidateGenerationEngine(candidate_db)
    base_time = datetime.datetime(2026, 10, 1, 10, 0, 0)

    # Incident in Property A
    inc_a = Incident(
        incident_id="INC-A",
        property_id="PROP-A",
        building_id="BLDG-A1",
        unit_id="U-101",
        asset_id="RISER-01",
        raw_description="Water dripping from ceiling",
        normalized_category="plumbing",
        created_at=base_time,
        updated_at=base_time
    )
    # Incident in Property B (same exact wording and timestamp)
    inc_b = Incident(
        incident_id="INC-B",
        property_id="PROP-B",
        building_id="BLDG-B1",
        unit_id="U-B1",
        asset_id=None,
        raw_description="Water dripping from ceiling",
        normalized_category="plumbing",
        created_at=base_time,
        updated_at=base_time
    )
    candidate_db.add_all([inc_a, inc_b])
    candidate_db.commit()

    candidates = engine.generate_candidates_for_incident(inc_a)
    assert len(candidates) == 0  # Strictly isolated by property boundary!

def test_shared_infrastructure_channel_retrieval(candidate_db):
    engine = CandidateGenerationEngine(candidate_db)
    base_time = datetime.datetime(2026, 10, 1, 10, 0, 0)

    inc1 = Incident(
        incident_id="INC-1",
        property_id="PROP-A",
        building_id="BLDG-A1",
        unit_id="U-101",
        asset_id="RISER-01",
        raw_description="Water leaking behind wall pipe",
        normalized_category="plumbing",
        created_at=base_time,
        updated_at=base_time
    )
    inc2 = Incident(
        incident_id="INC-2",
        property_id="PROP-A",
        building_id="BLDG-A1",
        unit_id="U-201",
        asset_id="RISER-01",
        raw_description="Damp spot on bathroom ceiling",
        normalized_category="plumbing",
        created_at=base_time + datetime.timedelta(hours=4),
        updated_at=base_time + datetime.timedelta(hours=4)
    )
    candidate_db.add_all([inc1, inc2])
    candidate_db.commit()

    candidates = engine.generate_candidates_for_incident(inc1)
    assert len(candidates) == 1
    cp = candidates[0]
    assert cp.incident_a_id == "INC-1"
    assert cp.incident_b_id == "INC-2"
    assert any("RISER-01" in r for r in cp.generation_reasons)
