"""Reference-free entry that reviews fitted diameters at either numerical limit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from stemsure_guard.cli import class_arg, run as upper_guard_run
from stemsure_run.cli import failure_code

from . import __version__

LOWER_GUARD_CM = 5.01


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_lower_guard(decisions: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = decisions.copy()
    lower = out.dbh_cm.le(LOWER_GUARD_CM)
    newly = lower & out.decision.eq("keep")
    out.loc[newly, "decision"] = "review"
    out.loc[newly, "reason"] = "FIT_RADIUS_MIN_LIMIT_REACHED"
    out.loc[lower, "dbh_status"] = "limit_hit_unreliable"
    out.loc[newly, "review_priority"] = np.nan
    return out, int(newly.sum())


def save_failure(output_dir: Path, input_path: Path, exc: OSError | ValueError,
                 options: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "failure.json"
    if target.exists():
        raise FileExistsError(target)
    record = {"status": "failed", "software_version": __version__,
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "input_path": str(input_path.resolve(strict=False)),
              "reason_code": failure_code(exc), "diagnostic": str(exc),
              "exception_type": type(exc).__name__, "options": options,
              "reference_data_used": False}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def run(input_path: Path, output_dir: Path, *, ground_class: int | None,
        stem_class: int | None, normalized: bool, seed: int, trials: int) -> dict:
    record = upper_guard_run(input_path, output_dir, ground_class=ground_class,
                             stem_class=stem_class, normalized=normalized,
                             seed=seed, trials=trials)
    decisions_path = output_dir / "decisions.csv"
    record_path = output_dir / "run_record.json"
    old_decisions = output_dir / "decisions_upper_guard_v03.csv"
    old_record = output_dir / "run_record_upper_guard_v03.json"
    shutil.copy2(decisions_path, old_decisions)
    shutil.copy2(record_path, old_record)
    revised, count = apply_lower_guard(pd.read_csv(decisions_path))
    revised.to_csv(decisions_path, index=False)
    record["software_version"] = __version__
    record["decision_counts"] = {str(k): int(v) for k, v in
                                  revised.decision.value_counts().items()}
    record["min_radius_safety_guard"] = {
        "fit_limit_cm": 5.0,
        "flag_through_cm": LOWER_GUARD_CM,
        "newly_flagged_for_review": count,
        "reason": "FIT_RADIUS_MIN_LIMIT_REACHED",
        "interpretation": "Constrained numerical DBH at the lower fit limit is not an accepted measurement",
        "previous_guard_decisions_sha256": sha(old_decisions),
        "previous_guard_run_record_sha256": sha(old_record),
        "reference_data_used": False}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(prog="stemsure-checked",
                                     description="Measure LAS/LAZ; review estimates at either fit limit")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--normalized", action="store_true")
    parser.add_argument("--ground-class", type=class_arg, default=2)
    parser.add_argument("--stem-class", type=class_arg, default=1)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--trials", type=int, default=20000)
    args = parser.parse_args()
    input_path, output_dir = Path(args.input), Path(args.output)
    if output_dir.exists():
        parser.exit(2, f"StemSure refused to overwrite existing output directory: {output_dir}\n")
    options = {"normalized": args.normalized,
               "ground_class": "all" if args.ground_class is None else args.ground_class,
               "stem_class": "all" if args.stem_class is None else args.stem_class,
               "seed": args.seed, "trials": args.trials}
    try:
        record = run(input_path, output_dir,
                     ground_class=args.ground_class, stem_class=args.stem_class,
                     normalized=args.normalized, seed=args.seed, trials=args.trials)
    except (OSError, ValueError) as exc:
        try:
            path = save_failure(output_dir, input_path, exc, options)
        except OSError as write_exc:
            parser.exit(2, f"StemSure failed: {exc}; could not write failure.json: {write_exc}\n")
        parser.exit(2, f"StemSure failed [{failure_code(exc)}]; details: {path}\n")
    print(json.dumps({"output": str(output_dir),
                      "candidate_count": record["candidate_count"],
                      "decision_counts": record["decision_counts"],
                      "new_lower_limit_reviews": record["min_radius_safety_guard"]
                      ["newly_flagged_for_review"],
                      "new_upper_limit_reviews": record["max_radius_safety_guard"]
                      ["newly_flagged_for_review"]}, ensure_ascii=False))
