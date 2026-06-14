import os

from .crs import lonlat_bbox_to_utm, reproject_to_utm, utm_bbox_to_lonlat

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
