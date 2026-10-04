"""Reference-free DBH entry that returns decisions or a reasoned failure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

import pandas as pd

from stemsure_guard.cli import apply_guard, class_arg
from stemsure_checked.cli import apply_lower_guard
from stemsure_run.cli import failure_code

from . import __version__
from .pipeline import _measure_into
from .execution import output_session, write_json


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(input_path: Path, output_dir: Path, *, ground_class: int | None = 2,
        stem_class: int | None = 1, normalized: bool = False,
        seed: int = 20260927, trials: int = 20000,
        breast_height_m: float = 1.30) -> dict:
    options = dict(ground_class="all" if ground_class is None else ground_class,
                   stem_class="all" if stem_class is None else stem_class,
                   normalized=normalized, seed=seed, trials=trials,
                   breast_height_m=breast_height_m)
    started = time.monotonic()
    with output_session(output_dir, input_path, options) as owned:
        report = _run_into(Path(input_path), owned, ground_class=ground_class,
                           stem_class=stem_class, normalized=normalized,
                           seed=seed, trials=trials, breast_height_m=breast_height_m)
        report["runtime_including_guards_seconds"] = round(time.monotonic() - started, 3)
        write_json(owned / "run_record.json", report)
        return report


def _run_into(input_path: Path, output_dir: Path, *, ground_class: int | None,
        stem_class: int | None, normalized: bool, seed: int, trials: int,
        breast_height_m: float = 1.30) -> dict:
    record = _measure_into(input_path, output_dir, ground_class=ground_class,
                     stem_class=stem_class, normalized=normalized, seed=seed,
                     trials=trials, breast_height_m=breast_height_m)
    decisions_path = output_dir / "decisions.csv"
    record_path = output_dir / "run_record.json"
    core_decisions = output_dir / "decisions_core_v05.csv"
    core_record = output_dir / "run_record_core_v05.json"
    shutil.copy2(decisions_path, core_decisions)
    shutil.copy2(record_path, core_record)
    upper, upper_count = apply_guard(pd.read_csv(decisions_path))
    upper_path = output_dir / "decisions_upper_v05.csv"
    upper.to_csv(upper_path, index=False)
    lower, lower_count = apply_lower_guard(upper)
    lower.to_csv(decisions_path, index=False)
    record["software_version"] = __version__
    record["base_software_version"] = __version__
    record["decision_counts"] = {str(k): int(v) for k, v in lower.decision.value_counts().items()}
    record["max_radius_safety_guard"] = {
        "fit_limit_cm": 70.0, "flag_from_cm": 69.95,
        "newly_flagged_for_review": upper_count,
        "reason": "FIT_RADIUS_LIMIT_REACHED", "reference_data_used": False}
    record["min_radius_safety_guard"] = {
        "fit_limit_cm": 5.0, "flag_through_cm": 5.01,
        "newly_flagged_for_review": lower_count,
        "reason": "FIT_RADIUS_MIN_LIMIT_REACHED", "reference_data_used": False}
    record["fit_schema_repair"] = {
        "all_candidate_fit_failed_heights": [int(h) for h, counts in
            record["fit_failure_counts_by_height"].items() if counts.get("SUCCESS", 0) == 0],
        "interpretation": "Missing success-only fit columns are NaN; original failed fits keep their failure codes",
        "core_decisions_sha256": sha(core_decisions),
        "core_record_sha256": sha(core_record),
        "upper_decisions_sha256": sha(upper_path)}
    write_json(record_path, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(prog="stemsure-reliable",
                                     description="Measure point-cloud DBH with explicit review and failure reasons")
    parser.add_argument("--version", action="version", version=f"StemSure {__version__}")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--normalized", action="store_true")
    parser.add_argument("--ground-class", type=class_arg, default=2)
    parser.add_argument("--stem-class", type=class_arg, default=1)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--trials", type=int, default=20000)
    parser.add_argument("--breast-height", type=float, default=1.30,
                        help="Central measurement height above ground in meters (default: 1.30)")
    args = parser.parse_args()
    input_path, output_dir = Path(args.input), Path(args.output)
    if output_dir.exists():
        parser.exit(2, f"StemSure refused to overwrite existing output directory: {output_dir}\n")
    try:
        record = run(input_path, output_dir, ground_class=args.ground_class,
                     stem_class=args.stem_class, normalized=args.normalized,
                     seed=args.seed, trials=args.trials, breast_height_m=args.breast_height)
    except Exception as exc:
        path = getattr(exc, "stemsure_failure_path", None)
        detail = f"; details: {path}" if path else ""
        record_error = getattr(exc, "stemsure_failure_record_error", None)
        if record_error:
            detail += f"; could not write failure record: {record_error}"
        code = failure_code(exc) if isinstance(exc, (OSError, ValueError)) else "INTERNAL_PROCESSING_ERROR"
        parser.exit(2, f"StemSure failed [{code}]: {exc}{detail}\n")
    print(json.dumps({"output": str(output_dir),
                      "candidate_count": record["candidate_count"],
                      "decision_counts": record["decision_counts"],
                      "all_candidate_fit_failed_heights": record["fit_schema_repair"]
                      ["all_candidate_fit_failed_heights"]}, ensure_ascii=False))
