"""Ingestion service for CSV parsing, record validation, and database insertion."""
import io
import csv
import datetime
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
from pydantic import ValidationError
from sqlalchemy.orm import Session
from database.models import Incident
from schemas.incident import IncidentInput, IngestionErrorRecord, NormalizedIncident
from services.normalization_service import NormalizationService, utc_now
from services.duplicate_detection import DuplicateDetectionService

class IngestionResult:
    def __init__(self):
        self.total_rows: int = 0
        self.successful_count: int = 0
        self.duplicate_count: int = 0
        self.errors: List[IngestionErrorRecord] = []
        self.imported_ids: List[str] = []

class IngestionService:
    """Handles structured validation, normalization, and ingestion of maintenance records."""

    def __init__(self, db: Session):
        self.db = db
        self.dup_service = DuplicateDetectionService(db)

    def ingest_csv(self, file_content: str, source_reference: str = "csv_upload") -> IngestionResult:
        """Parse, validate, and ingest maintenance incidents from CSV string."""
        result = IngestionResult()
        
        # Read with pandas or csv
        try:
            df = pd.read_csv(io.StringIO(file_content))
        except Exception as e:
            result.errors.append(
                IngestionErrorRecord(
                    row_index=0,
                    raw_data={},
                    error_message=f"Malformed CSV file format: {str(e)}",
                    error_fields=["file"]
                )
            )
            return result

        result.total_rows = len(df)

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            # Clean NaN to None
            clean_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
            
            # Map common alternate header names
            mapped = self._map_row_fields(clean_dict, source_reference)
            
            try:
                # 1. Validate with Pydantic
                incident_input = IncidentInput(**mapped)
                
                # 2. Normalize category and symptoms
                norm_category = NormalizationService.normalize_category(
                    incident_input.normalized_category or "unknown",
                    incident_input.raw_description
                )
                extracted_symptoms = NormalizationService.extract_symptoms(incident_input.raw_description)
                
                # 3. Check for duplicates
                is_dup, orig_id, dup_conf, _ = self.dup_service.check_duplicate(
                    property_id=incident_input.property_id,
                    unit_id=incident_input.unit_id,
                    created_at=incident_input.created_at,
                    raw_description=incident_input.raw_description
                )

                # 4. Check if incident ID already exists in DB
                existing_inc = self.db.query(Incident).filter_by(incident_id=incident_input.incident_id).first()
                if existing_inc:
                    result.errors.append(
                        IngestionErrorRecord(
                            row_index=int(idx) + 1,
                            raw_data=clean_dict,
                            error_message=f"Incident ID '{incident_input.incident_id}' already exists in database.",
                            error_fields=["incident_id"]
                        )
                    )
                    continue

                # 5. Insert Incident
                db_incident = Incident(
                    incident_id=incident_input.incident_id,
                    property_id=incident_input.property_id,
                    building_id=incident_input.building_id,
                    unit_id=incident_input.unit_id,
                    asset_id=incident_input.asset_id,
                    raw_description=incident_input.raw_description,
                    normalized_category=norm_category,
                    symptoms=extracted_symptoms,
                    severity=incident_input.severity,
                    status=incident_input.status,
                    created_at=incident_input.created_at,
                    updated_at=utc_now(),
                    source_reference=incident_input.source_reference,
                    is_duplicate_of=orig_id if is_dup else None,
                    duplicate_confidence=dup_conf if is_dup else None,
                    is_synthetic=True
                )
                self.db.add(db_incident)
                self.db.commit()

                if is_dup:
                    result.duplicate_count += 1
                result.successful_count += 1
                result.imported_ids.append(incident_input.incident_id)

            except ValidationError as ve:
                err_fields = [str(err["loc"][0]) for err in ve.errors() if "loc" in err and len(err["loc"]) > 0]
                msg = "; ".join([f"{e.get('loc', [''])[0]}: {e.get('msg', '')}" for e in ve.errors()])
                result.errors.append(
                    IngestionErrorRecord(
                        row_index=int(idx) + 1,
                        raw_data=clean_dict,
                        error_message=msg,
                        error_fields=err_fields
                    )
                )
            except Exception as ex:
                self.db.rollback()
                result.errors.append(
                    IngestionErrorRecord(
                        row_index=int(idx) + 1,
                        raw_data=clean_dict,
                        error_message=f"Database or processing error: {str(ex)}",
                        error_fields=["general"]
                    )
                )

        return result

    def ingest_single_incident(self, data: Dict[str, Any]) -> Tuple[bool, Optional[Incident], Optional[str]]:
        """Validate and ingest a single manual incident from form submission."""
        try:
            incident_input = IncidentInput(**data)
            
            norm_category = NormalizationService.normalize_category(
                incident_input.normalized_category or "unknown",
                incident_input.raw_description
            )
            extracted_symptoms = NormalizationService.extract_symptoms(incident_input.raw_description)

            # Duplicate check
            is_dup, orig_id, dup_conf, dup_reason = self.dup_service.check_duplicate(
                property_id=incident_input.property_id,
                unit_id=incident_input.unit_id,
                created_at=incident_input.created_at,
                raw_description=incident_input.raw_description
            )

            # Check if ID exists
            existing = self.db.query(Incident).filter_by(incident_id=incident_input.incident_id).first()
            if existing:
                return False, None, f"Incident ID '{incident_input.incident_id}' already exists."

            db_incident = Incident(
                incident_id=incident_input.incident_id,
                property_id=incident_input.property_id,
                building_id=incident_input.building_id,
                unit_id=incident_input.unit_id,
                asset_id=incident_input.asset_id,
                raw_description=incident_input.raw_description,
                normalized_category=norm_category,
                symptoms=extracted_symptoms,
                severity=incident_input.severity,
                status=incident_input.status,
                created_at=incident_input.created_at,
                updated_at=utc_now(),
                source_reference="manual_entry",
                is_duplicate_of=orig_id if is_dup else None,
                duplicate_confidence=dup_conf if is_dup else None,
                is_synthetic=False
            )
            self.db.add(db_incident)
            self.db.commit()
            self.db.refresh(db_incident)
            return True, db_incident, None

        except ValidationError as ve:
            msg = "; ".join([f"{e.get('loc', [''])[0]}: {e.get('msg', '')}" for e in ve.errors()])
            return False, None, msg
        except Exception as e:
            self.db.rollback()
            return False, None, str(e)

    def _map_row_fields(self, row: dict, source_reference: str) -> dict:
        """Standardize incoming dictionary keys."""
        out = {
            "incident_id": str(row.get("incident_id") or row.get("id") or ""),
            "property_id": str(row.get("property_id") or row.get("property") or ""),
            "building_id": str(row.get("building_id") or row.get("building") or "") or None,
            "unit_id": str(row.get("unit_id") or row.get("unit") or "") or None,
            "asset_id": str(row.get("asset_id") or row.get("asset") or "") or None,
            "raw_description": str(row.get("raw_description") or row.get("description") or ""),
            "normalized_category": str(row.get("normalized_category") or row.get("category") or "unknown"),
            "severity": str(row.get("severity") or "medium"),
            "status": str(row.get("status") or "open"),
            "source_reference": source_reference
        }
        
        # Parse timestamp safely
        ts_val = row.get("created_at") or row.get("date") or row.get("timestamp")
        if ts_val:
            try:
                out["created_at"] = NormalizationService.normalize_timestamp(ts_val)
            except Exception:
                out["created_at"] = ts_val  # Let Pydantic raise validation error
        else:
            out["created_at"] = None

        return out
