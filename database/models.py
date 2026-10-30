import datetime
from sqlalchemy import Column, String, Integer, Float, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database.connection import Base

def utc_now():
    """Return naive UTC timestamp to satisfy SQLite/PostgreSQL cleanly without deprecation warnings."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

class Property(Base):
    __tablename__ = "properties"

    property_id = Column(String(64), primary_key=True, index=True)
    organization_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    address = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    buildings = relationship("Building", back_populates="property", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="property")


class Building(Base):
    __tablename__ = "buildings"

    building_id = Column(String(64), primary_key=True, index=True)
    property_id = Column(String(64), ForeignKey("properties.property_id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    total_floors = Column(Integer, default=1)
    created_at = Column(DateTime, default=utc_now)

    property = relationship("Property", back_populates="buildings")
    units = relationship("Unit", back_populates="building", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="building", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="building")


class Unit(Base):
    __tablename__ = "units"

    unit_id = Column(String(64), primary_key=True, index=True)
    building_id = Column(String(64), ForeignKey("buildings.building_id"), nullable=False, index=True)
    unit_number = Column(String(32), nullable=False)
    floor = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now)

    building = relationship("Building", back_populates="units")
    incidents = relationship("Incident", back_populates="unit")
    asset_links = relationship("UnitAssetLink", back_populates="unit", cascade="all, delete-orphan")


class Asset(Base):
    """Shared infrastructure, risers, loops, etc."""
    __tablename__ = "assets"

    asset_id = Column(String(64), primary_key=True, index=True)
    building_id = Column(String(64), ForeignKey("buildings.building_id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    asset_type = Column(String(64), nullable=False)  # plumbing_riser, hvac_loop, roof_drainage, etc.
    location_description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    building = relationship("Building", back_populates="assets")
    incidents = relationship("Incident", back_populates="asset")
    unit_links = relationship("UnitAssetLink", back_populates="asset", cascade="all, delete-orphan")


class UnitAssetLink(Base):
    """Mapping units to shared assets/systems (e.g., units on riser A)."""
    __tablename__ = "unit_asset_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(String(64), ForeignKey("units.unit_id"), nullable=False, index=True)
    asset_id = Column(String(64), ForeignKey("assets.asset_id"), nullable=False, index=True)
    connection_type = Column(String(64), default="direct")

    unit = relationship("Unit", back_populates="asset_links")
    asset = relationship("Asset", back_populates="unit_links")


class Incident(Base):
    __tablename__ = "incidents"

    incident_id = Column(String(64), primary_key=True, index=True)
    property_id = Column(String(64), ForeignKey("properties.property_id"), nullable=False, index=True)
    building_id = Column(String(64), ForeignKey("buildings.building_id"), nullable=True, index=True)
    unit_id = Column(String(64), ForeignKey("units.unit_id"), nullable=True, index=True)
    asset_id = Column(String(64), ForeignKey("assets.asset_id"), nullable=True, index=True)
    
    raw_description = Column(Text, nullable=False)
    normalized_category = Column(String(64), nullable=False, index=True)
    symptoms = Column(JSON, default=list)  # list of strings
    severity = Column(String(32), default="medium")  # low, medium, high, critical
    status = Column(String(32), default="open")  # open, in_progress, repaired, closed
    
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime, nullable=True)
    
    source_reference = Column(String(128), nullable=True)
    is_duplicate_of = Column(String(64), nullable=True)
    duplicate_confidence = Column(Float, nullable=True)
    is_synthetic = Column(Boolean, default=True)

    property = relationship("Property", back_populates="incidents")
    building = relationship("Building", back_populates="incidents")
    unit = relationship("Unit", back_populates="incidents")
    asset = relationship("Asset", back_populates="incidents")
    repairs = relationship("RepairRecord", back_populates="incident", cascade="all, delete-orphan")


class RepairRecord(Base):
    __tablename__ = "repair_records"

    repair_id = Column(String(64), primary_key=True, index=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=False, index=True)
    action_taken = Column(Text, nullable=False)
    outcome = Column(String(64), default="completed")  # completed, temporary_fix, partially_resolved
    technician_notes = Column(Text, nullable=True)
    vendor_name = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    incident = relationship("Incident", back_populates="repairs")
    recurrence_flags = relationship("RecurrenceFlag", back_populates="prior_repair")


class IncidentRelationship(Base):
    """Candidate relationship between two incidents."""
    __tablename__ = "incident_relationships"

    relationship_id = Column(String(128), primary_key=True, index=True)
    incident_a_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    incident_b_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    
    review_score = Column(Float, nullable=False)  # 0.0 to 100.0 review-ranking score
    score_factors = Column(JSON, default=dict)  # factor breakdown dictionary
    evidence_summary = Column(Text, nullable=False)
    missing_evidence = Column(JSON, default=list)
    contradictory_evidence = Column(JSON, default=list)
    recommendation_tier = Column(String(32), default="suggest_for_review")
    rule_version = Column(String(32), default="v1.0")
    created_at = Column(DateTime, default=utc_now)


class RecurrenceFlag(Base):
    """Flags for incidents appearing after completed repairs."""
    __tablename__ = "recurrence_flags"

    flag_id = Column(String(64), primary_key=True, index=True)
    new_incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    prior_incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    repair_id = Column(String(64), ForeignKey("repair_records.repair_id"), nullable=False, index=True)
    
    days_since_repair = Column(Float, nullable=False)
    recurrence_window_days = Column(Integer, nullable=False)
    similarity_score = Column(Float, nullable=False)
    evidence_summary = Column(Text, nullable=False)
    status = Column(String(32), default="flagged")  # flagged, accepted, rejected, uncertain
    created_at = Column(DateTime, default=utc_now)

    prior_repair = relationship("RepairRecord", back_populates="recurrence_flags")


class ReviewDecision(Base):
    """Audit trail of human reviewer decisions."""
    __tablename__ = "review_decisions"

    decision_id = Column(String(64), primary_key=True, index=True)
    target_type = Column(String(32), nullable=False)  # relationship or recurrence
    target_id = Column(String(128), nullable=False, index=True)
    decision = Column(String(32), nullable=False)  # accept, reject, uncertain
    reviewer_id = Column(String(64), nullable=False, default="maintenance_coordinator")
    reason = Column(Text, nullable=True)
    rule_version = Column(String(32), default="v1.0")
    created_at = Column(DateTime, default=utc_now)
