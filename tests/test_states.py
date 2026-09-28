import numpy as np
import pytest

from src.bandpower import BandpowerSeries
from src.config import load_config, states_definitions_path
from src.states import QualityGateError, StateScorer, asymmetry_index, load_definitions

BANDS, STATES = load_definitions(states_definitions_path(load_config()))
CHANNELS = ["F3", "F4", "AF3", "AF4", "Fz", "FCz", "Cz", "C3", "C4", "FC3", "FC4", "CP3", "CP4",
            "CPz", "Pz", "P3", "P4", "POz", "O1", "O2"]


def _series(n_frames=200, seed=0):
    rng = np.random.default_rng(seed)
    power = {band: rng.normal(0, 1, (n_frames, len(CHANNELS))) for band in BANDS}
    return BandpowerSeries(np.arange(n_frames) * 0.25 + 0.5, CHANNELS, power,
                           np.ones(n_frames, bool), np.zeros(n_frames), np.full(n_frames, 30.0),
                           np.array(["ok"] * n_frames), 1.0, 0.25)


def _raise(series, frames, channels, band, db):
    for channel in channels:
        series.power_db[band][frames, CHANNELS.index(channel)] += db


def test_posterior_alpha_increase_scores_relaxation():
    series = _series()
    baseline = np.arange(200) < 100
    _raise(series, slice(100, 200), ["O1", "O2", "POz", "Pz", "P3", "P4"], "alpha", 4.0)
    scorer = StateScorer.from_series(series, baseline, STATES)
    ranking = scorer.score_mask(series, ~baseline)
    assert ranking[0].id == "entspannung" and ranking[0].detected
    assert ranking[0].score == 1.0 and ranking[0].z > 3


def test_contralateral_mu_drop_ranks_right_hand_first():
    series = _series()
    baseline = np.arange(200) < 100
    _raise(series, slice(100, 200), ["C3", "FC3", "CP3"], "mu", -3.0)
    ranking = StateScorer.from_series(series, baseline, STATES).score_mask(series, ~baseline)
    order = [s.id for s in ranking]
    assert order[0] == "motorik_rechts"
    assert order.index("motorik_links") > order.index("motorik_rechts")


def test_quiet_window_detects_nothing():
    series = _series()
    baseline = np.arange(200) < 100
    ranking = StateScorer.from_series(series, baseline, STATES).score_mask(series, ~baseline)
    assert not any(s.detected for s in ranking)


def test_asymmetry_sign_and_contribution():
    index, contribution, note = asymmetry_index({"F3": 1.0, "F4": 3.0}, {"F3": -1.0, "F4": 1.0})
    assert index == 2.0 and contribution == 2.0 and "approach" in note
    assert asymmetry_index({"F3": 1.0}, {"F3": 0.0})[0] is None


def test_baseline_that_fails_the_gate_raises():
    series = _series()
    series.frame_ok[:100] = False
    with pytest.raises(QualityGateError):
        StateScorer.from_series(series, np.arange(200) < 100, STATES)
