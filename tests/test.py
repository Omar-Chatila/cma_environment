import pickle
from pathlib import Path

from environmentcma import annotate_study_pickle, RangeType

FIXTURE_DIR = Path(__file__).resolve().parent

def test_terrestrial_study():
    path = FIXTURE_DIR / "bears.pickle"

    annotated_tcol = annotate_study_pickle(study_pickle=path,
                                           range_type=RangeType.LOCAL,
                                           resolution=1000,
    )
    print(annotated_tcol.to_point_gdf().head())
    pickle.dump(annotated_tcol, open(FIXTURE_DIR / "annotated.pickle", "wb"))

def test_bird_study():
    path = FIXTURE_DIR / "rubythroat.pickle"
    annotated_tcol = annotate_study_pickle(study_pickle=path,
                                           range_type=RangeType.LONG_RANGE,
                                           resolution=1000,
                                           output_directory=FIXTURE_DIR,
                                           add_utm=True)

    print(annotated_tcol.to_point_gdf().head())
    pickle.dump(annotated_tcol, open(FIXTURE_DIR / "annotated.pickle", "wb"))


test_terrestrial_study()
test_bird_study()
