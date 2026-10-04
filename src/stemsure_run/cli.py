"""Point-cloud-only CLI that records ordinary input and processing failures."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from stemsure_guard.cli import class_arg, run as guarded_measure

from . import __version__


def failure_code(exc: OSError | ValueError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "INPUT_NOT_FOUND"
    message = str(exc)
    if message.startswith("Input must"):
        return "UNSUPPORTED_INPUT_FORMAT"
    if message.startswith("Ground class") and "fewer than 100 points" in message:
        return "GROUND_CLASS_INSUFFICIENT"
    if message.startswith("Too few independent ground cells"):
        return "GROUND_CELLS_INSUFFICIENT"
    if message.startswith("No stem-class points in the"):
        return "BREAST_HEIGHT_POINTS_ABSENT"
    if message.startswith("No points in proposal height bands"):
        return "PROPOSAL_HEIGHT_POINTS_ABSENT"
    if message.startswith("NO_CANDIDATE"):
        return "NO_CANDIDATE"
    if message.startswith("Point-cloud extent is too large"):
        return "POINT_CLOUD_EXTENT_TOO_LARGE"
    if message.startswith("Invalid LAS coordinate bounds") or \
       message.startswith("LAS header extent disagrees"):
        return "INPUT_HEADER_INVALID"
    return "PROCESSING_ERROR"


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
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(prog="stemsure-run",
                                     description="Measure LAS/LAZ, recommend review, and record failures")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--normalized", action="store_true")
    parser.add_argument("--ground-class", type=class_arg, default=2)
    parser.add_argument("--stem-class", type=class_arg, default=1)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--trials", type=int, default=20000)
    args = parser.parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output)
    if output_dir.exists():
        parser.exit(2, f"StemSure refused to overwrite existing output directory: {output_dir}\n")
    options = {"normalized": args.normalized,
               "ground_class": "all" if args.ground_class is None else args.ground_class,
               "stem_class": "all" if args.stem_class is None else args.stem_class,
               "seed": args.seed, "trials": args.trials}
    try:
        record = guarded_measure(input_path, output_dir,
                                 ground_class=args.ground_class,
                                 stem_class=args.stem_class,
                                 normalized=args.normalized,
                                 seed=args.seed, trials=args.trials)
    except (OSError, ValueError) as exc:
        try:
            path = save_failure(output_dir, input_path, exc, options)
        except OSError as write_exc:
            parser.exit(2, f"StemSure failed: {exc}; could not write failure.json: {write_exc}\n")
        parser.exit(2, f"StemSure failed [{failure_code(exc)}]; details: {path}\n")
    print(json.dumps({"output": str(output_dir),
                      "candidate_count": record["candidate_count"],
                      "decision_counts": record["decision_counts"],
                      "new_radius_limit_reviews": record["max_radius_safety_guard"]["newly_flagged_for_review"]},
                     ensure_ascii=False))
