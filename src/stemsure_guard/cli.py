"""Point-cloud-only CLI with a review flag at the fixed circle-fit limit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from stemsure.pipeline import measure

from . import __version__


FIT_LIMIT_CM = 70.0
GUARD_START_CM = 69.95


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_guard(decisions: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = decisions.copy()
    saturated = out.dbh_cm.ge(GUARD_START_CM)
    newly_flagged = saturated & out.decision.eq("keep")
    out.loc[newly_flagged, "decision"] = "review"
    out.loc[newly_flagged, "reason"] = "FIT_RADIUS_LIMIT_REACHED"
    out["dbh_status"] = np.select(
        [out.dbh_cm.isna(), saturated], ["fit_failed", "limit_hit_unreliable"],
        default="measured")
    out.loc[newly_flagged, "review_priority"] = np.nan
    return out, int(newly_flagged.sum())


def run(input_path: Path, output_dir: Path, *, ground_class: int | None,
        stem_class: int | None, normalized: bool, seed: int, trials: int) -> dict:
    core = measure(input_path, output_dir, ground_class=ground_class,
                   stem_class=stem_class, normalized=normalized, seed=seed, trials=trials)
    decisions_path = output_dir / "decisions.csv"
    record_path = output_dir / "run_record.json"
    core_decisions = output_dir / "decisions_core_v02.csv"
    core_record = output_dir / "run_record_core_v02.json"
    shutil.copy2(decisions_path, core_decisions)
    shutil.copy2(record_path, core_record)
    revised, count = apply_guard(pd.read_csv(decisions_path))
    revised.to_csv(decisions_path, index=False)
    core["software_version"] = __version__
    core["base_software_version"] = "0.2.0"
    core["decision_counts"] = {str(k): int(v) for k, v in revised.decision.value_counts().items()}
    core["max_radius_safety_guard"] = {
        "fit_limit_cm": FIT_LIMIT_CM,
        "flag_from_cm": GUARD_START_CM,
        "newly_flagged_for_review": count,
        "reason": "FIT_RADIUS_LIMIT_REACHED",
        "interpretation": "Constrained numerical DBH at the fit limit is not an accepted measurement",
        "base_decisions_sha256": sha(core_decisions),
        "base_run_record_sha256": sha(core_record),
        "reference_data_used": False,
    }
    record_path.write_text(json.dumps(core, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return core


def class_arg(raw: str) -> int | None:
    if raw == "all":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("class must be an integer or all") from exc


def main() -> None:
    parser = argparse.ArgumentParser(prog="stemsure-guard",
                                     description="Measure LAS/LAZ and flag radius-limit estimates for review")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--normalized", action="store_true")
    parser.add_argument("--ground-class", type=class_arg, default=2)
    parser.add_argument("--stem-class", type=class_arg, default=1)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--trials", type=int, default=20000)
    args = parser.parse_args()
    try:
        record = run(Path(args.input), Path(args.output), ground_class=args.ground_class,
                     stem_class=args.stem_class, normalized=args.normalized,
                     seed=args.seed, trials=args.trials)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"StemSure guard failed: {exc}\n")
    print(json.dumps({"output": args.output, "candidate_count": record["candidate_count"],
                      "decision_counts": record["decision_counts"],
                      "new_radius_limit_reviews": record["max_radius_safety_guard"]["newly_flagged_for_review"]},
                     ensure_ascii=False))
