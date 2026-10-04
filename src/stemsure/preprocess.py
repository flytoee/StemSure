"""Point-cloud-only ground normalization and breast-height evidence extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import laspy
import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt, gaussian_filter, minimum_filter

HEIGHTS = np.array([.8, 1.1, 1.4, 1.7, 2.0])
GRID_CELL_M = .1
GROUND_CELL_M = .2
HALF_WIDTH_M = .08
MAX_GRID_CELLS = 4_000_000


@dataclass
class Prepared:
    grids: np.ndarray
    edges_x: np.ndarray
    edges_y: np.ndarray
    xyh: np.ndarray
    origin_x: float
    origin_y: float
    ground: np.ndarray | None
    stats: dict


def _dimensions(path: Path) -> tuple[float, float, int, int, int, int]:
    with laspy.open(path) as reader:
        header = reader.header
        mins, maxs = header.mins, header.maxs
        if not np.isfinite(mins).all() or not np.isfinite(maxs).all():
            raise ValueError("Invalid LAS coordinate bounds")
        left_x, left_y = np.floor(mins[:2]).astype(int) - 1
        right_x, right_y = np.ceil(maxs[:2]).astype(int) + 1
        nx, ny = int(right_x - left_x), int(right_y - left_y)
        if nx <= 0 or ny <= 0 or 100 * nx * ny > MAX_GRID_CELLS:
            raise ValueError("Point-cloud extent is too large for the current grid; crop the plot")
        return float(left_x), float(left_y), nx, ny, int(header.point_count), int(header.point_format.id)


def _ground_from_cloud(path: Path, x0: float, y0: float, nx: int, ny: int,
                       ground_class: int | None) -> tuple[np.ndarray, dict]:
    ids, zs = [], []
    ground_points = 0
    with laspy.open(path) as reader:
        for chunk in reader.chunk_iterator(1_000_000):
            take = np.ones(len(chunk), dtype=bool) if ground_class is None else \
                np.asarray(chunk.classification) == ground_class
            n = int(take.sum())
            ground_points += n
            if not n:
                continue
            x = np.asarray(chunk.x)[take]
            y = np.asarray(chunk.y)[take]
            z = np.asarray(chunk.z)[take]
            cx = np.floor((x - x0) / GROUND_CELL_M).astype(np.int32)
            cy = np.floor((y - y0) / GROUND_CELL_M).astype(np.int32)
            valid = (cx >= 0) & (cx < nx * 5) & (cy >= 0) & (cy < ny * 5)
            ids.append(cx[valid] * (ny * 5) + cy[valid])
            zs.append(z[valid].astype(np.float32))
    if ground_points < 100 or not ids:
        raise ValueError(f"Ground class {ground_class} has fewer than 100 points; provide a classified cloud or use --normalized")
    cells = np.concatenate(ids)
    elevations = np.concatenate(zs)
    grouped = pd.DataFrame({"cell": cells, "z": elevations}).groupby("cell", sort=False).z
    levels = grouped.quantile(.05) if ground_class is None else grouped.median()
    surface = np.full((nx * 5, ny * 5), np.nan, dtype=np.float32)
    flat = surface.ravel()
    flat[levels.index.to_numpy(dtype=int)] = levels.to_numpy(np.float32)
    observed = np.isfinite(surface)
    if int(observed.sum()) < 20:
        raise ValueError("Too few independent ground cells for height normalization")
    nearest = distance_transform_edt(~observed, return_distances=False, return_indices=True)
    filled = surface[tuple(nearest)]
    if ground_class is None:
        # Elevated trunk-only cells are replaced by nearby lower terrain evidence.
        ground = gaussian_filter(minimum_filter(filled, size=11), sigma=.75)
    else:
        smooth = gaussian_filter(filled, sigma=.75)
        ground = np.where(observed, .75 * surface + .25 * smooth, smooth)
    return ground, {"ground_class": "all_q05" if ground_class is None else ground_class,
                    "ground_points": ground_points,
                    "observed_ground_cells": int(observed.sum()),
                    "ground_coverage_fraction": float(observed.mean()),
                    "ground_cell_m": GROUND_CELL_M}


def prepare_cloud(path: Path, *, ground_class: int | None = 2,
                  stem_class: int | None = 1, normalized: bool = False,
                  breast_height_m: float = 1.30) -> Prepared:
    """Use no field reference or plot-specific DTM; coordinates stay local until export."""
    if not np.isfinite(breast_height_m) or breast_height_m <= .15:
        raise ValueError("breast_height_m must be finite and greater than 0.15 m")
    low, high = (1.15, 1.45) if breast_height_m == 1.30 else (breast_height_m - .15, breast_height_m + .15)
    x0, y0, nx, ny, header_points, point_format = _dimensions(path)
    ground, ground_stats = (None, {"ground_source": "input_z_is_normalized"}) if normalized else \
        _ground_from_cloud(path, x0, y0, nx, ny, ground_class)
    edges_x = np.linspace(0, nx, nx * 10 + 1)
    edges_y = np.linspace(0, ny, ny * 10 + 1)
    grids = np.zeros((len(HEIGHTS), nx * 10, ny * 10), dtype=np.int32)
    parts = []
    read_points = stem_points = normalized_points = 0
    with laspy.open(path) as reader:
        for chunk in reader.chunk_iterator(1_000_000):
            read_points += len(chunk)
            cls = np.asarray(chunk.classification)
            selection = np.ones(len(chunk), dtype=bool) if stem_class is None else cls == stem_class
            stem_points += int(selection.sum())
            if not selection.any():
                continue
            x = np.asarray(chunk.x)[selection] - x0
            y = np.asarray(chunk.y)[selection] - y0
            z = np.asarray(chunk.z)[selection]
            if normalized:
                height = z
            else:
                cx = np.floor(x / GROUND_CELL_M).astype(int)
                cy = np.floor(y / GROUND_CELL_M).astype(int)
                inside = (cx >= 0) & (cx < ground.shape[0]) & (cy >= 0) & (cy < ground.shape[1])
                if not inside.all():
                    raise ValueError("LAS header extent disagrees with point coordinates")
                height = z - ground[cx, cy]
            valid = np.isfinite(height)
            normalized_points += int(valid.sum())
            x, y, height = x[valid], y[valid], height[valid]
            for i, target in enumerate(HEIGHTS):
                band = np.abs(height - target) < HALF_WIDTH_M
                if band.any():
                    grids[i] += np.histogram2d(x[band], y[band], bins=(edges_x, edges_y))[0].astype(np.int32)
            breast = (height >= low) & (height <= high)
            if breast.any():
                parts.append(np.column_stack((x[breast].astype(np.float32),
                                              y[breast].astype(np.float32),
                                              height[breast].astype(np.float32))))
    if not parts:
        raise ValueError(f"No stem-class points in the {low:.3f}–{high:.3f} m breast-height region")
    xyh = np.concatenate(parts)
    if not grids.any():
        raise ValueError("No points in proposal height bands")
    stats = {"header_points": header_points, "read_points": read_points,
             "point_format": point_format, "stem_class": stem_class if stem_class is not None else "all",
             "stem_class_points": stem_points, "normalized_stem_points": normalized_points,
             "breast_slice_points": len(xyh), "proposal_grid_shape": list(grids.shape),
             "height_mode": "already_normalized" if normalized else "ground_class_surface",
             "origin_xy_m": [x0, y0], **ground_stats}
    return Prepared(grids, edges_x, edges_y, xyh, x0, y0, ground, stats)
