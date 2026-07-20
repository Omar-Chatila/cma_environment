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
    trajectories: mpd.TrajectoryCollection,
    output_directory: str | Path,
    *,
    range_type: RangeType | str = RangeType.LOCAL,
    resolution: int = 1000,
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

    resolution = int(resolution)

    selected_range = _coerce_range_type(range_type)
    artifact_directory = (
        Path(output_directory)
    )
    return annotate_trajectory_collection_environment(
        trajectories,
        is_long_range=selected_range is RangeType.LONG_RANGE,
        resolution=resolution,
        output_directory=artifact_directory,
        add_utm=add_utm,
    )
