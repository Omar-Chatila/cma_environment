import numpy as np
import pandas as pd


def fetch_ocean_data(data, output_directory: str, dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"):
    """Fetch eastward and northward ocean currents from Copernicus Marine."""
    import os

    import copernicusmarine
    from dotenv import load_dotenv

    load_dotenv()
    max_lat = data["location-lat"].max()
    max_long = data["location-long"].max()
    min_lat = data["location-lat"].min()
    min_long = data["location-long"].min()
    start_date = data["timestamp"].min()
    end_date = data["timestamp"].max()

    return copernicusmarine.subset(
        dataset_id=dataset_id,
        output_directory=output_directory,
        username=os.getenv("COPERNICUS_USERNAME"),
        password=os.getenv("COPERNICUS_PASSWORD"),
        minimum_latitude=min_lat,
        maximum_latitude=max_lat,
        minimum_longitude=min_long,
        maximum_longitude=max_long,
        start_datetime=start_date,
        end_datetime=end_date,
        variables=["time", "latitude", "longitude", "uo", "vo"],
    )


def convert_nc_in_csv(file_path):
    import xarray as xr

    ds = xr.open_dataset(file_path)
    return ds.to_dataframe().to_csv()


def build_currents_dataframe(raw_data):
    """
    Build a current DataFrame suitable for per-step interpolation.

    Required columns: ``time``, ``longitude``, ``latitude``, ``uo``, ``vo``.
    """
    df = pd.DataFrame(raw_data)

    required_cols = ["time", "longitude", "latitude", "uo", "vo"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df["time"] = pd.to_datetime(df["time"])
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["uo"] = pd.to_numeric(df["uo"], errors="coerce")
    df["vo"] = pd.to_numeric(df["vo"], errors="coerce")

    df = df.dropna(subset=required_cols)
    df = df.sort_values(by=["time", "latitude", "longitude"]).reset_index(drop=True)

    return df


def currents_df_to_grid(df_currents, lon_res=0.01, lat_res=0.01):
    """
    Convert currents into 2D nearest-neighbor grids.
    """
    lon_min, lon_max = df_currents["longitude"].min(), df_currents["longitude"].max()
    lat_min, lat_max = df_currents["latitude"].min(), df_currents["latitude"].max()
    grid_x = np.arange(lon_min, lon_max + lon_res, lon_res)
    grid_y = np.arange(lat_min, lat_max + lat_res, lat_res)

    currents_u = np.zeros((len(grid_y), len(grid_x)))
    currents_v = np.zeros((len(grid_y), len(grid_x)))

    for i, y in enumerate(grid_y):
        for j, x in enumerate(grid_x):
            dist2 = (df_currents["longitude"].values - x) ** 2 + (df_currents["latitude"].values - y) ** 2
            idx_min = np.argmin(dist2)
            currents_u[i, j] = df_currents["uo"].values[idx_min]
            currents_v[i, j] = df_currents["vo"].values[idx_min]

    return grid_x, grid_y, currents_u, currents_v
