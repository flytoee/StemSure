"""Inference path: proposal, circle fitting, and review decisions without labels."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.spatial import cKDTree

from . import __version__
from .decisions import THRESHOLD_CM, make_decisions
from .fitting import fit_circle
from .preprocess import HEIGHTS, Prepared, prepare_cloud

RNG_SEED = 20260927


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def proposals(prepared: Prepared, peak_size: int = 9,
              score_quantile: float = .95) -> tuple[np.ndarray, np.ndarray]:
    score = np.sqrt(np.maximum(1, gaussian_filter(prepared.grids.astype(float),
                                                  sigma=(0, 1.5, 1.5)))).mean(axis=0)
    peaks = (score == maximum_filter(score, size=peak_size)) & (score > np.quantile(score, score_quantile))
    ix = np.argwhere(peaks)
    xy = np.column_stack((prepared.edges_x[ix[:, 0]] + .05,
                          prepared.edges_y[ix[:, 1]] + .05))
    if len(xy) == 0:
        raise ValueError("NO_CANDIDATE: no proposal grid peak passed the threshold")
    return xy, score[peaks]


def fit_candidates(prepared: Prepared, *, trials: int = 20000,
                   crop_radius: float = .45, max_radius: float = .35,
                   max_center_offset: float = .28,
                   seed: int = RNG_SEED) -> tuple[dict[int, pd.DataFrame], pd.DataFrame]:
    xy, scores = proposals(prepared)
    outputs = {}
    for height, low, high in ((120, 1.15, 1.25), (130, 1.25, 1.35), (140, 1.35, 1.45)):
        points = prepared.xyh[(prepared.xyh[:, 2] >= low) &
                              (prepared.xyh[:, 2] <= high), :2].astype(float)
        tree = cKDTree(points) if len(points) else None
        rng = np.random.default_rng(seed)
        rows = []
        for i, center in enumerate(xy):
            subset = points[tree.query_ball_point(center, crop_radius)] if tree is not None else np.empty((0, 2))
            fit = fit_circle(subset, center, rng, trials, crop_radius,
                             max_radius, max_center_offset)
            if "center_x_m" in fit:
                fit["center_x_m"] += prepared.origin_x
                fit["center_y_m"] += prepared.origin_y
            rows.append({"candidate_id": i,
                         "proposal_x_m": center[0] + prepared.origin_x,
                         "proposal_y_m": center[1] + prepared.origin_y,
                         "proposal_score": scores[i], **fit})
        outputs[height] = pd.DataFrame(rows)
    decisions = make_decisions(outputs)
    return outputs, decisions


def measure(input_path: Path, output_dir: Path, *, ground_class: int | None = 2,
            stem_class: int | None = 1, normalized: bool = False,
            seed: int = RNG_SEED, trials: int = 20000) -> dict:
    input_path = input_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    if not input_path.is_file():
        raise ValueError("Input must be a LAS or LAZ file")
    if input_path.suffix.lower() not in (".las", ".laz"):
        raise ValueError("Input must end in .las or .laz")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    if trials <= 0:
        raise ValueError("--trials must be positive")
    started_at_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    prepared = prepare_cloud(input_path, ground_class=ground_class,
                             stem_class=stem_class, normalized=normalized)
    candidates, decisions = fit_candidates(prepared, seed=seed, trials=trials)
    output_dir.mkdir(parents=True)
    np.savez_compressed(output_dir / "proposal_grids.npz", gr=prepared.grids,
                        edges_x=prepared.edges_x, edges_y=prepared.edges_y, hs=HEIGHTS)
    if prepared.ground is not None:
        np.savez_compressed(output_dir / "ground_surface.npz", ground=prepared.ground,
                            origin_x=prepared.origin_x, origin_y=prepared.origin_y, cell=.2)
    for height, table in candidates.items():
        table.to_csv(output_dir / f"candidates_h{height}.csv", index=False)
    decisions.to_csv(output_dir / "decisions.csv", index=False)
    report = {
        "status": "completed", "software_version": __version__,
        "started_at_utc": started_at_utc,
        "runtime_seconds": round(time.monotonic() - started, 3),
        "input_path": str(input_path), "input_sha256": sha256(input_path),
        "python_version": platform.python_version(),
        "ground_class": None if normalized else ("all_q05" if ground_class is None else ground_class),
        "stem_class": "all" if stem_class is None else stem_class,
        "normalized_input": normalized, "rng_seed": seed, "trials_per_candidate_per_height": trials,
        "crop_radius_m": .45, "max_circle_radius_m": .35,
        "max_center_offset_m": .28, "fixed_height_range_threshold_cm": THRESHOLD_CM,
        "preprocessing": prepared.stats,
        "candidate_count": len(decisions),
        "decision_counts": {k: int(v) for k, v in decisions.decision.value_counts().items()},
        "fit_failure_counts_by_height": {
            str(h): {k: int(v) for k, v in table.failure.fillna("SUCCESS").value_counts().items()}
            for h, table in candidates.items()},
        "reference_data_used": False,
        "scope": "Candidate measurements and review recommendations; no automatic tree identity verification",
    }
    (output_dir / "run_record.json").write_text(json.dumps(report, ensure_ascii=False,
                                                        indent=2) + "\n", encoding="utf-8")
    return report
