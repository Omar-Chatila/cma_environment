"""Environmental data helpers for random-walk workflows.

This package intentionally has no dependency on ``random_walk_package`` or its
compiled extension. Public helpers are loaded lazily so importing the package
does not pull in heavy geospatial dependencies until a specific helper needs
them.
"""

from importlib import import_module

_EXPORTS = {
    "bbox_to_discrete_space": "bounds",
    "build_currents_dataframe": "currents",
    "clamp_lonlat_bbox": "bounds",
    "convert_nc_in_csv": "currents",
    "create_weather_csvs": "weather",
    "currents_df_to_grid": "currents",
    "fetch_landcover_data": "landcover",
    "fetch_ocean_cover_tif": "ocean_cover",
    "fetch_ocean_data": "currents",
    "fetch_weather_data": "weather",
    "geodetic_to_utm": "crs",
    "grid_shape_from_bbox": "crs",
    "grid_to_geo": "crs",
    "grid_to_geo_walk": "crs",
    "landcover_classes": "landcover",
    "landcover_to_discrete_txt": "landcover",
    "lonlat_bbox_to_utm": "crs",
    "make_segment_transformer": "crs",
    "marine_cover_path": "ocean_cover",
    "padded_bbox": "bounds",
    "padded_utm_bbox": "crs",
    "reproject_to_utm": "crs",
    "utm_bbox_to_lonlat": "crs",
    "utm_to_grid": "crs",
    "utm_to_lonlat": "crs",
    "utm_zone_from_lon": "crs",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(f"{__name__}.{_EXPORTS[name]}")
    value = getattr(module, name)
    globals()[name] = value
    return value
