"""Reference-free fixed keep/review/reject decision from three fitted heights."""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESHOLD_CM = 2.303410785193904


def make_decisions(candidates: dict[int, pd.DataFrame], threshold_cm: float = THRESHOLD_CM) -> pd.DataFrame:
    parts = []
    for height in (120, 130, 140):
        d = candidates[height].set_index("candidate_id")
        cols = ["dbh_cm", "failure", "vote_support"]
        if height == 130:
            cols += ["proposal_x_m", "proposal_y_m", "proposal_score",
                     "occupied_angle_deg", "inlier_ratio", "median_residual_cm"]
        # Every candidate can fail at one height. Success-only columns then
        # disappear from that entire table; absent measurements remain NaN.
        parts.append(d.reindex(columns=cols).add_suffix(f"_{height}"))
    out = pd.concat(parts, axis=1)
    diameter = out[[f"dbh_cm_{h}" for h in (120, 130, 140)]]
    out["height_range_cm"] = diameter.max(axis=1) - diameter.min(axis=1)
    fit_ok = out.failure_130.isna()
    flank_ok = out.failure_120.isna() & out.failure_140.isna()
    out["decision"] = np.select(
        [~fit_ok, fit_ok & ~flank_ok, fit_ok & flank_ok & (out.height_range_cm <= threshold_cm)],
        ["reject", "review", "keep"], default="review")
    out["reason"] = np.select(
        [~fit_ok, fit_ok & ~flank_ok, out.decision.eq("keep")],
        ["BREAST_HEIGHT_FIT_FAILED", "ADJACENT_SLICE_FAILED", "STABLE_HEIGHT_EVIDENCE"],
        default="HEIGHT_DIAMETER_DISAGREEMENT")
    out["fit_failure_120"] = out.failure_120
    out["fit_failure_130"] = out.failure_130
    out["fit_failure_140"] = out.failure_140
    out = out.reset_index().rename(columns={"dbh_cm_130": "dbh_cm",
                                            "proposal_x_m_130": "x_m", "proposal_y_m_130": "y_m"})
    columns = ["candidate_id", "x_m", "y_m", "dbh_cm", "decision", "reason",
               "fit_failure_120", "fit_failure_130", "fit_failure_140", "height_range_cm",
               "proposal_score_130", "vote_support_130", "occupied_angle_deg_130",
               "inlier_ratio_130", "median_residual_cm_130"]
    out = out[columns]
    out["review_priority"] = np.where(out.decision.eq("keep"), out.dbh_cm, np.nan)
    return out
