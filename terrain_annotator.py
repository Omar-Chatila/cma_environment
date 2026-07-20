from copy import deepcopy
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
import re
from typing import Any
import warnings

import movingpandas as mpd

from .crs import bbox_utm, grid_shape_from_bbox, traj_utm, utm_to_grid
from .landcover import (
    _add_utm_columns,
    land_water_classes,
    landcover_classes,
    landcover_to_discrete_txt,
    sample_raster_at_points,
    fetch_landcover_data,
)
from .ocean_cover import fetch_ocean_cover_tif, marine_cover_path


_LAND_WATER_VALUE_MAP = {0: 80, 1: 10, 255: 80}


@dataclass(frozen=True)
class _EnvironmentFiles:
    raster: Path
    grid: Path


def _safe_identifier(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._") or "trajectory"


def _lonlat_bounds(trajectory):
    df = trajectory.df
    if df.crs is None:
        raise ValueError("Trajectory data frame must have a CRS")
    return tuple(float(value) for value in df.to_crs("EPSG:4326").total_bounds)


def _remap_land_water_grid(path: Path) -> None:
    rows = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            values = (
                str(_LAND_WATER_VALUE_MAP.get(int(value), int(value)))
                for value in line.split()
            )
            rows.append(" ".join(values))
    with path.open("w", encoding="utf-8") as target:
        target.write("\n".join(rows) + ("\n" if rows else ""))


def _prepare_environment_data(
    trajectories: mpd.TrajectoryCollection,
    *,
    is_long_range: bool,
    resolution: int,
    output_directory: str | Path | None,
) -> dict[Any, _EnvironmentFiles]:
    if not isinstance(resolution, Integral) or isinstance(resolution, bool) or resolution < 1:
        raise ValueError("resolution must be a positive integer")
    resolution = int(resolution)

    root = (
        Path("landcover")
        if output_directory is None
        else Path(output_directory) / "landcover"
    )
    root.mkdir(exist_ok=True, parents=True)
    shapefile_path = marine_cover_path()

    results = {}
    for trajectory in trajectories.trajectories:
        trajectory_id = trajectory.id
        min_lon, min_lat, max_lon, max_lat = _lonlat_bounds(trajectory)
        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        pad_lon = max(0.1 * lon_span, 1e-4)
        pad_lat = max(0.1 * lat_span, 1e-4)
        coverage_bbox = (
            min_lon - pad_lon,
            min_lat - pad_lat,
            max_lon + pad_lon,
            max_lat + pad_lat,
        )
        projected_bbox, _ = bbox_utm(trajectory)
        nx, ny = grid_shape_from_bbox(projected_bbox, resolution)

        projected = traj_utm(trajectory)
        gx, gy = utm_to_grid(
            nx,
            ny,
            projected_bbox,
            projected.df.geometry.x.to_numpy(),
            projected.df.geometry.y.to_numpy(),
        )
        trajectory.df["grid_x"] = gx
        trajectory.df["grid_y"] = gy

        cover_kind = "land_water" if is_long_range else "landcover"
        base_name = (
            f"{cover_kind}_{_safe_identifier(trajectory_id)}_"
            f"{min_lon:.2f}_{min_lat:.2f}_{max_lon:.2f}_{max_lat:.2f}"
        )
        raster_path = root / f"{base_name}.tif"
        grid_path = root / f"{base_name}_{resolution}.txt"

        if not raster_path.exists():
            if is_long_range:
                coverage_lon_span = coverage_bbox[2] - coverage_bbox[0]
                coverage_lat_span = coverage_bbox[3] - coverage_bbox[1]
                resolution_deg = (
                    max(coverage_lon_span, coverage_lat_span, 0.01)
                    / max(resolution, 2)
                )
                fetch_ocean_cover_tif(
                    str(shapefile_path),
                    coverage_bbox,
                    str(raster_path),
                    resolution_deg=resolution_deg,
                )
            else:
                fetched = fetch_landcover_data(
                    coverage_bbox,
                    str(raster_path),
                )
                if fetched is None:
                    raise RuntimeError(
                        f"Could not fetch landcover for trajectory {trajectory_id!r}"
                    )

        converted = landcover_to_discrete_txt(
            str(raster_path),
            res_x=nx,
            res_y=ny,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            output=str(grid_path),
        )
        if converted is None:
            raise RuntimeError(
                f"Could not create landcover grid for trajectory {trajectory_id!r}"
            )
        if is_long_range:
            _remap_land_water_grid(grid_path)

        results[trajectory_id] = _EnvironmentFiles(raster_path, grid_path)

    return results


def create_landcover_data_txt(
    traj: mpd.TrajectoryCollection,
    is_long_range: bool = False,
    resolution: int = 200,
    out_directory: str | Path | None = None,
    **legacy_options,
) -> dict[Any, str]:
    """Create one projected environment grid per animal trajectory."""
    if "is_marine" in legacy_options:
        warnings.warn(
            "is_marine is deprecated; use is_long_range",
            DeprecationWarning,
            stacklevel=2,
        )
        is_long_range = bool(legacy_options.pop("is_marine"))
    if legacy_options:
        unexpected = next(iter(legacy_options))
        raise TypeError(f"unexpected keyword argument: {unexpected!r}")

    files = _prepare_environment_data(
        traj,
        is_long_range=is_long_range,
        resolution=resolution,
        output_directory=out_directory,
    )
    return {trajectory_id: str(paths.grid) for trajectory_id, paths in files.items()}


def annotate_trajectory_collection_environment(
    trajectories: mpd.TrajectoryCollection,
    *,
    is_long_range: bool = False,
    resolution: int = 1000,
    output_directory: str | Path | None = None,
    add_utm: bool = True,
    inplace: bool = False,
):
    """
    Fetch, project, and annotate environmental cover independently per animal.

    Long-range trajectories use the packaged land polygons and are classified
    only as land or water. Local trajectories use ESA WorldCover classes.
    """
    collection = trajectories if inplace else deepcopy(trajectories)
    files = _prepare_environment_data(
        collection,
        is_long_range=is_long_range,
        resolution=resolution,
        output_directory=output_directory,
    )
    class_lookup = land_water_classes if is_long_range else landcover_classes

    import pandas as pd

    for trajectory in collection.trajectories:
        df = trajectory.df.copy()
        source_crs = df.crs
        if source_crs is None:
            raise ValueError("Trajectory data frame must have a CRS")

        terrain = sample_raster_at_points(
            df.geometry,
            files[trajectory.id].raster,
            source_crs=source_crs,
        )
        terrain.index = df.index
        if is_long_range:
            terrain = terrain.map(
                lambda value: value
                if pd.isna(value)
                else _LAND_WATER_VALUE_MAP.get(value, value)
            )
        df["terrain"] = terrain
        df["terrain_name"] = terrain.map(
            lambda value: pd.NA
            if pd.isna(value)
            else class_lookup.get(value, str(value))
        )

        if add_utm:
            df = _add_utm_columns(
                df,
                x_column="utm_x",
                y_column="utm_y",
                crs_column="utm_crs",
                source_crs=source_crs,
            )
        trajectory.df = df

    return collection


def annotate_tcol_terrain(
    is_long_range=None,
    trajectories=None,
    output_directory=None,
    add_utm=True,
    resolution=1000,
    **legacy_options,
):
    """Compatibility wrapper for :func:`annotate_trajectory_collection_environment`."""
    used_legacy_name = False
    if "is_marine" in legacy_options:
        is_long_range = legacy_options.pop("is_marine")
        used_legacy_name = True
    if "turtles" in legacy_options:
        trajectories = legacy_options.pop("turtles")
        used_legacy_name = True
    if "tmp_path" in legacy_options:
        output_directory = legacy_options.pop("tmp_path")
        used_legacy_name = True
    if legacy_options:
        unexpected = next(iter(legacy_options))
        raise TypeError(f"unexpected keyword argument: {unexpected!r}")
    if used_legacy_name:
        warnings.warn(
            "is_marine/turtles/tmp_path are deprecated; use "
            "is_long_range/trajectories/output_directory",
            DeprecationWarning,
            stacklevel=2,
        )
    if trajectories is None:
        raise TypeError("trajectories is required")

    return annotate_trajectory_collection_environment(
        trajectories,
        is_long_range=bool(is_long_range),
        resolution=resolution,
        output_directory=output_directory,
        add_utm=add_utm,
    )
