import pickle
from pathlib import Path

from environmentcma import annotate_study_pickle, RangeType

FIXTURE_DIR = Path(__file__).resolve().parent

def test_terrestrial_study():
    path = FIXTURE_DIR / "bears.pickle"
    t_col = pickle.load(open(path, "rb"))
    annotated_tcol = annotate_study_pickle(trajectories=t_col,
                                           output_directory=FIXTURE_DIR,
                                           range_type=RangeType.LOCAL,
                                           resolution=1000,
    )
    print(annotated_tcol.to_point_gdf().head())
    pickle.dump(annotated_tcol, open(FIXTURE_DIR / "bears_annotated.pickle", "wb"))

def test_bird_study():
    path = FIXTURE_DIR / "rubythroat.pickle"
    t_col = pickle.load(open(path, "rb"))
    annotated_tcol = annotate_study_pickle(trajectories=t_col,
                                           output_directory=FIXTURE_DIR,
                                           range_type=RangeType.LONG_RANGE,
                                           resolution=1000,
                                           add_utm=True)

    print(annotated_tcol.to_point_gdf().head())
    pickle.dump(annotated_tcol, open(FIXTURE_DIR / "rubythroats_annotated.pickle", "wb"))


test_terrestrial_study()
test_bird_study()
