"""Example: preprocessed epochs, alpha power per segment vs. rest, head maps. Usage: python example_epochs.py [recording.csv]"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np

from eeg_states import BASELINE_LABELS
from flex2_mne_pipeline import DEFAULT_SOURCE, Flex2Pipeline

OUT_PNG = Path(__file__).with_name("exports") / "example_epochs.png"
ALPHA = (8.0, 12.0)


def alpha_power(epochs: mne.Epochs, label: str) -> np.ndarray:
    """Mean alpha power per EEG channel for one segment label."""
    spectrum = epochs[label].compute_psd(method="welch", fmin=ALPHA[0], fmax=ALPHA[1],
                                         verbose=False)
    return spectrum.get_data().mean(axis=(0, 2))


def main(argv: list[str]) -> int:
    csv = Path(argv[0] if argv else DEFAULT_SOURCE)

    pipe = Flex2Pipeline(steps=["notch", "filter", "car"])
    epochs = pipe.process_file(csv)
    print(f"{csv.name}: {len(epochs)} epochs, {epochs.times[-1]:.1f} s each")
    print("segments:", ", ".join(epochs.event_id))
    for warning in pipe.warnings:
        print("  !", warning)

    rest_label = next((name for name in epochs.event_id
                       if name.lower().startswith(BASELINE_LABELS)), None)
    labels = [name for name in epochs.event_id if name != rest_label]
    if rest_label is None or not labels:
        print("This example needs a rest segment (label starting with "
              f"{', '.join(BASELINE_LABELS)}) and at least one other segment.")
        return 1

    epochs = epochs.copy().pick("eeg")
    rest = alpha_power(epochs, rest_label)
    change = {name: 10.0 * np.log10(alpha_power(epochs, name) / rest) for name in labels}

    limit = max(np.abs(v).max() for v in change.values())
    fig, axes = plt.subplots(1, len(labels), figsize=(3.4 * len(labels), 3.6),
                             squeeze=False)
    for ax, name in zip(axes[0], labels):
        mne.viz.plot_topomap(change[name], epochs.info, axes=ax, show=False,
                             cmap="RdBu_r", vlim=(-limit, limit), contours=4)
        ax.set_title(name, fontsize=10)
        top = int(np.argmax(np.abs(change[name])))
        print(f"  {name:22s} largest change: {epochs.ch_names[top]} "
              f"({change[name][top]:+.1f} dB)")
    fig.colorbar(plt.cm.ScalarMappable(cmap="RdBu_r", norm=plt.Normalize(-limit, limit)),
                 ax=axes, fraction=0.03, label=f"alpha power vs. {rest_label} (dB)")
    OUT_PNG.parent.mkdir(exist_ok=True)
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"saved: {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
