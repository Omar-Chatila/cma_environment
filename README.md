# environmentcma

Environmental annotation helpers for MovingPandas trajectory collections.

## Annotate a pickled study

```python
from environmentcma import RangeType, annotate_study_pickle

annotated = annotate_study_pickle(
    "study.pickle",
    range_type=RangeType.LONG_RANGE,
    resolution=1000,
)
```

`RangeType.LOCAL` fetches ESA WorldCover classes. `RangeType.LONG_RANGE`
uses the packaged Natural Earth land polygons and annotates only `Land` or
`Water`. Processing and CRS selection happen independently for each animal;
all fixes for one animal are transformed to the UTM zone containing the
spatial centre of that animal's track.

The returned value is the annotated `movingpandas.TrajectoryCollection`.
Generated rasters and discrete grids are stored next to the input pickle in a
`<study-name>_environment` directory unless `output_directory` is provided.
