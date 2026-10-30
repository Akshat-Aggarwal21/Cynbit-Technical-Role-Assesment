"""Unit tests for repair recurrence verification."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base
from database.models import Property, Building, Unit, Incident, RepairRecord
from services.recurrence_detection import RecurrenceDetectionService

@pytest.fixture
def recurrence_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    prop = Property(property_id="PROP-REC", organization_id="ORG-1", name="Recurrence Test Prop")
    bldg = Building(building_id="BLDG-REC", property_id="PROP-REC", name="Building 1", total_floors=2)
    unit = Unit(unit_id="UNIT-101", building_id="BLDG-REC", unit_number="101", floor=1)
    db.add_all([prop, bldg, unit])
    db.commit()

    yield db
    db.close()

def test_detect_recurrence_within_window(recurrence_db):
    service = RecurrenceDetectionService(recurrence_db)
    base_time = datetime.datetime(2026, 10, 1, 10, 0, 0)

    # 1. First incident
    inc1 = Incident(
        incident_id="INC-OLD",
        property_id="PROP-REC",
        building_id="BLDG-REC",
        unit_id="UNIT-101",
        raw_description="Bathroom faucet pipe leaking onto vanity base",
        normalized_category="plumbing",
        symptoms=["water_leakage"],
        created_at=base_time,
        updated_at=base_time,
        status="closed"
    )
    recurrence_db.add(inc1)
    recurrence_db.commit()

    # 2. Repair completed 2 days later
    repair = RepairRecord(
        repair_id="REP-001",
        incident_id="INC-OLD",
        completed_at=base_time + datetime.timedelta(days=2),
        action_taken="Replaced faucet compression washer and tested seals.",
        outcome="completed"
    )
    recurrence_db.add(repair)
    recurrence_db.commit()

    # 3. New incident reported 8 days after repair (within 30-day plumbing window)
    inc2 = Incident(
        incident_id="INC-NEW",
        property_id="PROP-REC",
        building_id="BLDG-REC",
        unit_id="UNIT-101",
        raw_description="Bathroom faucet pipe leaking again; puddle forming",
        normalized_category="plumbing",
        symptoms=["water_leakage"],
        created_at=base_time + datetime.timedelta(days=10),
        updated_at=base_time + datetime.timedelta(days=10),
        status="open"
    )
    recurrence_db.add(inc2)
    recurrence_db.commit()

    flags = service.check_incident_for_recurrence(inc2)
    assert len(flags) == 1
    flag = flags[0]
    assert flag.new_incident_id == "INC-NEW"
    assert flag.prior_incident_id == "INC-OLD"
    assert flag.repair_id == "REP-001"
    assert flag.days_since_repair == 8.0
    # Must use careful non-causal language
    assert "Possible recurrence" in flag.evidence_summary
    assert "Requires" in flag.evidence_summary
    assert "failed" not in flag.evidence_summary.lower()

def test_no_recurrence_outside_window(recurrence_db):
    service = RecurrenceDetectionService(recurrence_db)
    base_time = datetime.datetime(2026, 10, 1, 10, 0, 0)

    inc1 = Incident(
        incident_id="INC-ANCIENT",
        property_id="PROP-REC",
        building_id="BLDG-REC",
        unit_id="UNIT-101",
        raw_description="Bathroom faucet leaking",
        normalized_category="plumbing",
        created_at=base_time,
        updated_at=base_time,
        status="closed"
    )
    repair = RepairRecord(
        repair_id="REP-ANCIENT",
        incident_id="INC-ANCIENT",
        completed_at=base_time + datetime.timedelta(days=1),
        action_taken="Replaced washer",
        outcome="completed"
    )
    # New incident reported 90 days later (exceeds 30-day window)
    inc2 = Incident(
        incident_id="INC-MUCH-LATER",
        property_id="PROP-REC",
        building_id="BLDG-REC",
        unit_id="UNIT-101",
        raw_description="Bathroom faucet leaking",
        normalized_category="plumbing",
        created_at=base_time + datetime.timedelta(days=91),
        updated_at=base_time + datetime.timedelta(days=91),
        status="open"
    )
    recurrence_db.add_all([inc1, repair, inc2])
    recurrence_db.commit()

    flags = service.check_incident_for_recurrence(inc2)
    assert len(flags) == 0
