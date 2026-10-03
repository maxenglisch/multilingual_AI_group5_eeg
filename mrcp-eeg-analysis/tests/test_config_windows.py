from src.config import load_config

def test_all_windows_are_yaml_values():
    windows=load_config()["epochs"]
    assert windows=={"tmin_s":-2.0,"tmax_s":2.0,"baseline_start_s":-2.0,"baseline_end_s":-1.5,"pre_start_s":-1.0,"pre_end_s":0.0,"movement_start_s":0.0,"movement_end_s":1.0,"post_start_s":1.0,"post_end_s":2.0}
