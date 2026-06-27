from pathlib import Path
from typing import Any
import geopandas

from . import utm_to_grid, traj_utm
from . import bbox_utm, grid_shape_from_bbox
from . import fetch_landcover_for_trajectory_collection, annotate_trajectory_collection_with_terrain, \
    landcover_classes

from . import fetch_landcover_data, landcover_to_discrete_txt
from . import fetch_ocean_cover_tif, marine_cover_path
import movingpandas as mpd

def create_landcover_data_txt(traj:mpd.TrajectoryCollection, is_marine: bool = False, resolution: int = 200,
                                out_directory: str | None = None) -> dict[Any, str]:
    
    if out_directory is None:
        out_directory = "landcover"

    out_directory = Path(out_directory, "landcover")
    out_directory.mkdir(exist_ok=True, parents=True)

    shapefile_path = marine_cover_path()

    results = {}
    for traj in traj.trajectories:
        traj_id = traj.id
        # PADDED GEO BBOX (lon/lat)
        min_lon, min_lat, max_lon, max_lat = traj.df.total_bounds
        # PADDED UTM BBOX (x/y)
        utm_bbox, _ = bbox_utm(traj)
        # REGULAR GRID SHAPE (x/y)
        nx, ny = grid_shape_from_bbox(utm_bbox, resolution)
        # TRAJECTORY IN UTM
        trajectory_utm = traj_utm(traj)
        df = trajectory_utm.df.copy()
        # GRID COORDINATES
        gx, gy = utm_to_grid(
            nx, ny, utm_bbox,
            df.geometry.x.values,
            df.geometry.y.values
        )
        # Add grid coordinates to trajectory
        traj.df["grid_x"] = gx
        traj.df["grid_y"] = gy

        terrain_TIFFs = {}
        # Output paths
        base_name = (
            f"landcover_{traj_id}_"
            f"{min_lon:.2f}_{min_lat:.2f}_{max_lon:.2f}_{max_lat:.2f}"
        )
        tif_path = out_directory / f"{base_name}.tif"
        txt_path = out_directory / f"{base_name}_{resolution}.txt"
        terrain_TIFFs[str(traj_id)] = tif_path
        # only fetch TIFF if it doesn't exist yet
        if not tif_path.exists():
            if is_marine:
                fetch_ocean_cover_tif(
                    str(shapefile_path),
                    (min_lon, min_lat, max_lon, max_lat),
                    str(tif_path),
                )
            else:
                fetch_landcover_data(
                    (min_lon, min_lat, max_lon, max_lat),
                    str(tif_path),
                )

        landcover_to_discrete_txt(
            str(tif_path),
            res_x=nx, res_y=ny,
            min_lon=min_lon, max_lat=max_lat, max_lon=max_lon, min_lat=min_lat,
            output=str(txt_path),
        )
        if is_marine:
            with open(txt_path, 'r') as file:
                data = file.read()
            OCEAN_VALUE = 0
            LAND_VALUE = 1
            OCEAN_VALUE_MAPPED = 80
            LAND_VALUE_MAPPED = 10
            # Use temporary placeholder to avoid conflicts
            data = data.replace(str(OCEAN_VALUE), str(OCEAN_VALUE_MAPPED))
            data = data.replace(str(LAND_VALUE), str(LAND_VALUE_MAPPED))
            data = data.replace("255", str(OCEAN_VALUE_MAPPED))

            with open(txt_path, 'w') as file:
                file.write(data)

        results[traj_id] = str(txt_path)

    return results


def annotate_tcol_terrain(is_marine, turtles, tmp_path, add_utm=True):

    original_dfs = [trajectory.df.copy() for trajectory in turtles.trajectories]
    output_filename = tmp_path / "landcover_aoi.tif"

    if is_marine:
        landcover_tif = 0
    else:
        landcover_tif = fetch_landcover_for_trajectory_collection(
            is_marine,
            turtles,
            output_filename=output_filename,
        )

    assert landcover_tif == output_filename
    assert output_filename.exists()

    annotated = annotate_trajectory_collection_with_terrain(
        turtles,
        landcover_tif,
        add_utm=add_utm,
    )
    return annotated