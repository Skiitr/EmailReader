#!/usr/bin/env python3
"""
Offline calibration/evaluation harness for deterministic heuristic triage.

Dataset format (JSONL):
{"email": {...normalized_email...}, "label": "flag|surface|ignore"}
"""
import argparse
import json
from collections import defaultdict

from heuristics import infer_user_email, load_sender_profiles
from rules import triage_email


VALID_LABELS = {"flag", "surface", "ignore"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate heuristic triage against labeled data.")
    parser.add_argument(
        "--dataset",
        default="calibration_dataset.jsonl",
        help="Path to labeled JSONL dataset (default: calibration_dataset.jsonl)",
    )
    return parser.parse_args()


def load_dataset(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            label = row.get("label")
            if label not in VALID_LABELS:
                raise ValueError(f"Invalid label at line {i}: {label}")
            if "email" not in row:
                raise ValueError(f"Missing email object at line {i}")
            rows.append(row)
    return rows


def metrics(confusion: dict[str, dict[str, int]], label: str) -> tuple[float, float]:
    tp = confusion[label][label]
    fp = sum(confusion[p][label] for p in VALID_LABELS if p != label)
    fn = sum(confusion[label][p] for p in VALID_LABELS if p != label)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def main() -> int:
    args = parse_args()
    data = load_dataset(args.dataset)
    if not data:
        print("Dataset is empty.")
        return 1

    sender_profiles = load_sender_profiles()
    inferred_user_email = infer_user_email([row["email"] for row in data])
    if inferred_user_email:
        print(f"Inferred user email for eval: {inferred_user_email}")
    confusion: dict[str, dict[str, int]] = {
        a: defaultdict(int) for a in VALID_LABELS
    }

    for row in data:
        expected = row["label"]
        predicted = triage_email(
            row["email"],
            ai_result=None,
            sender_profiles=sender_profiles,
            user_email=inferred_user_email,
        )["decision"]
        confusion[expected][predicted] += 1

    total = len(data)
    correct = sum(confusion[l][l] for l in VALID_LABELS)
    accuracy = correct / total

    print("Heuristic Evaluation")
    print("=" * 60)
    print(f"Dataset: {args.dataset}")
    print(f"Samples: {total}")
    print(f"Accuracy: {accuracy:.1%}")
    print()
    print("Confusion Matrix (actual -> predicted)")
    print("-" * 60)
    for actual in ("flag", "surface", "ignore"):
        print(
            f"{actual:7} -> "
            f"flag={confusion[actual]['flag']:3d} "
            f"surface={confusion[actual]['surface']:3d} "
            f"ignore={confusion[actual]['ignore']:3d}"
        )
    print()
    print("Per-class Precision/Recall")
    print("-" * 60)
    for label in ("flag", "surface", "ignore"):
        precision, recall = metrics(confusion, label)
        print(f"{label:7} precision={precision:.1%} recall={recall:.1%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
