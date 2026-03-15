"""
evaluate.py — Benchmark evaluation against ground truth
Input:  behavior_timeline_smoke.json (NDJSON from smoke test)
Output: evaluation_report.json + console summary

Compares analyzer output against the known 2-min benchmark clip (minute 15-17).
Ground truth: 40 behavioral windows (3s each) with known distribution.
"""

import json
import os
import sys
from collections import Counter

TIMELINE_PATH = "behavior_timeline_smoke.json"
EVAL_OUTPUT_PATH = "evaluation_report.json"

# Ground truth from benchmark validation (docs/claude_takeover_instructions.md)
GROUND_TRUTH = {
    "exploration": 13,
    "aiming": 11,
    "reviving": 6,
    "combat": 4,
    "death_event": 2,
    "looting": 2,
    "hi_intensity_combat": 1,
    "vehicle_traversal": 1,
}
GROUND_TRUTH_TOTAL = sum(GROUND_TRUTH.values())  # 40

# Map state_names to match ground truth keys
NAME_MAP = {
    "high_intensity_combat": "hi_intensity_combat",
}

# Window size for aggregation (3s windows to match reference project)
WINDOW_SIZE_S = 3.0


def load_timeline(path: str) -> list:
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def aggregate_to_windows(events: list, window_s: float = WINDOW_SIZE_S) -> list:
    """Aggregate per-frame events into fixed-size windows.
    Each window's behavior = majority vote of events within that window.
    """
    if not events:
        return []

    t_min = events[0]["t"]
    t_max = events[-1]["t"]
    windows = []

    t = t_min
    while t < t_max:
        window_end = t + window_s
        window_events = [e for e in events if t <= e["t"] < window_end]
        if window_events:
            # Majority vote
            votes = Counter(e["state_name"] for e in window_events)
            behavior = votes.most_common(1)[0][0]
            windows.append({
                "t_start": round(t, 1),
                "t_end": round(window_end, 1),
                "behavior": behavior,
                "votes": dict(votes),
                "n_events": len(window_events),
            })
        t += window_s

    return windows


def evaluate(windows: list) -> dict:
    """Compare window distribution against ground truth."""
    predicted = Counter()
    for w in windows:
        name = w["behavior"]
        name = NAME_MAP.get(name, name)
        predicted[name] += 1

    total_predicted = sum(predicted.values())

    # Per-class comparison
    all_classes = sorted(set(list(GROUND_TRUTH.keys()) + list(predicted.keys())))
    per_class = {}
    for cls in all_classes:
        gt = GROUND_TRUTH.get(cls, 0)
        pred = predicted.get(cls, 0)
        diff = pred - gt
        per_class[cls] = {
            "ground_truth": gt,
            "predicted": pred,
            "diff": diff,
            "match": "exact" if diff == 0 else ("over" if diff > 0 else "under"),
        }

    # Revive recall analysis
    revive_gt = GROUND_TRUTH.get("reviving", 0)
    revive_pred = predicted.get("reviving", 0)
    revive_recall = revive_pred / revive_gt if revive_gt > 0 else 0.0

    return {
        "total_windows_predicted": total_predicted,
        "total_windows_ground_truth": GROUND_TRUTH_TOTAL,
        "per_class": per_class,
        "predicted_distribution": dict(predicted),
        "revive_recall": round(revive_recall, 3),
        "revive_analysis": {
            "ground_truth": revive_gt,
            "predicted": revive_pred,
            "recall": round(revive_recall, 3),
            "note": (
                "Revive detection depends on OCR sampling interval. "
                "v0.2 reduced OCR interval from 15s to 5s for better recall."
            ),
        },
    }


def main():
    if not os.path.exists(TIMELINE_PATH):
        print(f"ERROR: {TIMELINE_PATH} not found. Run: python analyzer.py --smoke")
        sys.exit(1)

    print(f"==> Evaluating {TIMELINE_PATH} against benchmark ground truth")

    events = load_timeline(TIMELINE_PATH)
    if not events:
        print("ERROR: No events found in timeline.")
        sys.exit(1)

    print(f"    Loaded {len(events)} events, t=[{events[0]['t']:.1f}, {events[-1]['t']:.1f}]s")

    windows = aggregate_to_windows(events)
    print(f"    Aggregated to {len(windows)} windows ({WINDOW_SIZE_S}s each)")

    result = evaluate(windows)

    # Console summary
    print(f"\n{'='*60}")
    print(f"  BENCHMARK EVALUATION — {result['total_windows_predicted']} predicted vs {GROUND_TRUTH_TOTAL} ground truth")
    print(f"{'='*60}")
    print(f"\n  {'Class':<24s} {'GT':>4s} {'Pred':>4s} {'Diff':>5s}  Status")
    print(f"  {'-'*50}")
    for cls, info in sorted(result["per_class"].items(), key=lambda x: -x[1]["ground_truth"]):
        gt = info["ground_truth"]
        pred = info["predicted"]
        diff = info["diff"]
        status = "OK" if diff == 0 else (f"+{diff}" if diff > 0 else str(diff))
        marker = " " if diff == 0 else "*"
        print(f"  {cls:<24s} {gt:4d} {pred:4d} {diff:+5d}  {status}{marker}")

    print(f"\n  Revive recall: {result['revive_recall']:.0%} ({result['revive_analysis']['predicted']}/{result['revive_analysis']['ground_truth']})")
    print(f"  {result['revive_analysis']['note']}")

    # Save
    with open(EVAL_OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n==> Saved {EVAL_OUTPUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        TIMELINE_PATH = sys.argv[1]
    main()
