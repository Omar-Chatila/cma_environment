"""Small public workflows for environmental trajectory annotation."""

from enum import Enum
from numbers import Integral
from pathlib import Path

import movingpandas as mpd
import pickle

from .terrain_annotator import annotate_trajectory_collection_environment


class RangeType(str, Enum):
    """Spatial range used to select the environmental data source."""

    LOCAL = "local"
    LONG_RANGE = "long_range"


def _coerce_range_type(value) -> RangeType:
    if isinstance(value, RangeType):
        return value
    try:
        return RangeType(str(value).lower())
    except ValueError as error:
        choices = ", ".join(item.value for item in RangeType)
        raise ValueError(f"range_type must be one of: {choices}") from error


def annotate_study_pickle(
    study_pickle: str | Path,
    *,
    range_type: RangeType | str = RangeType.LOCAL,
    resolution: int = 1000,
    output_directory: str | Path | None = None,
    add_utm: bool = True,
) -> mpd.TrajectoryCollection:
    """
    Load and environmentally annotate a pickled MovingPandas collection.

    ``RangeType.LOCAL`` fetches ESA WorldCover. ``RangeType.LONG_RANGE``
    rasterizes packaged land polygons and records only land or water. Each
    animal receives coordinates in the UTM zone containing that animal's
    spatial centre.

    ``resolution`` is the maximum grid dimension in cells for each animal.
    Pickle files can execute code while loading. The
    annotated trajectory collection is returned and is not pickled again.
    """
    study_path = Path(study_pickle)
    if not study_path.is_file():
        raise FileNotFoundError(f"Study pickle does not exist: {study_path}")
    if not isinstance(resolution, Integral) or isinstance(resolution, bool) or resolution < 1:
        raise ValueError("resolution must be a positive integer")
    resolution = int(resolution)

    with study_path.open("rb") as source:
        trajectories = pickle.load(source)
    if not hasattr(trajectories, "trajectories"):
        raise TypeError("Study pickle must contain a MovingPandas TrajectoryCollection")

    selected_range = _coerce_range_type(range_type)
    artifact_directory = (
        Path(output_directory)
        if output_directory is not None
        else study_path.parent / f"{study_path.stem}_environment"
    )
    return annotate_trajectory_collection_environment(
        trajectories,
        is_long_range=selected_range is RangeType.LONG_RANGE,
        resolution=resolution,
        output_directory=artifact_directory,
        add_utm=add_utm,
    )
