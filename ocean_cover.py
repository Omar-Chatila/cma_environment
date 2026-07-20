from importlib import resources
from pathlib import Path

import numpy as np

from .crs import reproject_to_utm


def marine_cover_path(filename: str = "ne_10m_land.shp") -> Path:
    return Path(resources.files("environmentcma.resources.marine_cover") / filename)


def fetch_ocean_cover_tif(
    shapefile_path: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    output_tif_path: str | None = None,
    resolution_deg: float = 0.01,
    ocean_value: int = 0,
    land_value: int = 1,
) -> str:
    """
    Rasterize packaged or user-provided land polygons into an ocean/land GeoTIFF.

    Parameters
    ----------
    shapefile_path
        Path to a land-boundary shapefile. If ``None``, the packaged Natural
        Earth land polygons are used.
    bbox
        Bounding box as ``(min_lon, min_lat, max_lon, max_lat)``.
    output_tif_path
        Output GeoTIFF path. The saved raster is reprojected to the local UTM zone.
    """
    if shapefile_path is None:
        shapefile_path = str(marine_cover_path())
    if bbox is None:
        raise ValueError("bbox is required")
    if output_tif_path is None:
        raise ValueError("output_tif_path is required")

    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize

    print(f"\nFetching ocean cover data for BBOX: {bbox}...")
    min_lon, min_lat, max_lon, max_lat = bbox

    minimum_span = max(2 * resolution_deg, 1e-6)
    if max_lon - min_lon < minimum_span:
        center_lon = 0.5 * (min_lon + max_lon)
        min_lon = center_lon - 0.5 * minimum_span
        max_lon = center_lon + 0.5 * minimum_span
    if max_lat - min_lat < minimum_span:
        center_lat = 0.5 * (min_lat + max_lat)
        min_lat = center_lat - 0.5 * minimum_span
        max_lat = center_lat + 0.5 * minimum_span
    bbox = min_lon, min_lat, max_lon, max_lat

    land = gpd.read_file(shapefile_path).to_crs("EPSG:4326")
    print(f"Loaded {len(land)} land polygons")

    MIN_RASTER_CELLS = 2  # clip_box requires >1 pixel per axis, this is the floor

    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat
    resolution_deg = min(resolution_deg, lon_span / MIN_RASTER_CELLS, lat_span / MIN_RASTER_CELLS)

    width = max(1, int(np.ceil(lon_span / resolution_deg)))
    height = max(1, int(np.ceil(lat_span / resolution_deg)))
    transform = rasterio.transform.from_bounds(
        min_lon,
        min_lat,
        max_lon,
        max_lat,
        width,
        height,
    )

    land_clipped = land.cx[min_lon:max_lon, min_lat:max_lat]
    print(f"Clipped to {len(land_clipped)} land polygons in bbox")
    if len(land_clipped) == 0:
        print("WARNING: No land geometries found in bbox - result will be all ocean!")

    mask = rasterize(
        [(geom, land_value) for geom in land_clipped.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=ocean_value,
        dtype="uint8",
        all_touched=True,
    )

    with rasterio.open(
        output_tif_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        compress="LZW",
    ) as dst:
        dst.write(mask, 1)

    print("Clipping to exact bbox...")
    import rioxarray

    da = rioxarray.open_rasterio(output_tif_path)
    clipped_xds = da.rio.clip_box(
        minx=bbox[0],
        miny=bbox[1],
        maxx=bbox[2],
        maxy=bbox[3],
        crs="EPSG:4326",
    )

    clipped_xds.rio.to_raster(output_tif_path, compress="LZW", dtype="uint8")

    print(f"Ocean cover data saved to {output_tif_path}")
    print("Reprojecting to UTM zone...")
    reproject_to_utm(output_tif_path, output_tif_path)
    return output_tif_path
