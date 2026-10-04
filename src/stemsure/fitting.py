"""Randomized Hough circle fitting, ported from frozen plot2_rht.py without labels."""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def circle_votes(points: np.ndarray, seed: np.ndarray, rng: np.random.Generator,
                 n_trials: int, max_radius: float, max_offset: float) -> np.ndarray:
    out = []
    for start in range(0, n_trials, 5000):
        n = min(5000, n_trials - start)
        ix = rng.integers(0, len(points), size=(n, 3))
        p = points[ix]
        a = p[:, 1] - p[:, 0]
        b = p[:, 2] - p[:, 0]
        det = 2 * (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
        good = np.abs(det) > 1e-4
        q = p[good]
        a, b, det = a[good], b[good], det[good]
        u = np.einsum("ij,ij->i", a, a)
        v = np.einsum("ij,ij->i", b, b)
        dx = (u * b[:, 1] - v * a[:, 1]) / det
        dy = (v * a[:, 0] - u * b[:, 0]) / det
        center = q[:, 0] + np.column_stack((dx, dy))
        rad = np.hypot(dx, dy)
        keep = (rad >= .025) & (rad <= max_radius) & (np.linalg.norm(center - seed, axis=1) <= max_offset)
        out.append(np.column_stack((center[keep], rad[keep])))
    return np.concatenate(out) if out else np.empty((0, 3))


def fit_circle(points: np.ndarray, seed: np.ndarray, rng: np.random.Generator,
               trials: int = 20000, crop_radius: float = .45, max_radius: float = .35,
               max_offset: float = .28) -> dict:
    """Preserve the frozen estimator's output and failure thresholds."""
    if len(points) < 80:
        return {"failure": "INSUFFICIENT_SLICE_POINTS", "point_count": len(points)}
    raw_count = len(points)
    if len(points) > 2500:
        points = points[rng.choice(len(points), 2500, replace=False)]
    votes = circle_votes(points, seed, rng, trials, max_radius, max_offset)
    if len(votes) < 30:
        return {"failure": "FIT_FAILED", "point_count": raw_count, "vote_count": len(votes)}
    xyz = np.floor((votes - [seed[0] - max_offset, seed[1] - max_offset, 0]) /
                   [.015, .015, .01]).astype(np.int32)
    _, inverse, counts = np.unique(xyz, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(counts)[-24:][::-1]
    candidates = []
    for i in order:
        model = np.median(votes[inverse == i], axis=0)
        residual = np.abs(np.linalg.norm(points - model[:2], axis=1) - model[2])
        inlier = residual <= .018
        if inlier.sum() < 30:
            continue
        angles = np.mod(np.arctan2(points[inlier, 1] - model[1],
                                   points[inlier, 0] - model[0]), 2*np.pi)
        sectors = np.unique((angles * 24 / (2*np.pi)).astype(int))
        coverage = 15 * len(sectors)
        score = np.log1p(counts[i]) * np.sqrt(inlier.sum()) * (coverage / 360)
        candidates.append((score, model, inlier, int(counts[i])))
    if not candidates:
        return {"failure": "FIT_FAILED", "point_count": raw_count, "vote_count": len(votes)}
    _, model, inlier, vote_support = max(candidates, key=lambda x: x[0])
    opt = least_squares(lambda p: np.linalg.norm(points[inlier] - p[:2], axis=1) - p[2],
                        model, bounds=([-np.inf, -np.inf, .025],
                                       [np.inf, np.inf, max_radius]), max_nfev=200)
    center, rad = opt.x[:2], opt.x[2]
    residual = np.abs(np.linalg.norm(points-center, axis=1)-rad)
    inlier = residual <= .018
    degrees = np.mod(np.degrees(np.arctan2(points[inlier,1]-center[1],
                                           points[inlier,0]-center[0])), 360)
    sectors = np.unique((degrees // 15).astype(int))
    occupancy = 15 * len(sectors)
    gap = np.diff(np.r_[np.sort(degrees), np.sort(degrees)[0]+360]).max() if len(degrees) else 360
    failure = None if occupancy >= 90 else "INSUFFICIENT_ANGULAR_COVERAGE"
    return {"failure": failure, "point_count": raw_count, "vote_count": len(votes),
            "vote_support": vote_support, "inliers": int(inlier.sum()),
            "inlier_ratio": float(inlier.mean()), "center_x_m": float(center[0]),
            "center_y_m": float(center[1]), "dbh_cm": float(200*rad),
            "median_residual_cm": float(100*np.median(residual[inlier])) if inlier.any() else None,
            "occupied_angle_deg": occupancy, "largest_angle_gap_deg": float(gap)}
