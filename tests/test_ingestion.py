"""Unit and integration tests for data ingestion, schema validation, and duplicate handling."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base
from database.models import Property, Building, Unit, Incident
from services.ingestion_service import IngestionService

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Seed a basic property & building
    prop = Property(property_id="PROP-TEST", organization_id="ORG-TEST", name="Test Property")
    bldg = Building(building_id="BLDG-TEST-1", property_id="PROP-TEST", name="Tower 1", total_floors=3)
    unit = Unit(unit_id="UNIT-TEST-101", building_id="BLDG-TEST-1", unit_number="101", floor=1)
    db.add_all([prop, bldg, unit])
    db.commit()
    
    yield db
    db.close()

def test_ingest_valid_csv(test_db):
    service = IngestionService(test_db)
    csv_content = """incident_id,property_id,building_id,unit_id,created_at,raw_description,normalized_category,severity,status
INC-T-01,PROP-TEST,BLDG-TEST-1,UNIT-TEST-101,2026-10-01 10:00:00,Water dripping steadily from ceiling seam,plumbing,high,open
INC-T-02,PROP-TEST,BLDG-TEST-1,UNIT-TEST-101,2026-10-01 12:00:00,Bathroom sink drainage is blocked,plumbing,medium,open
"""
    result = service.ingest_csv(csv_content, source_reference="test_csv")
    assert result.total_rows == 2
    assert result.successful_count == 2
    assert len(result.errors) == 0

    inc1 = test_db.query(Incident).filter_by(incident_id="INC-T-01").first()
    assert inc1 is not None
    assert inc1.normalized_category == "plumbing"
    assert "water_dripping" in inc1.symptoms or "water_leakage" in inc1.symptoms

def test_ingest_validation_failure_accumulates_errors(test_db):
    service = IngestionService(test_db)
    # Row 1 is invalid (missing raw_description), Row 2 is valid
    csv_content = """incident_id,property_id,created_at,raw_description
INC-BAD-01,PROP-TEST,2026-10-01 10:00:00,
INC-GOOD-02,PROP-TEST,2026-10-01 11:00:00,Valid description of electrical flicker
"""
    result = service.ingest_csv(csv_content)
    assert result.total_rows == 2
    assert result.successful_count == 1
    assert len(result.errors) == 1
    assert result.errors[0].row_index == 1
    assert "raw_description" in result.errors[0].error_fields

def test_duplicate_flagging_without_silent_deletion(test_db):
    service = IngestionService(test_db)
    # Ingest original record
    res1, inc1, err1 = service.ingest_single_incident({
        "incident_id": "INC-ORIG",
        "property_id": "PROP-TEST",
        "building_id": "BLDG-TEST-1",
        "unit_id": "UNIT-TEST-101",
        "created_at": "2026-10-01 09:00:00",
        "raw_description": "Water pipe under kitchen sink leaking onto hardwood cabinet."
    })
    assert res1 is True
    assert inc1.is_duplicate_of is None

    # Ingest duplicate report 15 minutes later
    res2, inc2, err2 = service.ingest_single_incident({
        "incident_id": "INC-DUP",
        "property_id": "PROP-TEST",
        "building_id": "BLDG-TEST-1",
        "unit_id": "UNIT-TEST-101",
        "created_at": "2026-10-01 09:15:00",
        "raw_description": "Water pipe under kitchen sink leaking onto hardwood cabinet."
    })
    assert res2 is True
    assert inc2 is not None
    assert inc2.is_duplicate_of == "INC-ORIG"
    assert inc2.duplicate_confidence >= 0.90
