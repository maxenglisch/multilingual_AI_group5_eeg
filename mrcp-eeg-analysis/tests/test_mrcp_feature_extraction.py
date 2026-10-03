import numpy as np
from src.config import load_config
from src.feature_extraction import extract_mrcp_epoch_features

class Epochs:
    times=np.linspace(-2,2,9); ch_names=["C3"]
    def get_data(self,copy=False):
        return np.array([[[0,0,1,0,-2,-1,2,3,4]]])*1e-6

def test_feature_values_and_latency():
    row=extract_mrcp_epoch_features(Epochs(),"SUBJECT01","R1",load_config()).iloc[0]
    assert row.baseline_mean_uv==0
    assert row.minimum_amplitude_uv==-2 and row.minimum_latency_s==0
    assert np.isfinite(row.pre_movement_slope_uv_per_s)
    assert row.post_minus_pre_uv>0
