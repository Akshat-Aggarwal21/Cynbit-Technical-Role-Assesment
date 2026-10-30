"""Run reproducible evaluation comparing:
1. Baseline Model (Same-Building + 72h Window)
2. Rules-First Property Intelligence Engine (Topology + Symptom Overlap + Decay)
3. Recurrence Detection Verification
"""
import json
from pathlib import Path
from typing import Dict, Any, Set, Tuple
from database.connection import SessionLocal
from database.models import Incident, RepairRecord, RecurrenceFlag
from services.candidate_generation import CandidateGenerationEngine
from services.relationship_scoring import RelationshipScoringEngine
from services.recurrence_detection import RecurrenceDetectionService
from evaluation.evaluation_metrics import EvaluationMetricsCalculator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def run_full_evaluation() -> Dict[str, Any]:
    db = SessionLocal()

    # Load ground truth pairs
    gt_rel_path = DATA_DIR / "ground_truth_relationships.json"
    gt_rec_path = DATA_DIR / "ground_truth_recurrence.json"

    ground_truth_relationships: Set[Tuple[str, str]] = set()
    if gt_rel_path.exists():
        with open(gt_rel_path, "r") as f:
            raw_gt = json.load(f)
            ground_truth_relationships = {tuple(sorted(pair)) for pair in raw_gt}

    ground_truth_recurrences: Set[Tuple[str, str]] = set()
    if gt_rec_path.exists():
        with open(gt_rec_path, "r") as f:
            raw_rec = json.load(f)
            ground_truth_recurrences = {tuple(pair) for pair in raw_rec}

    all_incidents = db.query(Incident).all()
    incident_map = {inc.incident_id: inc for inc in all_incidents}

    # 1. Run Baseline Model
    baseline_results = EvaluationMetricsCalculator.run_baseline_evaluation(
        incidents=all_incidents,
        ground_truth_pairs=ground_truth_relationships,
        time_window_hours=72.0
    )

    # 2. Run Proposed Intelligence Engine
    cand_engine = CandidateGenerationEngine(db)
    scoring_engine = RelationshipScoringEngine(db)

    all_candidate_pairs = cand_engine.generate_all_candidates()

    proposed_predicted: Set[Tuple[str, str]] = set()
    all_scored_relationships = []

    for cp in all_candidate_pairs:
        inc_a = incident_map.get(cp.incident_a_id)
        inc_b = incident_map.get(cp.incident_b_id)
        if not inc_a or not inc_b:
            continue

        assessment = scoring_engine.compute_relationship(inc_a, inc_b)
        all_scored_relationships.append(assessment)

        # Threshold for positive prediction
        if assessment.review_score >= 50.0 and assessment.recommendation_tier == "suggest_for_review":
            pair = tuple(sorted([cp.incident_a_id, cp.incident_b_id]))
            proposed_predicted.add(pair)

    proposed_results = EvaluationMetricsCalculator.calculate_classification_metrics(
        predicted_pairs=proposed_predicted,
        ground_truth_pairs=ground_truth_relationships
    )

    # 3. Run Recurrence Detection Verification
    rec_service = RecurrenceDetectionService(db)
    flagged_recurrences = rec_service.scan_all_for_recurrence()

    predicted_recurrence_pairs = {
        (rf.new_incident_id, rf.prior_incident_id) for rf in flagged_recurrences
    }

    tp_rec = predicted_recurrence_pairs & ground_truth_recurrences
    fp_rec = predicted_recurrence_pairs - ground_truth_recurrences
    fn_rec = ground_truth_recurrences - predicted_recurrence_pairs

    rec_precision = len(tp_rec) / (len(tp_rec) + len(fp_rec)) if (tp_rec or fp_rec) else 0.0
    rec_recall = len(tp_rec) / (len(tp_rec) + len(fn_rec)) if (tp_rec or fn_rec) else 0.0
    rec_f1 = (2 * rec_precision * rec_recall) / (rec_precision + rec_recall) if (rec_precision + rec_recall) > 0 else 0.0

    recurrence_results = {
        "true_positives": len(tp_rec),
        "false_positives": len(fp_rec),
        "false_negatives": len(fn_rec),
        "precision": round(rec_precision, 4),
        "recall": round(rec_recall, 4),
        "f1_score": round(rec_f1, 4),
        "flagged_count": len(flagged_recurrences),
        "tp_examples": sorted(list(tp_rec)),
        "fp_examples": sorted(list(fp_rec)),
        "fn_examples": sorted(list(fn_rec))
    }

    summary = {
        "baseline_model": baseline_results,
        "proposed_engine": proposed_results,
        "recurrence_detection": recurrence_results,
        "ground_truth_rel_count": len(ground_truth_relationships),
        "ground_truth_rec_count": len(ground_truth_recurrences),
        "total_evaluated_incidents": len(all_incidents)
    }

    db.close()
    return summary

if __name__ == "__main__":
    res = run_full_evaluation()
    print("================ EVALUATION BENCHMARK RESULTS ================")
    print("1. Baseline Model (Same Building + 72h Window):")
    print(f"   Precision: {res['baseline_model']['precision']:.4f} | Recall: {res['baseline_model']['recall']:.4f} | F1: {res['baseline_model']['f1_score']:.4f}")
    print(f"   TP: {res['baseline_model']['true_positives']} | FP: {res['baseline_model']['false_positives']} | FN: {res['baseline_model']['false_negatives']}")
    print("\n2. TenantEase Property Intelligence Engine (Rules + Topology + Decay):")
    print(f"   Precision: {res['proposed_engine']['precision']:.4f} | Recall: {res['proposed_engine']['recall']:.4f} | F1: {res['proposed_engine']['f1_score']:.4f}")
    print(f"   TP: {res['proposed_engine']['true_positives']} | FP: {res['proposed_engine']['false_positives']} | FN: {res['proposed_engine']['false_negatives']}")
    print("\n3. Recurrence Detection Verification:")
    print(f"   Precision: {res['recurrence_detection']['precision']:.4f} | Recall: {res['recurrence_detection']['recall']:.4f} | F1: {res['recurrence_detection']['f1_score']:.4f}")
    print(f"   TP: {res['recurrence_detection']['true_positives']} | FP: {res['recurrence_detection']['false_positives']} | FN: {res['recurrence_detection']['false_negatives']}")
    print("==============================================================")
