"""Motor-task descriptive bar charts generated from existing group CSV outputs."""
from __future__ import annotations

from pathlib import Path
import logging
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)


FOCUS_CHANNELS = [
    "FC3", "FC1", "FCz", "FC2", "FC4", "C3", "C1", "Cz", "C2", "C4",
    "CP3", "CP1", "CPz", "CP2", "CP4",
]
REGIONS = {
    "left": ["FC3", "FC1", "C3", "C1", "CP3", "CP1"],
    "midline": ["FCz", "Cz", "CPz"],
    "right": ["FC2", "FC4", "C2", "C4", "CP2", "CP4"],
}
EPOCH_KEYS = ["subject_id", "recording_key", "epoch_index"]


def _require_columns(frame, columns, table_name):
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{table_name} is missing required columns: {missing}")


def prepare_valid_motor_events(subject_qc):
    _require_columns(subject_qc, ["subject_id", "valid_epoch_count", "dropped_epoch_count", "processing_status"], "subject_qc_summary.csv")
    accepted = subject_qc["processing_status"].astype(str).str.lower().isin({"success", "partial_success"})
    result = subject_qc.loc[accepted, ["subject_id", "valid_epoch_count", "dropped_epoch_count", "processing_status"]].copy()
    result = result.rename(columns={"valid_epoch_count": "valid_motor_events", "dropped_epoch_count": "dropped_motor_events"})
    result["valid_motor_events"] = pd.to_numeric(result["valid_motor_events"], errors="raise")
    result["dropped_motor_events"] = pd.to_numeric(result["dropped_motor_events"], errors="raise")
    return result.sort_values(["valid_motor_events", "subject_id"], ascending=[False, True]).reset_index(drop=True)


def select_epoch_winners(features):
    _require_columns(features, EPOCH_KEYS + ["channel"], "mrcp_epoch_features.csv")
    if features.empty:
        raise ValueError("mrcp_epoch_features.csv is empty")
    valid = features.copy()
    if "epoch_valid" in valid.columns:
        truth = valid["epoch_valid"].astype(str).str.lower().isin({"true", "1"})
        valid = valid.loc[truth]
    valid = valid[valid["channel"].isin(FOCUS_CHANNELS)].copy()
    if valid.empty:
        raise ValueError("No valid rows remain for the configured motor-related EEG channels")
    if "minimum_amplitude_uv" in valid.columns:
        metric = "minimum_amplitude_uv"
        valid[metric] = pd.to_numeric(valid[metric], errors="coerce")
        valid = valid.dropna(subset=[metric])
        winner_indices = valid.groupby(EPOCH_KEYS, sort=False)[metric].idxmin()
    elif "post_minus_pre_uv" in valid.columns:
        metric = "post_minus_pre_uv"
        valid[metric] = pd.to_numeric(valid[metric], errors="coerce")
        valid = valid.dropna(subset=[metric])
        valid["_winner_metric"] = valid[metric].abs()
        winner_indices = valid.groupby(EPOCH_KEYS, sort=False)["_winner_metric"].idxmax()
    else:
        raise ValueError("mrcp_epoch_features.csv requires minimum_amplitude_uv or post_minus_pre_uv; raw instantaneous amplitude will not be inferred")
    if valid.empty or len(winner_indices) == 0:
        raise ValueError(f"No finite values are available for winner metric {metric}")
    winners = valid.loc[winner_indices, EPOCH_KEYS + ["channel"]].copy()
    winners["metric_used"] = metric
    if winners.duplicated(EPOCH_KEYS).any():
        raise RuntimeError("Each valid epoch must produce exactly one winner channel")
    return winners.reset_index(drop=True)


def summarize_winner_channels(winners):
    _require_columns(winners, EPOCH_KEYS + ["channel", "metric_used"], "winner rows")
    total = len(winners)
    if not total:
        raise ValueError("No epoch winners are available")
    result = winners.groupby("channel", as_index=False).size().rename(columns={"size": "winner_count"})
    result["percentage_of_valid_epochs"] = result["winner_count"] / total * 100.0
    result["metric_used"] = winners["metric_used"].iloc[0]
    return result.sort_values(["winner_count", "channel"], ascending=[False, True]).reset_index(drop=True)


def summarize_regions(winners):
    channel_region = {channel: region for region, channels in REGIONS.items() for channel in channels}
    regions = winners["channel"].map(channel_region)
    if regions.isna().any():
        raise ValueError(f"Winner channels lack a configured region: {sorted(winners.loc[regions.isna(), 'channel'].unique())}")
    counts = regions.value_counts().reindex(REGIONS, fill_value=0)
    return pd.DataFrame({
        "region": counts.index,
        "winner_count": counts.values,
        "percentage_of_valid_epochs": counts.values / len(winners) * 100.0,
    })


def _horizontal_bar_pillow(labels, values, title, subtitle, xlabel, path, annotations):
    """Compatibility renderer for the known Matplotlib transform DLL failure on Win/Py3.14."""
    from PIL import Image, ImageDraw, ImageFont
    labels, values, annotations = list(labels), list(values), list(annotations)
    width, row_height = 2200, 62
    height = max(900, 260 + row_height * len(labels))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    font = ImageFont.truetype(str(font_path), 28); title_font = ImageFont.truetype(str(font_path), 38)
    draw.text((80, 35), title, fill="black", font=title_font)
    draw.text((80, 90), subtitle, fill="black", font=font)
    draw.text((800, height-55), xlabel, fill="black", font=font)
    maximum = max(values) if values else 0
    left, right, top = 280, width-300, 165
    default_color = matplotlib.rcParams["axes.prop_cycle"].by_key()["color"][0]
    for index, (label, value, annotation) in enumerate(zip(labels, values, annotations)):
        y = top + index * row_height
        draw.text((60, y+8), str(label), fill="black", font=font)
        bar_width = int((float(value) / maximum) * (right-left)) if maximum else 0
        draw.rectangle((left, y, left+bar_width, y+40), fill=default_color)
        draw.text((left+bar_width+14, y+7), str(annotation), fill="black", font=font)
    image.save(path, dpi=(200, 200))


def _horizontal_bar(labels, values, title, subtitle, xlabel, path, annotations):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Matplotlib 3.10 on the supplied Windows/Python 3.14 Conda environment
    # terminates inside its native Bezier transform. Other environments use
    # the requested standard Agg renderer; this branch keeps the CLI usable.
    if sys.platform == "win32" and sys.version_info >= (3, 14):
        _horizontal_bar_pillow(labels, values, title, subtitle, xlabel, path, annotations)
        plt.close("all")
        return
    height = max(4.5, 0.32 * len(labels) + 1.8)
    fig, axis = plt.subplots(figsize=(11, height))
    bars = axis.barh(range(len(labels)), values)
    axis.set_yticks(range(len(labels)), labels)
    axis.invert_yaxis()
    axis.set_xlabel(xlabel)
    axis.set_title(f"{title}\n{subtitle}")
    maximum = max(values) if len(values) else 0
    margin = max(maximum * 0.01, 0.1)
    for bar, annotation in zip(bars, annotations):
        axis.text(bar.get_width() + margin, bar.get_y() + bar.get_height() / 2, annotation, va="center")
    axis.set_xlim(0, max(maximum * 1.22, 1))
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def generate_motorik_barcharts(output_dir, update_report=True):
    group = Path(output_dir) / "group_analysis"
    tables, figures = group / "tables", group / "figures"
    qc_path, feature_path = tables / "subject_qc_summary.csv", tables / "mrcp_epoch_features.csv"
    logger.info("Reading subject QC table: %s", qc_path.resolve())
    if not qc_path.exists():
        raise FileNotFoundError(
            f"Motorik Bar Chart input not found:\n{qc_path}\n\nPlease run:\n"
            'python -m src.main --data-dir "D:\\Uni\\10\\MUlti\\EEG and EMG Dataset for Analyzing Movement-Related\\SUBJECTS" --output-dir outputs --all-subjects')
    logger.info("Reading MRCP epoch features: %s", feature_path.resolve())
    if not feature_path.exists():
        raise FileNotFoundError(
            f"Motorik Bar Chart input not found:\n{feature_path}\n\nPlease run:\n"
            'python -m src.main --data-dir "D:\\Uni\\10\\MUlti\\EEG and EMG Dataset for Analyzing Movement-Related\\SUBJECTS" --output-dir outputs --all-subjects')

    motor_events = prepare_valid_motor_events(pd.read_csv(qc_path))
    winners = select_epoch_winners(pd.read_csv(feature_path))
    channel_frequency = summarize_winner_channels(winners)
    region_frequency = summarize_regions(winners)

    paths = {
        "valid_events_png": figures / "valid_motor_events_per_subject.png",
        "prominent_channel_png": figures / "most_frequent_mrcp_channel.png",
        "region_frequency_png": figures / "mrcp_region_frequency.png",
        "valid_events_csv": tables / "valid_motor_events_per_subject.csv",
        "prominent_channel_csv": tables / "most_frequent_mrcp_channel.csv",
        "region_frequency_csv": tables / "mrcp_region_frequency.csv",
    }
    motor_events.to_csv(paths["valid_events_csv"], index=False)
    channel_frequency.to_csv(paths["prominent_channel_csv"], index=False)
    region_frequency.to_csv(paths["region_frequency_csv"], index=False)
    for key in ("valid_events_csv", "prominent_channel_csv", "region_frequency_csv"):
        logger.info("Saved: %s", paths[key].resolve())
    logger.info("Generating valid movement events chart...")
    _horizontal_bar(
        motor_events["subject_id"], motor_events["valid_motor_events"],
        "Valid Motor Events per Subject", "Anzahl gültiger Bewegungsereignisse pro Versuchsperson",
        "Number of valid movement epochs", paths["valid_events_png"],
        motor_events["valid_motor_events"].map(lambda value: f"{value:g}"))
    logger.info("Saved: %s", paths["valid_events_png"].resolve())
    logger.info("Generating prominent channel chart...")
    _horizontal_bar(
        channel_frequency["channel"], channel_frequency["winner_count"],
        "Most Frequently Prominent Motor-Related EEG Channel",
        "Am häufigsten auffälliger motorikbezogener EEG-Kanal", "Number of epochs",
        paths["prominent_channel_png"],
        channel_frequency.apply(lambda row: f"{row.winner_count:g} ({row.percentage_of_valid_epochs:.1f}%)", axis=1))
    logger.info("Saved: %s", paths["prominent_channel_png"].resolve())
    logger.info("Generating region frequency chart...")
    _horizontal_bar(
        region_frequency["region"], region_frequency["winner_count"],
        "Distribution of Prominent Motor-Related EEG Regions",
        "Verteilung auffälliger motorikbezogener EEG-Regionen", "Number of epochs",
        paths["region_frequency_png"],
        region_frequency.apply(lambda row: f"{row.winner_count:g} ({row.percentage_of_valid_epochs:.1f}%)", axis=1))
    logger.info("Saved: %s", paths["region_frequency_png"].resolve())

    if update_report:
        from .report import refresh_group_report
        refresh_group_report(group / "reports" / "group_mrcp_report.html")
    logger.info("Motorik bar charts completed.")
    return {key: path.resolve() for key, path in paths.items()}
