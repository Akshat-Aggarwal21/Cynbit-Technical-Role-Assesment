"""Evaluation metrics module for comparing baseline vs proposed intelligence engine."""
from typing import List, Tuple, Set, Dict, Any, Optional
import json
from pathlib import Path

class EvaluationMetricsCalculator:
    """Calculates Pairwise Precision, Recall, F1, Recurrence metrics, and baseline comparisons."""

    @staticmethod
    def calculate_classification_metrics(
        predicted_pairs: Set[Tuple[str, str]],
        ground_truth_pairs: Set[Tuple[str, str]],
        evaluated_universe_pairs: Optional[Set[Tuple[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Calculate precision, recall, F1, and error breakdown.
        Pairs are represented as canonically sorted tuples: (min_id, max_id).
        """
        tp_set = predicted_pairs & ground_truth_pairs
        fp_set = predicted_pairs - ground_truth_pairs
        fn_set = ground_truth_pairs - predicted_pairs

        tp = len(tp_set)
        fp = len(fp_set)
        fn = len(fn_set)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        tn = 0
        if evaluated_universe_pairs:
            tn = len(evaluated_universe_pairs - predicted_pairs - ground_truth_pairs)

        return {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "tp_examples": sorted(list(tp_set)),
            "fp_examples": sorted(list(fp_set)),
            "fn_examples": sorted(list(fn_set))
        }

    @staticmethod
    def run_baseline_evaluation(
        incidents: list,
        ground_truth_pairs: Set[Tuple[str, str]],
        time_window_hours: float = 72.0
    ) -> Dict[str, Any]:
        """
        Simple baseline: Predicts as related any two incidents in the SAME BUILDING
        reported within 72 hours of each other, without topology or symptom analysis.
        """
        baseline_predicted: Set[Tuple[str, str]] = set()

        for i in range(len(incidents)):
            for j in range(i + 1, len(incidents)):
                inc_a = incidents[i]
                inc_b = incidents[j]

                # Same building check
                if inc_a.building_id and inc_b.building_id and inc_a.building_id == inc_b.building_id:
                    diff_hours = abs((inc_a.created_at - inc_b.created_at).total_seconds()) / 3600.0
                    if diff_hours <= time_window_hours:
                        pair = tuple(sorted([inc_a.incident_id, inc_b.incident_id]))
                        baseline_predicted.add(pair)

        return EvaluationMetricsCalculator.calculate_classification_metrics(
            baseline_predicted, ground_truth_pairs
        )
