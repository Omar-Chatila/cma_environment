import os
from copy import deepcopy
from typing import Iterable, Optional

from .crs import (
    lonlat_bbox_to_utm,
    reproject_to_utm,
    utm_bbox_to_lonlat,
    utm_crs_for_geodataframe,
)

landcover_classes = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}

land_water_classes = {
    10: "Land",
    80: "Water",
}


def _coerce_sample_value(value, nodata):
    import numpy as np
    import pandas as pd

    if np.ma.is_masked(value):
        return pd.NA

    scalar = value.item() if hasattr(value, "item") else value
    if nodata is not None and scalar == nodata:
        return pd.NA
    return scalar


def sample_raster_at_points(
    geometries: Iterable,
    raster_path,
    *,
    source_crs=None,
    band: int = 1,
):
    """
    Sample a raster band at point geometries.

    Parameters
    ----------
    geometries
        Iterable of point geometries.
    raster_path
        Path to a GeoTIFF or other raster readable by rasterio.
    source_crs
        CRS of the input geometries. Required when it cannot be inferred by the
        caller and differs from the raster CRS.
    band
        1-based raster band index to sample.
    """
    import pandas as pd
    import rasterio
    from pyproj import CRS, Transformer

    points = list(geometries)
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError("Raster must have a CRS to annotate trajectories")
        if source_crs is None:
            raise ValueError("source_crs is required to sample raster values")

        source = CRS.from_user_input(source_crs)
        target = CRS.from_user_input(src.crs)

        xs = [point.x for point in points]
        ys = [point.y for point in points]
        if source != target:
            transformer = Transformer.from_crs(source, target, always_xy=True)
            xs, ys = transformer.transform(xs, ys)

        values = [
            _coerce_sample_value(sample[0], src.nodata)
            for sample in src.sample(zip(xs, ys), indexes=band, masked=True)
        ]

    return pd.Series(values)


def _add_utm_columns(df, *, x_column, y_column, crs_column, source_crs):
    from pyproj import CRS, Transformer

    source = CRS.from_user_input(source_crs)
    target = utm_crs_for_geodataframe(df)
    transformer = Transformer.from_crs(source, target, always_xy=True)
    xs, ys = transformer.transform(df.geometry.x.to_numpy(), df.geometry.y.to_numpy())

    result = df.copy()
    result[x_column] = xs
    result[y_column] = ys
    result[crs_column] = target.to_string()
    return result


def trajectory_collection_bbox(traj_collection, target_crs: str = "EPSG:4326"):
    """Return the bounding box of all trajectories in ``target_crs``."""
    import geopandas as gpd
    import pandas as pd

    frames = []
    for trajectory in traj_collection.trajectories:
        df = trajectory.df
        if df.crs is None:
            raise ValueError("Trajectory data frame must have a CRS")
        frames.append(df.to_crs(target_crs))

    if not frames:
        raise ValueError("Trajectory collection contains no trajectories")

    combined = gpd.GeoDataFrame(pd.concat(frames), crs=target_crs)
    min_x, min_y, max_x, max_y = combined.total_bounds
    return float(min_x), float(min_y), float(max_x), float(max_y)


def padded_trajectory_collection_bbox(
    traj_collection,
    *,
    padding: float = 0.0,
    target_crs: str = "EPSG:4326",
):
    """Return a trajectory collection bbox padded by a fraction of its size."""
    min_x, min_y, max_x, max_y = trajectory_collection_bbox(traj_collection, target_crs)
    width = max_x - min_x
    height = max_y - min_y
    pad_x = width * padding
    pad_y = height * padding
    return min_x - pad_x, min_y - pad_y, max_x + pad_x, max_y + pad_y


def fetch_landcover_for_trajectory_collection(
    traj_collection,
    *,
    output_filename="landcover_aoi.tif",
    padding: float = 0.0,
):
    """
    Fetch ESA WorldCover data for the bounding box of a trajectory collection.
    """
    bbox = padded_trajectory_collection_bbox(traj_collection, padding=padding)
    return fetch_landcover_data(bbox, output_filename=output_filename)


def annotate_trajectory_collection_with_terrain(
    traj_collection,
    raster_path,
    *,
    terrain_column: str = "terrain",
    terrain_name_column: Optional[str] = "terrain_name",
    terrain_classes: Optional[dict] = None,
    terrain_value_map: Optional[dict] = None,
    band: int = 1,
    add_utm: bool = False,
    utm_x_column: str = "utm_x",
    utm_y_column: str = "utm_y",
    utm_crs_column: str = "utm_crs",
    inplace: bool = False,
):
    """
    Annotate every trajectory row with terrain sampled from a raster.

    The returned trajectory collection keeps the same trajectories and original
    columns as the input, with terrain columns appended. Set ``add_utm=True`` to
    also append UTM coordinates and the CRS used for those coordinates.
    """
    import pandas as pd

    collection = traj_collection if inplace else deepcopy(traj_collection)
    class_lookup = landcover_classes if terrain_classes is None else terrain_classes

    for trajectory in collection.trajectories:
        df = trajectory.df.copy()
        source_crs = df.crs
        if source_crs is None:
            raise ValueError("Trajectory data frame must have a CRS")

        terrain = sample_raster_at_points(
            df.geometry,
            raster_path,
            source_crs=source_crs,
            band=band,
        )
        terrain.index = df.index
        if terrain_value_map is not None:
            terrain = terrain.map(
                lambda value: value
                if pd.isna(value)
                else terrain_value_map.get(value, value)
            )
        df[terrain_column] = terrain

        if terrain_name_column is not None:
            df[terrain_name_column] = terrain.map(
                lambda value: pd.NA if pd.isna(value) else class_lookup.get(value, str(value))
            )

        if add_utm:
            df = _add_utm_columns(
                df,
                x_column=utm_x_column,
                y_column=utm_y_column,
                crs_column=utm_crs_column,
                source_crs=source_crs,
            )

        trajectory.df = df

    return collection


def annotate_trajectory_collection_with_landcover(
    traj_collection,
    *,
    raster_path=None,
    output_filename="landcover_aoi.tif",
    padding: float = 0.0,
    add_utm: bool = False,
    inplace: bool = False,
    **annotation_kwargs,
):
    """
    Fetch landcover for a trajectory collection bbox and append landcover values.

    If ``raster_path`` is provided, that TIFF is sampled directly. Otherwise the
    trajectory collection bbox is computed and ``fetch_landcover_data`` is used
    to create ``output_filename`` before annotation.
    """
    if raster_path is None:
        raster_path = fetch_landcover_for_trajectory_collection(
            traj_collection,
            output_filename=output_filename,
            padding=padding,
        )
        if raster_path is None:
            raise RuntimeError("Could not fetch landcover data for trajectory collection")

    return annotate_trajectory_collection_with_terrain(
        traj_collection,
        raster_path,
        terrain_column=annotation_kwargs.pop("terrain_column", "landcover"),
        terrain_name_column=annotation_kwargs.pop("terrain_name_column", "landcover_name"),
        add_utm=add_utm,
        inplace=inplace,
        **annotation_kwargs,
    )


def fetch_landcover_data(bbox, output_filename="landcover_aoi.tif"):
    """
    Fetch ESA WorldCover landcover data for a bounding box via Planetary Computer.

    Parameters
    ----------
    bbox
        Bounding box as ``(min_lon, min_lat, max_lon, max_lat)`` in EPSG:4326.
    output_filename
        GeoTIFF output path. The saved raster is reprojected to the local UTM zone.
    """
    import planetary_computer
    import rioxarray
    from pystac_client import Client

    print(f"\nFetching landcover data for BBOX: {bbox}...")
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        search = catalog.search(
            collections=["esa-worldcover"],
            bbox=bbox,
        )

        items = search.item_collection()
        if not items:
            print("No ESA WorldCover items found for the given AOI.")
            return None

        print(f"Found {len(items)} STAC items. Using the first one: {items[0].id}")
        asset_href = items[0].assets["map"].href

        xds = rioxarray.open_rasterio(asset_href).rio.write_crs("EPSG:4326")
        clipped_xds = xds.rio.clip_box(
            minx=bbox[0],
            miny=bbox[1],
            maxx=bbox[2],
            maxy=bbox[3],
            crs="EPSG:4326",
        )

        clipped_xds.rio.to_raster(output_filename, compress="LZW", dtype="uint8")
        print(f"Landcover data saved to {output_filename}")

        print("Reprojecting to UTM zone...")
        reproject_to_utm(output_filename, output_filename)
        return output_filename

    except Exception as e:
        print(f"Error fetching landcover data: {e}")
        return None


def landcover_to_discrete_txt(
    file_path,
    res_x,
    res_y,
    min_lon,
    min_lat,
    max_lon,
    max_lat,
    output="terrain.txt",
) -> tuple[int, tuple[float, float, float, float]] | None:
    import rasterio

    if os.path.exists(output):
        print(f"Output file {output} already exists, overwriting...")
    try:
        bbox_lonlat = (min_lon, min_lat, max_lon, max_lat)

        with rasterio.open(file_path) as src:
            crs_epsg = src.crs.to_epsg()
            if crs_epsg is None:
                raise ValueError("Raster CRS has no valid EPSG code")

            min_x, min_y, max_x, max_y = lonlat_bbox_to_utm(*bbox_lonlat, crs_epsg)
            print(f"BBox transformed to UTM: {min_x}, {min_y}, {max_x}, {max_y}")

            landcover_array = src.read(1)
            array_height, array_width = landcover_array.shape

            row_start, col_start = src.index(min_x, max_y)
            row_stop, col_stop = src.index(max_x, min_y)

            if row_start > row_stop:
                row_start, row_stop = row_stop, row_start
            if col_start > col_stop:
                col_start, col_stop = col_stop, col_start

            row_start = max(0, min(row_start, array_height - 1))
            row_stop = max(0, min(row_stop, array_height - 1))
            col_start = max(0, min(col_start, array_width - 1))
            col_stop = max(0, min(col_stop, array_width - 1))

            roi_rows = row_stop - row_start
            roi_cols = col_stop - col_start

            if roi_rows < 0 or roi_cols < 0 or (row_start == row_stop and col_start == col_stop):
                raise ValueError(
                    "Requested bounding box does not overlap the landcover raster. "
                    f"Raster bounds (lon, lat): {src.bounds}. "
                    f"Requested bbox: ({min_lon}, {min_lat}, {max_lon}, {max_lat})."
                )

            step_y = roi_rows / (res_y - 1) if res_y > 1 else 0
            step_x = roi_cols / (res_x - 1) if res_x > 1 else 0

            with open(output, "w") as f:
                for y_idx in range(res_y):
                    r = row_start + int(y_idx * step_y)
                    r = max(row_start, min(r, row_stop))
                    r = min(r, array_height - 1)

                    row_values = []
                    for x_idx in range(res_x):
                        c = col_start + int(x_idx * step_x)
                        c = max(col_start, min(c, col_stop))
                        c = min(c, array_width - 1)

                        pixel_value = landcover_array[r, c]
                        row_values.append(str(pixel_value))

                    f.write(" ".join(row_values) + "\n")

            print(f"Landcover grid written to {output}")
            print(f"UTM Bounds: {min_x}, {min_y}, {max_x}, {max_y}")
            lon_min, lat_min, lon_max, lat_max = utm_bbox_to_lonlat(min_x, min_y, max_x, max_y, crs_epsg)
            print(f"Debug: UTM Bounds back transformed to Lon/Lat: ({lon_min}, {lat_min}, {lon_max}, {lat_max})")

            return crs_epsg, (min_x, min_y, max_x, max_y)
    except rasterio.RasterioIOError as e:
        print(f"Error opening the file: {e}")
        return None
