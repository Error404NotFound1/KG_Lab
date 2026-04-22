from collections import Counter
from typing import Dict, Iterable, List, Tuple



def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0



def compute_metrics(y_true: List[List[str]], y_pred: List[List[str]]) -> Dict[str, float]:
    true_set = {tuple(item) for item in y_true}
    pred_set = {tuple(item) for item in y_pred}
    tp = len(true_set & pred_set)
    fp = len(pred_set - true_set)
    fn = len(true_set - pred_set)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }



def compute_entity_metrics(y_true: Iterable[dict], y_pred: Iterable[dict]) -> Dict[str, float]:
    gold = [[item["doc_id"], item["sentence_id"], item["entity"], item["entity_type"]] for item in y_true]
    pred = [[item["doc_id"], item["sentence_id"], item["entity"], item["entity_type"]] for item in y_pred]
    return compute_metrics(gold, pred)



def compute_relation_metrics(y_true: Iterable[dict], y_pred: Iterable[dict]) -> Dict[str, float]:
    gold = [[item["doc_id"], item["sentence_id"], item["head"], item["relation"], item["tail"]] for item in y_true]
    pred = [[item["doc_id"], item["sentence_id"], item["head"], item["relation"], item["tail"]] for item in y_pred]
    return compute_metrics(gold, pred)



def group_metrics_by_type(rows_true: Iterable[dict], rows_pred: Iterable[dict], key: str) -> Dict[str, Dict[str, float]]:
    grouped_true = {}
    grouped_pred = {}
    for row in rows_true:
        grouped_true.setdefault(row[key], []).append(row)
    for row in rows_pred:
        grouped_pred.setdefault(row[key], []).append(row)
    labels = set(grouped_true) | set(grouped_pred)
    results = {}
    for label in labels:
        true_rows = grouped_true.get(label, [])
        pred_rows = grouped_pred.get(label, [])
        if key == "entity_type":
            results[label] = compute_entity_metrics(true_rows, pred_rows)
        else:
            results[label] = compute_relation_metrics(true_rows, pred_rows)
    return results
