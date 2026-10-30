"""Explanation service for generating grounded natural-language explanations."""
from typing import Dict, Any, List

class ExplanationService:
    """Generates human-readable, grounded explanations for incident relationships and recurrence."""

    @staticmethod
    def explain_relationship(
        incident_a_id: str,
        incident_b_id: str,
        review_score: float,
        recommendation_tier: str,
        score_factors: Dict[str, Any],
        missing_evidence: List[str],
        contradictory_evidence: List[str]
    ) -> str:
        """
        Builds a concise, non-causal review rationale.
        Example: 'These incidents were suggested for review because both were reported in Building A
        within a short time interval, and both reference the same mapped plumbing riser.'
        """
        if contradictory_evidence:
            return (
                f"These incidents were NOT recommended as related (Score: {review_score}/100) "
                f"because contradictory evidence was detected: {'; '.join(contradictory_evidence)}."
            )

        if recommendation_tier == "insufficient_evidence":
            return (
                f"Insufficient evidence to link {incident_a_id} and {incident_b_id} (Score: {review_score}/100). "
                f"Key missing data: {', '.join(missing_evidence) if missing_evidence else 'Weak spatial/temporal correlation'}."
            )

        reasons = []
        shared = score_factors.get("shared_asset", {})
        if shared.get("raw_value", 0) > 0.6:
            reasons.append(shared.get("evidence_text", "shared infrastructure link"))

        topo = score_factors.get("topology", {})
        if topo.get("raw_value", 0) > 0.4:
            reasons.append(topo.get("evidence_text", "spatial co-location"))

        temporal = score_factors.get("temporal", {})
        if temporal.get("raw_value", 0) > 0.5:
            reasons.append(temporal.get("evidence_text", "short time window"))

        sym = score_factors.get("symptoms", {})
        if sym.get("raw_value", 0) > 0.3:
            reasons.append(sym.get("evidence_text", "overlapping symptoms"))

        summary_text = (
            f"These incidents were suggested for review (Ranking Score: {review_score}/100) because "
            + "; ".join(reasons) + "."
        )
        if missing_evidence:
            summary_text += f" (Note: Missing {'; '.join(missing_evidence)})"

        return summary_text

    @staticmethod
    def explain_recurrence(
        new_incident_id: str,
        prior_incident_id: str,
        repair_id: str,
        days_since_repair: float,
        repair_action: str,
        symptom_overlap: List[str]
    ) -> str:
        """
        Generates a carefully worded recurrence explanation.
        Never concludes that the repair failed; flags for verification.
        """
        symptom_str = f"with similar symptoms ({', '.join(symptom_overlap)})" if symptom_overlap else "with matching issue category"
        return (
            f"Possible recurrence flagged for human verification: Incident {new_incident_id} was reported "
            f"{days_since_repair:.1f} days after Repair {repair_id} was marked complete for previous incident {prior_incident_id} "
            f"('{repair_action}'). The new complaint describes {symptom_str}. Requires on-site verification."
        )
