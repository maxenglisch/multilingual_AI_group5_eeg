import numpy as np
from src.feature_extraction import subject_weighted_group_timeseries

def test_subjects_have_equal_weight_not_epoch_weight():
    mean,_=subject_weighted_group_timeseries({"S1":np.array([[0.,0.]]),"S2":np.array([[10.,10.]])})
    assert np.allclose(mean,5.0)
