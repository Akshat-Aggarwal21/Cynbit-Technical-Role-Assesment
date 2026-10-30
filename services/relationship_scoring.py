"""Transparent Relationship Scoring Engine for Cross-Unit Incident Intelligence."""
import math
from typing import Dict, List, Tuple, Set, Optional, Any
import datetime
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from database.models import Incident, UnitAssetLink, Unit
from config.scoring_config import scoring_config
from schemas.relationship import IncidentRelationshipSchema
from services.normalization_service import utc_now

class RelationshipScoringEngine:
    """Calculates interpretable review-ranking scores and evidence breakdowns."""

    def __init__(self, db: Session):
        self.db = db
        self.weights = scoring_config.weights
        self.thresholds = scoring_config.thresholds
        self.decay = scoring_config.decay

    def compute_relationship(
        self,
        incident_a: Incident,
        incident_b: Incident,
        rule_version: str = "v1.2.0"
    ) -> IncidentRelationshipSchema:
        """
        Evaluate two incidents and produce a transparent, feature-level relationship score.
        """
        # Ensure canonical ordering min_id < max_id
        if incident_a.incident_id > incident_b.incident_id:
            incident_a, incident_b = incident_b, incident_a

        rel_id = f"REL_{incident_a.incident_id}_{incident_b.incident_id}"

        missing_evidence: List[str] = []
        contradictory_evidence: List[str] = []
        evidence_points: List[str] = []

        # 1. Temporal Factor
        f_temporal, temp_text, temp_available = self._eval_temporal(
            incident_a.created_at, incident_b.created_at, incident_a.normalized_category
        )
        if temp_text:
            evidence_points.append(temp_text)

        # 2. Topology Factor
        f_topology, topo_text, topo_missing, topo_contra = self._eval_topology(incident_a, incident_b)
        if topo_text:
            evidence_points.append(topo_text)
        if topo_missing:
            missing_evidence.extend(topo_missing)
        if topo_contra:
            contradictory_evidence.extend(topo_contra)

        # 3. Shared Asset / Infrastructure Factor
        f_asset, asset_text, asset_missing = self._eval_shared_asset(incident_a, incident_b)
        if asset_text:
            evidence_points.append(asset_text)
        if asset_missing:
            missing_evidence.extend(asset_missing)

        # 4. Category Factor
        f_category, cat_text, cat_contra = self._eval_category(
            incident_a.normalized_category, incident_b.normalized_category
        )
        if cat_text:
            evidence_points.append(cat_text)
        if cat_contra:
            contradictory_evidence.extend(cat_contra)

        # 5. Symptom & Description Similarity
        f_symptoms, sym_text = self._eval_symptoms(incident_a, incident_b)
        if sym_text:
            evidence_points.append(sym_text)

        # Calculate Score
        # score = 100 * sum(w_i * f_i) / sum(w_i for available features)
        factors = {
            "shared_asset": {
                "factor_name": "Shared Infrastructure",
                "weight": self.weights.shared_asset,
                "raw_value": round(f_asset, 3),
                "weighted_value": round(self.weights.shared_asset * f_asset, 3),
                "is_available": True,
                "evidence_text": asset_text or "No shared infrastructure mapped"
            },
            "topology": {
                "factor_name": "Spatial Topology",
                "weight": self.weights.topology,
                "raw_value": round(f_topology, 3),
                "weighted_value": round(self.weights.topology * f_topology, 3),
                "is_available": True,
                "evidence_text": topo_text
            },
            "temporal": {
                "factor_name": "Temporal Proximity",
                "weight": self.weights.temporal,
                "raw_value": round(f_temporal, 3),
                "weighted_value": round(self.weights.temporal * f_temporal, 3),
                "is_available": temp_available,
                "evidence_text": temp_text
            },
            "category": {
                "factor_name": "Issue Category",
                "weight": self.weights.category,
                "raw_value": round(f_category, 3),
                "weighted_value": round(self.weights.category * f_category, 3),
                "is_available": True,
                "evidence_text": cat_text
            },
            "symptoms": {
                "factor_name": "Symptoms & Description",
                "weight": self.weights.symptoms,
                "raw_value": round(f_symptoms, 3),
                "weighted_value": round(self.weights.symptoms * f_symptoms, 3),
                "is_available": True,
                "evidence_text": sym_text
            }
        }

        sum_weighted = sum(item["weighted_value"] for item in factors.values())
        sum_weights = sum(item["weight"] for item in factors.values() if item["is_available"])

        raw_score = (sum_weighted / sum_weights * 100.0) if sum_weights > 0 else 0.0

        # Apply hard contradiction suppression
        if contradictory_evidence:
            # Downgrade score if there are severe contradictions (e.g. cross-building with no link)
            raw_score = raw_score * 0.40

        review_score = round(min(100.0, max(0.0, raw_score)), 1)

        # Determine Recommendation Tier
        if review_score >= self.thresholds.suggest_for_review and not contradictory_evidence:
            recommendation_tier = "suggest_for_review"
        elif review_score >= self.thresholds.low_evidence:
            recommendation_tier = "low_evidence"
        else:
            recommendation_tier = "insufficient_evidence"

        # Evidence Summary Construction
        evidence_summary = self._build_evidence_summary(
            incident_a, incident_b, evidence_points, missing_evidence, contradictory_evidence, review_score
        )

        return IncidentRelationshipSchema(
            relationship_id=rel_id,
            incident_a_id=incident_a.incident_id,
            incident_b_id=incident_b.incident_id,
            review_score=review_score,
            score_factors=factors,
            evidence_summary=evidence_summary,
            missing_evidence=missing_evidence,
            contradictory_evidence=contradictory_evidence,
            recommendation_tier=recommendation_tier,
            rule_version=rule_version,
            created_at=utc_now()
        )

    def _eval_temporal(self, t1: datetime.datetime, t2: datetime.datetime, category: str) -> Tuple[float, str, bool]:
        if t1 is None or t2 is None:
            return 0.0, "Missing timestamp", False
        if t1.tzinfo is not None:
            t1 = t1.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        if t2.tzinfo is not None:
            t2 = t2.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        diff_hours = abs((t1 - t2).total_seconds()) / 3600.0
        scale = getattr(self.decay, f"{category}_hours", self.decay.default_hours)
        # Exponential decay: e^(-dt / scale)
        f_val = math.exp(-diff_hours / scale)
        if diff_hours < 1.0:
            text = f"Reported nearly simultaneously ({diff_hours * 60:.0f} mins apart)"
        elif diff_hours < 24.0:
            text = f"Reported within {diff_hours:.1f} hours ({diff_hours/24:.1f} days)"
        else:
            text = f"Reported {diff_hours / 24.0:.1f} days apart ({diff_hours:.0f} hours)"
        return f_val, text, True

    def _eval_topology(self, inc_a: Incident, inc_b: Incident) -> Tuple[float, str, List[str], List[str]]:
        missing = []
        contra = []

        if not inc_a.property_id or not inc_b.property_id or inc_a.property_id != inc_b.property_id:
            contra.append("Incidents are from different properties or organizations")
            return 0.0, "Cross-property mismatch", missing, contra

        # Check Unit level
        if inc_a.unit_id and inc_b.unit_id:
            if inc_a.unit_id == inc_b.unit_id:
                return 1.0, f"Same unit ({inc_a.unit_id})", missing, contra

            # Check if same building
            if inc_a.building_id and inc_b.building_id and inc_a.building_id == inc_b.building_id:
                u1 = self.db.query(Unit).filter(Unit.unit_id == inc_a.unit_id).first()
                u2 = self.db.query(Unit).filter(Unit.unit_id == inc_b.unit_id).first()
                if u1 and u2 and u1.unit_number and u2.unit_number:
                    # Vertical stack alignment heuristic
                    if len(u1.unit_number) >= 3 and len(u2.unit_number) >= 3:
                        if u1.unit_number[-2:] == u2.unit_number[-2:]:
                            return 0.85, f"Vertical stack co-location (Units {u1.unit_number} & {u2.unit_number} in Bldg {inc_a.building_id})", missing, contra
                return 0.50, f"Same building ({inc_a.building_id}), distinct units", missing, contra
            else:
                contra.append(f"Different buildings ({inc_a.building_id} vs {inc_b.building_id})")
                return 0.10, "Different buildings in same property", missing, contra
        else:
            if not inc_a.unit_id:
                missing.append(f"Unit ID missing for Incident {inc_a.incident_id}")
            if not inc_b.unit_id:
                missing.append(f"Unit ID missing for Incident {inc_b.incident_id}")

            if inc_a.building_id and inc_b.building_id and inc_a.building_id == inc_b.building_id:
                return 0.45, f"Same building ({inc_a.building_id}), unit unassigned", missing, contra
            else:
                return 0.10, "Property-level match without unit assignment", missing, contra

    def _eval_shared_asset(self, inc_a: Incident, inc_b: Incident) -> Tuple[float, Optional[str], List[str]]:
        missing = []
        if inc_a.property_id != inc_b.property_id:
            return 0.0, None, ["Cross-property comparison"]

        assets_a: Set[str] = set()
        assets_b: Set[str] = set()

        if inc_a.asset_id:
            assets_a.add(inc_a.asset_id)
        if inc_b.asset_id:
            assets_b.add(inc_b.asset_id)

        if inc_a.unit_id:
            links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == inc_a.unit_id).all()
            for l in links:
                assets_a.add(l.asset_id)

        if inc_b.unit_id:
            links = self.db.query(UnitAssetLink).filter(UnitAssetLink.unit_id == inc_b.unit_id).all()
            for l in links:
                assets_b.add(l.asset_id)

        common = assets_a & assets_b
        if common:
            asset_names = sorted(list(common))
            return 1.0, f"Mapped to shared building infrastructure: {', '.join(asset_names)}", missing
        
        # Check vertical stack heuristic if units known
        if inc_a.unit_id and inc_b.unit_id and inc_a.building_id == inc_b.building_id:
            u1 = self.db.query(Unit).filter(Unit.unit_id == inc_a.unit_id).first()
            u2 = self.db.query(Unit).filter(Unit.unit_id == inc_b.unit_id).first()
            if u1 and u2 and u1.unit_number and u2.unit_number:
                if len(u1.unit_number) >= 3 and len(u2.unit_number) >= 3 and u1.unit_number[-2:] == u2.unit_number[-2:]:
                    return 0.70, f"Probable shared riser alignment (Units {u1.unit_number} & {u2.unit_number})", missing

        missing.append("No common shared asset or plumbing riser established in system mapping")
        return 0.0, None, missing

    def _eval_category(self, cat_a: str, cat_b: str) -> Tuple[float, str, List[str]]:
        contra = []
        if cat_a == cat_b:
            return 1.0, f"Matching category ({cat_a})", contra
        
        # Compatible cross-categories
        compatible_pairs = [
            ({"plumbing", "water_intrusion"}),
            ({"plumbing", "structural"}),
            ({"water_intrusion", "structural"}),
        ]
        s = {cat_a, cat_b}
        for pair in compatible_pairs:
            if s == pair:
                return 0.65, f"Compatible issue categories ({cat_a} and {cat_b})", contra

        contra.append(f"Divergent issue categories ({cat_a} vs {cat_b})")
        return 0.10, f"Disparate categories ({cat_a} vs {cat_b})", contra

    def _eval_symptoms(self, inc_a: Incident, inc_b: Incident) -> Tuple[float, str]:
        # Jaccard overlap of symptoms
        s1 = set(inc_a.symptoms or [])
        s2 = set(inc_b.symptoms or [])
        jaccard = 0.0
        if s1 and s2:
            jaccard = len(s1 & s2) / len(s1 | s2)

        # Lexical cosine similarity
        text1 = inc_a.raw_description
        text2 = inc_b.raw_description
        cos_sim = 0.0
        try:
            vec = TfidfVectorizer().fit_transform([text1, text2])
            cos_sim = float(cosine_similarity(vec[0:1], vec[1:2])[0][0])
        except Exception:
            cos_sim = 0.0

        score = 0.60 * jaccard + 0.40 * cos_sim
        score = min(1.0, max(0.0, score))

        common_syms = sorted(list(s1 & s2))
        if common_syms:
            text = f"Symptom overlap: {', '.join(common_syms)} (Lexical similarity: {cos_sim:.2f})"
        else:
            text = f"Lexical description similarity: {cos_sim:.2f} (No exact symptom tag overlap)"

        return score, text

    def _build_evidence_summary(
        self,
        inc_a: Incident,
        inc_b: Incident,
        evidence_points: List[str],
        missing: List[str],
        contradictions: List[str],
        score: float
    ) -> str:
        """Constructs an interpretable explanation without unsupported claims."""
        if contradictions:
            return (
                f"Review Score: {score}/100. Disqualified or downgraded due to contradictions: "
                f"{'; '.join(contradictions)}."
            )

        lines = [f"Suggested for review with ranking score of {score}/100 based on the following verified evidence:"]
        for pt in evidence_points:
            lines.append(f"• {pt}")
        if missing:
            lines.append("Missing information:")
            for m in missing:
                lines.append(f"- {m}")

        return "\n".join(lines)
