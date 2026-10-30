"""Data repository layer for CRUD operations with property-scoped access."""
import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from database.models import (
    Property, Building, Unit, Asset, UnitAssetLink,
    Incident, RepairRecord, IncidentRelationship,
    RecurrenceFlag, ReviewDecision
)
from services.normalization_service import utc_now

class PropertyRepository:
    def __init__(self, db: Session):
        self.db = db

    # Topology Methods
    def get_all_properties(self) -> List[Property]:
        return self.db.query(Property).all()

    def get_property(self, property_id: str) -> Optional[Property]:
        return self.db.query(Property).filter(Property.property_id == property_id).first()

    def create_property(self, property_id: str, organization_id: str, name: str, address: Optional[str] = None) -> Property:
        prop = Property(property_id=property_id, organization_id=organization_id, name=name, address=address)
        self.db.add(prop)
        self.db.commit()
        self.db.refresh(prop)
        return prop

    def get_buildings(self, property_id: Optional[str] = None) -> List[Building]:
        query = self.db.query(Building)
        if property_id:
            query = query.filter(Building.property_id == property_id)
        return query.all()

    def create_building(self, building_id: str, property_id: str, name: str, total_floors: int = 1) -> Building:
        bldg = Building(building_id=building_id, property_id=property_id, name=name, total_floors=total_floors)
        self.db.add(bldg)
        self.db.commit()
        self.db.refresh(bldg)
        return bldg

    def get_units(self, building_id: Optional[str] = None) -> List[Unit]:
        query = self.db.query(Unit)
        if building_id:
            query = query.filter(Unit.building_id == building_id)
        return query.all()

    def create_unit(self, unit_id: str, building_id: str, unit_number: str, floor: int = 1) -> Unit:
        unit = Unit(unit_id=unit_id, building_id=building_id, unit_number=unit_number, floor=floor)
        self.db.add(unit)
        self.db.commit()
        self.db.refresh(unit)
        return unit

    def get_assets(self, building_id: Optional[str] = None) -> List[Asset]:
        query = self.db.query(Asset)
        if building_id:
            query = query.filter(Asset.building_id == building_id)
        return query.all()

    def create_asset(self, asset_id: str, building_id: str, name: str, asset_type: str, location_description: Optional[str] = None) -> Asset:
        asset = Asset(asset_id=asset_id, building_id=building_id, name=name, asset_type=asset_type, location_description=location_description)
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def link_unit_to_asset(self, unit_id: str, asset_id: str, connection_type: str = "direct") -> UnitAssetLink:
        existing = self.db.query(UnitAssetLink).filter_by(unit_id=unit_id, asset_id=asset_id).first()
        if existing:
            return existing
        link = UnitAssetLink(unit_id=unit_id, asset_id=asset_id, connection_type=connection_type)
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def get_connected_assets_for_unit(self, unit_id: str) -> List[Asset]:
        links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == unit_id).all()
        return [link.asset for link in links if link.asset]

    def get_units_connected_to_asset(self, asset_id: str) -> List[Unit]:
        links = self.db.query(UnitAssetLink).filter(UnitAssetLink.asset_id == asset_id).all()
        return [link.unit for link in links if link.unit]

    # Incident Methods
    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return self.db.query(Incident).filter(Incident.incident_id == incident_id).first()

    def get_incidents(
        self,
        property_id: Optional[str] = None,
        building_id: Optional[str] = None,
        unit_id: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 500
    ) -> List[Incident]:
        query = self.db.query(Incident)
        if property_id:
            query = query.filter(Incident.property_id == property_id)
        if building_id:
            query = query.filter(Incident.building_id == building_id)
        if unit_id:
            query = query.filter(Incident.unit_id == unit_id)
        if category and category != "All":
            query = query.filter(Incident.normalized_category == category)
        if severity and severity != "All":
            query = query.filter(Incident.severity == severity)
        if status and status != "All":
            query = query.filter(Incident.status == status)
        return query.order_by(desc(Incident.created_at)).limit(limit).all()

    def create_incident(self, incident_data: Dict[str, Any]) -> Incident:
        incident = Incident(**incident_data)
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def update_incident(self, incident_id: str, updates: Dict[str, Any]) -> Optional[Incident]:
        incident = self.get_incident(incident_id)
        if not incident:
            return None
        for key, value in updates.items():
            if hasattr(incident, key):
                setattr(incident, key, value)
        incident.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(incident)
        return incident

    # Repair Records
    def create_repair_record(self, repair_data: Dict[str, Any]) -> RepairRecord:
        repair = RepairRecord(**repair_data)
        self.db.add(repair)
        self.db.commit()
        self.db.refresh(repair)
        return repair

    def get_repair(self, repair_id: str) -> Optional[RepairRecord]:
        return self.db.query(RepairRecord).filter(RepairRecord.repair_id == repair_id).first()

    def get_repairs_for_incident(self, incident_id: str) -> List[RepairRecord]:
        return self.db.query(RepairRecord).filter(RepairRecord.incident_id == incident_id).all()

    def get_all_repairs(self, limit: int = 500) -> List[RepairRecord]:
        return self.db.query(RepairRecord).order_by(desc(RepairRecord.completed_at)).limit(limit).all()

    # Relationship Suggestions
    def upsert_relationship(self, rel_data: Dict[str, Any]) -> IncidentRelationship:
        rel_id = rel_data["relationship_id"]
        existing = self.db.query(IncidentRelationship).filter_by(relationship_id=rel_id).first()
        if existing:
            for k, v in rel_data.items():
                setattr(existing, k, v)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        rel = IncidentRelationship(**rel_data)
        self.db.add(rel)
        self.db.commit()
        self.db.refresh(rel)
        return rel

    def get_relationships_for_incident(self, incident_id: str) -> List[IncidentRelationship]:
        return self.db.query(IncidentRelationship).filter(
            or_(
                IncidentRelationship.incident_a_id == incident_id,
                IncidentRelationship.incident_b_id == incident_id
            )
        ).order_by(desc(IncidentRelationship.review_score)).all()

    def get_all_relationships(self, min_score: float = 0.0, limit: int = 500) -> List[IncidentRelationship]:
        return self.db.query(IncidentRelationship).filter(
            IncidentRelationship.review_score >= min_score
        ).order_by(desc(IncidentRelationship.review_score)).limit(limit).all()

    def get_relationship_by_id(self, relationship_id: str) -> Optional[IncidentRelationship]:
        return self.db.query(IncidentRelationship).filter(IncidentRelationship.relationship_id == relationship_id).first()

    # Recurrence Flags
    def upsert_recurrence_flag(self, flag_data: Dict[str, Any]) -> RecurrenceFlag:
        flag_id = flag_data["flag_id"]
        existing = self.db.query(RecurrenceFlag).filter_by(flag_id=flag_id).first()
        if existing:
            for k, v in flag_data.items():
                setattr(existing, k, v)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        flag = RecurrenceFlag(**flag_data)
        self.db.add(flag)
        self.db.commit()
        self.db.refresh(flag)
        return flag

    def get_all_recurrence_flags(self, limit: int = 500) -> List[RecurrenceFlag]:
        return self.db.query(RecurrenceFlag).order_by(desc(RecurrenceFlag.created_at)).limit(limit).all()

    def get_recurrence_flag_by_id(self, flag_id: str) -> Optional[RecurrenceFlag]:
        return self.db.query(RecurrenceFlag).filter(RecurrenceFlag.flag_id == flag_id).first()

    # Review Decisions (Audit Trail)
    def add_review_decision(self, decision_data: Dict[str, Any]) -> ReviewDecision:
        decision = ReviewDecision(**decision_data)
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def get_review_decisions(self, target_id: Optional[str] = None, limit: int = 500) -> List[ReviewDecision]:
        query = self.db.query(ReviewDecision)
        if target_id:
            query = query.filter(ReviewDecision.target_id == target_id)
        return query.order_by(desc(ReviewDecision.created_at)).limit(limit).all()
