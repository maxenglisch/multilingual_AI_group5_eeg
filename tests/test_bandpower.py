import numpy as np

from src.bandpower import compute_bandpower

BANDS = {"theta": {"lo": 4, "hi": 7}, "alpha": {"lo": 8, "hi": 12}, "mu": {"lo": 8, "hi": 13},
         "highbeta": {"lo": 16, "hi": 30}}


def _noise(n_ch=32, seconds=20, sfreq=128, seed=0):
    return np.random.default_rng(seed).normal(0, 5, (n_ch, int(seconds * sfreq)))


def test_sine_lands_in_its_band(make_raw, gate):
    data = _noise()
    t = np.arange(data.shape[1]) / 128
    data[30] += 20 * np.sin(2 * np.pi * 10 * t)                       # O1
    series = compute_bandpower(make_raw(data), BANDS, 1.0, 0.25, gate)
    o1 = series.channels.index("O1")
    alpha = np.nanmean(series.power_db["alpha"], axis=0)
    assert alpha.argmax() == o1
    assert alpha[o1] - np.median(alpha) > 10
    assert abs(np.nanmean(series.power_db["theta"][:, o1]) - np.median(np.nanmean(series.power_db["theta"], 0))) < 3


def test_psd_scaling_matches_white_noise_density(make_raw, gate):
    data = _noise(seed=1)
    series = compute_bandpower(make_raw(data), {"all": {"lo": 1, "hi": 60}}, 1.0, 0.5, gate)
    # white noise with sigma=5 uV at 128 Hz has a one-sided density of 2*25/128 uV^2/Hz
    assert abs(np.nanmean(series.power_db["all"]) - 10 * np.log10(2 * 25 / 128)) < 0.5


def test_frame_times_are_window_centres(make_raw, gate):
    series = compute_bandpower(make_raw(_noise(seconds=5)), BANDS, 1.0, 0.5, gate)
    assert np.allclose(series.times[:3], [0.5, 1.0, 1.5])
    mask = series.segment_mask(1.0, 3.0)
    assert np.allclose(series.times[mask], [1.5, 2.0, 2.5])


def test_gate_rejects_artifact_cells_and_frames(make_raw, gate):
    data = _noise()
    data[0, int(5.2 * 128):int(5.8 * 128)] += 400                      # AF3 step artefact inside 5-6 s
    data[:, 12 * 128:13 * 128] += np.linspace(0, 500, 128)             # every channel at 12-13 s
    series = compute_bandpower(make_raw(data), BANDS, 1.0, 0.5, gate)
    at = lambda s: int(np.argmin(np.abs(series.times - s)))
    assert series.frame_ok[at(5.5)] and np.isnan(series.power_db["alpha"][at(5.5), 0])
    assert not series.frame_ok[at(12.5)] and series.reason[at(12.5)] == "amplitude"
    assert series.frame_ok[at(9.0)] and not np.isnan(series.power_db["alpha"][at(9.0)]).any()
